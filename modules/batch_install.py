"""
batch_install.py - Batch installation for winget/choco, run in a visible
console window instead of one hidden subprocess per app.

WHY A VISIBLE CONSOLE (not hidden + piped, as an earlier version of this
module did): real testing showed two problems with hiding it entirely -
(1) a batch call can legitimately run 20-60+ seconds with a fully
blocking capture, during which nothing appeared anywhere and the app
looked hung, and (2) winget can still hit an unexpected interactive
prompt (a store terms-of-service agreement, in testing) that a hidden,
non-interactive process has no way to answer. Running in a real,
visible console - the same CREATE_NEW_CONSOLE + PowerShell transcript
mechanism already used for tweaks/scripts - fixes both: the person sees
live download/install progress directly (no more "is this stuck?"), and
if something genuinely needs a prompt answered, it's right there to
answer. --disable-interactivity / -y still get passed so *known*
prompts fail fast rather than block, but the console is the safety net
for anything unexpected.

WHY CHAINED INSTALLS INSTEAD OF `winget import`: real-machine testing
found winget's JSON-import path hitting a well-documented winget source-
cache bug ("Source required for import is not installed" /
"0x8A15000F Data required by the source is missing") that self-heal
(`winget source reset --force`) didn't clear on that machine, and the
same broken source affected direct `winget install` calls too - so
`winget import`'s extra manifest/source-matching machinery was adding
fragility without a compensating benefit. Chaining individual
`winget install --id=X -e --silent` calls with `;` in one PowerShell
console/process achieves the same "one console, one process, many
apps" batching goal winget import was for, without depending on a
manifest's source metadata matching what's actually configured on the
target machine.

ATTRIBUTION: since chained commands run through one wrapping console
process, there's no single meaningful exit code to key off afterward.
Per-app success is decided by a before/after "is it actually installed
now" check (verify_winget_installed / verify_choco_installed) - not by
trying to parse winget's per-package progress text, which is far less
stable across versions than a plain presence query. Choco's summary
line is still parsed first as a fast, well-documented path; winget
relies on the before/after check directly.
"""

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

# Phrases winget prints when it fails at the whole-batch/source level
# rather than for an individual package. When these appear, nothing in
# that run's output (or a "verify" check right after it) can be trusted -
# the right move is to self-heal and retry, or fall back entirely.
_WINGET_FATAL_PATTERNS = (
    "source required for import is not installed",
    "source does not exist",
    "failed to update source",
    "source agreements were not agreed",
    "data required by the source is missing",
    "failed in attempting to update the source",
)

# A specific, well-documented winget bug (see e.g.
# github.com/microsoft/winget-cli issues #5253, #4799, #872): winget's
# per-profile source cache can end up uninitialized/broken, most often
# reported when winget is run elevated on a profile that's never run it
# non-elevated first. `winget source reset --force` is the fix reported
# to work in most cases. This is a subset of _WINGET_FATAL_PATTERNS that
# we specifically know how to try to self-heal, rather than just fall
# back and hope installing one at a time works around it (it usually
# won't - the same broken source affects `winget install` too).
_WINGET_SOURCE_CACHE_PATTERNS = (
    "source required for import is not installed",
    "data required by the source is missing",
    "failed in attempting to update the source",
)

# A few known Windows/winget exit codes worth explaining in plain English
# instead of leaving someone to google a random 10-digit number. Keyed by
# the HRESULT as an unsigned 32-bit int.
_KNOWN_EXIT_CODES = {
    0x8A15000F: (
        "winget: \"Data required by the source is missing\" - a known winget bug where its "
        "per-profile source cache is uninitialized/broken, commonly seen when winget is run "
        "elevated on a profile that has never run it non-elevated first. This app already tries "
        "'winget source reset --force' automatically when it sees this; if it still fails, try "
        "running winget manually once as the normal (non-elevated) user on this machine, or "
        "reboot and try again."
    ),
    0x8A150042: (
        "winget: \"Error reading input in prompt\" - winget needed an interactive answer (e.g. a "
        "store terms-of-service prompt) that couldn't be given in a non-interactive context. This "
        "app now passes --disable-interactivity to fail fast on this instead of hanging, and runs "
        "winget in a visible console so you can answer any prompt directly if one does appear."
    ),
    0x800704C7: (
        "The installer's UAC elevation prompt was cancelled - typically because it appeared "
        "with no elevated context available to answer it (e.g. running non-elevated)."
    ),
}


def decode_windows_exit_code(code) -> str:
    """Turns a raw process exit code into the hex HRESULT form Windows
    tools actually report (e.g. 2316632079 -> '0x8A15000F'), plus a plain-
    English explanation when it's a code we recognize. Windows exit codes
    for HRESULT-style failures often show up as a large unsigned 32-bit
    number (or its negative signed equivalent) rather than the compact
    hex form every winget/choco doc and forum post actually uses - so a
    raw decimal number like "2316632079" is nearly unsearchable, while
    "0x8A15000F" immediately is."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return f"Exit code {code}"
    unsigned = code & 0xFFFFFFFF
    hex_form = f"0x{unsigned:08X}"
    known = _KNOWN_EXIT_CODES.get(unsigned)
    if known:
        return f"Exit code {hex_form}: {known}"
    return f"Exit code {hex_form}"


def is_winget_source_cache_issue(text: str) -> bool:
    lowered = (text or '').lower()
    return any(p in lowered for p in _WINGET_SOURCE_CACHE_PATTERNS)


# Substrings that indicate a failure was actually caused by the process
# not running elevated, seen verbatim in real Chocolatey/winget output:
# choco's own UnauthorizedAccessException writing to ProgramData, and
# winget's installer-level UAC prompt being auto-cancelled (0x800704c7)
# when there's no elevated context to answer the prompt from.
_ELEVATION_FAILURE_PATTERNS = (
    "access to the path",
    "unauthorizedaccessexception",
    "0x800704c7",
    "operation was canceled by the user",
    "not running from an elevated",
    "access is denied",
)


def looks_like_elevation_failure(text: str) -> bool:
    lowered = (text or '').lower()
    return any(p in lowered for p in _ELEVATION_FAILURE_PATTERNS)


def is_elevated() -> bool:
    """Best-effort check of whether the current process is running with
    administrator rights. Returns False (safe default) on any failure or
    on non-Windows platforms."""
    if sys.platform != 'win32':
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class BatchInstallUnavailable(Exception):
    """Raised when the batch command couldn't even be started (tool
    missing, timed out, etc.) - the caller should fall back to the
    proven one-app-at-a-time loop rather than treat this as a per-app
    failure."""
    pass


class WingetBatchFailed(Exception):
    """Raised when winget failed at the whole-batch/source level (see
    _WINGET_FATAL_PATTERNS) rather than for an individual package. None
    of this batch's output (or a 'verify' check afterward) can be
    trusted - callers should treat this the same as
    BatchInstallUnavailable and fall back to installing one at a time."""
    pass


# Chocolatey's progress bar writes one update per percentage tick,
# terminated with \r rather than \n so a real terminal overwrites the
# same line in place. The live console window shows this exactly as
# intended; forwarding every tick into the app's own log as a separate
# line afterward would just be noise (hundreds of near-identical lines
# for one download), so those are filtered out of what gets relayed into
# the app's log/transcript summary specifically - not from the console
# itself, which shows everything live.
_NOISY_PROGRESS_LINE = re.compile(r'^\s*Progress:\s')


def _forward_line(log_callback, prefix, line):
    if log_callback and not _NOISY_PROGRESS_LINE.match(line):
        log_callback(f"{prefix}{line}")


def _read_transcript_file(path):
    """Reads a PowerShell transcript and strips the boilerplate
    header/footer banner lines, leaving just the actual command output."""
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return ""
    skip_exact_prefixes = ('**********************', 'Windows PowerShell transcript')
    skip_stripped_prefixes = (
        'Start time:', 'End time:', 'Username:', 'RunAs User:', 'Configuration Name:',
        'Machine:', 'Host Application:', 'Process ID:', 'PSVersion:', 'PSEdition:',
        'PSCompatibleVersions:', 'BuildVersion:', 'CLRVersion:', 'WSManStackVersion:',
        'PSRemotingProtocolVersion:', 'SerializationVersion:',
    )
    content_lines = []
    for ln in lines:
        if any(ln.startswith(p) for p in skip_exact_prefixes):
            continue
        if any(ln.lstrip().startswith(p) for p in skip_stripped_prefixes):
            continue
        content_lines.append(ln.rstrip('\n'))
    return "\n".join(content_lines).strip()


def _run_in_visible_console(ps_command_line, log_callback=None, transcript_callback=None,
                             timeout=3600, label=""):
    """Runs a PowerShell command line in a new, visible console window -
    the same CREATE_NEW_CONSOLE mechanism used for interactive tweaks/
    scripts - so live progress is directly visible and any unexpected
    prompt can actually be answered, while a parallel transcript still
    feeds the app's own structured log/report. Returns the transcript
    text (boilerplate stripped). Raises BatchInstallUnavailable if this
    isn't Windows, or subprocess.TimeoutExpired if it runs past timeout.

    log_callback gets a couple of concise milestone messages (about to
    open a console, roughly). transcript_callback (falls back to
    log_callback if not given) gets every line of the actual transcript -
    kept separate because the console window already shows all of this
    live; relaying the entire thing into the app's own log a second time
    afterward was pure noise with no new information in it."""
    if sys.platform != 'win32':
        raise BatchInstallUnavailable("Visible-console execution is only supported on Windows")

    detail_callback = transcript_callback if transcript_callback is not None else log_callback

    transcript_path = None
    runner_path = None
    try:
        fd, transcript_path = tempfile.mkstemp(suffix='.log', prefix='dk_batch_transcript_')
        os.close(fd)
        os.unlink(transcript_path)  # Start-Transcript needs to create it itself

        safe_transcript = transcript_path.replace('`', '``').replace('"', '`"')
        runner_ps1 = (
            "$ErrorActionPreference = 'Continue'\n"
            f'try {{ Start-Transcript -Path "{safe_transcript}" -Force | Out-Null }} catch {{ }}\n'
            f"{ps_command_line}\n"
            "try { Stop-Transcript | Out-Null } catch { }\n"
        )
        fd, runner_path = tempfile.mkstemp(suffix='.ps1', prefix='dk_batch_runner_')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(runner_ps1)

        cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', runner_path]
        if log_callback:
            log_callback(f"Opening a console window for {label} - watch it for live progress "
                         f"(and to answer anything unexpected); a result summary appears here "
                         f"once it finishes.")

        process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise

        transcript_text = _read_transcript_file(transcript_path)
        if transcript_text:
            for line in transcript_text.splitlines():
                _forward_line(detail_callback, f"  [{label}] ", line)
        return transcript_text
    finally:
        for p in (runner_path, transcript_path):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def _refresh_path_env():
    """After bootstrapping choco/winget, their install location gets
    added to the system/user PATH by the installer - but this already-
    running process's os.environ won't pick that up on its own (a child
    installer process's env changes don't propagate back to the
    parent). Re-reads PATH from the registry, plus known common install
    locations as a pragmatic fallback, so a freshly-installed tool can
    be found immediately without restarting the app."""
    if sys.platform != 'win32':
        return
    extra_paths = []
    try:
        import winreg
        for hive, subkey in (
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "Path")
                    extra_paths.append(value)
            except OSError:
                continue
    except ImportError:
        pass

    extra_paths.append(r"C:\ProgramData\chocolatey\bin")
    extra_paths.append(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps"))

    current = os.environ.get('PATH', '')
    combined = current.split(os.pathsep) + [p for entry in extra_paths for p in entry.split(os.pathsep) if p]
    seen = set()
    deduped = []
    for p in combined:
        if p and p not in seen:
            seen.add(p)
            deduped.append(p)
    os.environ['PATH'] = os.pathsep.join(deduped)


def attempt_winget_source_reset(log_callback=None, timeout=60) -> bool:
    """Runs the community-documented fix for the winget source-cache bug
    above. Returns True if the reset command itself completed without
    error - that's not a guarantee winget is now fixed, just that we
    successfully attempted the known recovery step, so the caller knows
    whether it's worth retrying."""
    if log_callback:
        log_callback("Detected a known winget source-cache issue - attempting self-heal "
                     "('winget source reset --force') before retrying...")
    try:
        result = subprocess.run(
            ['winget', 'source', 'reset', '--force', '--disable-interactivity'],
            capture_output=True, text=True, timeout=timeout,
        )
        if log_callback:
            for line in (result.stdout or '').splitlines():
                log_callback(f"  [winget source reset] {line}")
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as e:
        if log_callback:
            log_callback(f"  winget source reset itself failed to run: {e}")
        return False


# ---------------------------------------------------------------------
# Bootstrapping - install winget/choco themselves if they're missing
# ---------------------------------------------------------------------

def ensure_choco_installed(log_callback=None, transcript_callback=None, timeout=600) -> bool:
    """Checks for choco and, if missing, runs the official
    chocolatey.org bootstrap script (the same one-liner published in
    their own install docs) in a visible console, so the person can see
    it happen and step in if it needs anything unexpected. Returns True
    if choco is available by the end (whether it was already there or
    this just installed it)."""
    if shutil.which('choco'):
        return True
    if sys.platform != 'win32':
        return False
    if log_callback:
        log_callback("Chocolatey isn't installed - installing it now via the official "
                     "chocolatey.org bootstrap script...")
    ps_line = (
        "Set-ExecutionPolicy Bypass -Scope Process -Force; "
        "[System.Net.ServicePointManager]::SecurityProtocol = "
        "[System.Net.ServicePointManager]::SecurityProtocol -bor 3072; "
        "iex ((New-Object System.Net.WebClient).DownloadString"
        "('https://community.chocolatey.org/install.ps1'))"
    )
    try:
        _run_in_visible_console(ps_line, log_callback=log_callback, transcript_callback=transcript_callback,
                                 timeout=timeout, label="choco-bootstrap")
    except (subprocess.TimeoutExpired, BatchInstallUnavailable) as e:
        if log_callback:
            log_callback(f"Chocolatey install attempt didn't complete cleanly: {e}")
        return False
    _refresh_path_env()
    return shutil.which('choco') is not None


def ensure_winget_installed(log_callback=None, transcript_callback=None, timeout=600) -> bool:
    """Checks for winget and, if missing, attempts to install the App
    Installer package (which provides winget) by downloading the latest
    release directly from Microsoft's official winget-cli GitHub repo
    and installing it via Add-AppxPackage - the standard community-
    documented bootstrap for machines where the Store version isn't
    available. NOTE: on older or heavily locked-down Windows installs
    this can still fail if companion dependency packages
    (Microsoft.VCLibs, Microsoft.UI.Xaml) aren't already present - this
    is a best-effort attempt covering the common case, not a guarantee
    for every machine configuration. Returns True if winget is available
    by the end."""
    if shutil.which('winget'):
        return True
    if sys.platform != 'win32':
        return False
    if log_callback:
        log_callback("winget isn't installed - attempting to install the latest App Installer "
                     "package from Microsoft's official winget-cli GitHub releases...")
    ps_line = (
        "$ProgressPreference = 'SilentlyContinue'; "
        "$asset = (Invoke-RestMethod 'https://api.github.com/repos/microsoft/winget-cli/releases/latest')."
        "assets | Where-Object { $_.name -like '*.msixbundle' } | Select-Object -First 1; "
        "$out = Join-Path $env:TEMP 'AppInstaller.msixbundle'; "
        "Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $out; "
        "Add-AppxPackage -Path $out"
    )
    try:
        _run_in_visible_console(ps_line, log_callback=log_callback, transcript_callback=transcript_callback,
                                 timeout=timeout, label="winget-bootstrap")
    except (subprocess.TimeoutExpired, BatchInstallUnavailable) as e:
        if log_callback:
            log_callback(f"winget install attempt didn't complete cleanly: {e}")
        return False
    _refresh_path_env()
    return shutil.which('winget') is not None


# ---------------------------------------------------------------------
# Winget - chained individual installs in one visible console
# ---------------------------------------------------------------------

def _build_winget_install_statement(pid: str) -> str:
    return (f'winget install --id="{pid}" -e --silent '
            f'--accept-package-agreements --accept-source-agreements --disable-interactivity')


def run_winget_installs_chained(winget_ids, log_callback=None, transcript_callback=None,
                                 timeout=3600, _allow_self_heal=True):
    """Runs `winget install --id=X -e --silent ...` for every id, chained
    with ';' into ONE PowerShell command line, so the whole batch runs in
    a single visible console/process rather than winget_ids separate
    console windows opening and closing - matching what a person doing
    this by hand would type. Returns the transcript text. Raises
    BatchInstallUnavailable if winget isn't present, or WingetBatchFailed
    if it failed at the whole-batch/source level even after one self-heal
    retry - callers should fall back to per-app handling in either case.
    """
    if not shutil.which('winget'):
        raise BatchInstallUnavailable("winget not found on PATH")
    if not winget_ids:
        raise BatchInstallUnavailable("No winget package IDs given")

    ps_line = " ; ".join(_build_winget_install_statement(pid) for pid in winget_ids)
    if log_callback:
        log_callback(f"Batch-installing {len(winget_ids)} app(s) via winget "
                     f"(chained, one console window)...")

    transcript_text = _run_in_visible_console(ps_line, log_callback=log_callback,
                                               transcript_callback=transcript_callback,
                                               timeout=timeout, label="winget")

    if _allow_self_heal and is_winget_source_cache_issue(transcript_text):
        attempt_winget_source_reset(log_callback)
        # Retry exactly once, with self-heal disabled so a repeat
        # failure raises normally instead of looping.
        return run_winget_installs_chained(winget_ids, log_callback=log_callback,
                                            transcript_callback=transcript_callback, timeout=timeout,
                                            _allow_self_heal=False)

    if any(p in transcript_text.lower() for p in _WINGET_FATAL_PATTERNS):
        raise WingetBatchFailed(
            f"winget failed at the source/environment level: {transcript_text.strip()[-300:]} "
            f"(this batch's results can't be trusted)"
        )

    return transcript_text


def verify_winget_installed(winget_ids, max_workers=6, timeout_per_item=30):
    """Lightweight, capped-concurrency verification pass: for each id,
    ask winget whether it's actually installed now. This is what
    actually decides per-app success/failure - the chained-console
    approach above has no single meaningful exit code to key off, and
    even a per-package exit code would be less trustworthy than directly
    confirming presence. Returns {winget_id: bool}."""
    results = {}

    def check_one(pid):
        try:
            r = subprocess.run(
                ['winget', 'list', '--id', pid, '--exact', '--accept-source-agreements',
                 '--disable-interactivity'],
                capture_output=True, text=True, timeout=timeout_per_item,
            )
            # winget list exits 0 and prints the package when found; a
            # "No installed package found" message (or non-zero) means no.
            found = r.returncode == 0 and pid.lower() in r.stdout.lower()
            return pid, found
        except (subprocess.TimeoutExpired, OSError):
            return pid, False

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="winget-verify") as executor:
        for pid, found in executor.map(check_one, winget_ids):
            results[pid] = found
    return results


# ---------------------------------------------------------------------
# Chocolatey
# ---------------------------------------------------------------------

_CHOCO_SUMMARY_RE = re.compile(r'Chocolatey installed (\d+)/(\d+) packages?\.', re.IGNORECASE)

# Choco's own "already installed" warning, printed when its internal
# package ledger (C:\ProgramData\chocolatey\lib\<pkg>) says a package is
# there. That ledger is choco's OWN bookkeeping, separate from Windows'
# real Programs-and-Features state - if the app was removed through a
# channel choco doesn't know about (e.g. uninstalled via Windows Settings
# instead of `choco uninstall`), choco's ledger goes stale: it still
# believes the package is installed and refuses to do anything, even
# though the app is genuinely gone. This pattern is how that gets
# detected so it can be corrected with a forced reinstall rather than
# taken at face value.
_CHOCO_ALREADY_INSTALLED_RE = re.compile(
    r'^(\S+)\s+v?[\d.]+\s+already installed\.?', re.IGNORECASE | re.MULTILINE
)


def find_choco_stale_already_installed(choco_ids, transcript_text):
    """Returns the subset of choco_ids that choco's own transcript
    reported as 'already installed'. Whether that belief is actually
    still true is exactly what the caller should double-check (via a
    forced reinstall + verification) rather than assume."""
    already = set()
    for line in (transcript_text or '').splitlines():
        m = _CHOCO_ALREADY_INSTALLED_RE.match(line.strip())
        if m:
            candidate = m.group(1)
            for pid in choco_ids:
                if pid.lower() == candidate.lower():
                    already.add(pid)
    return already


def set_choco_cache_location(path, log_callback=None, timeout=30) -> bool:
    """Sets choco's global download cache location via the documented
    `choco config set --name cacheLocation --value <path>` command. This
    is ONE shared folder for everything choco downloads - choco has no
    per-package cache-location flag, so a distinct subfolder per app
    (the way winget's own per-installer download works) isn't something
    choco's own mechanism supports; the closest honest equivalent is one
    shared redirected folder for all choco downloads. Returns True if
    the config command itself succeeded."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        if log_callback:
            log_callback(f"Couldn't create choco cache folder {path}: {e}")
        return False
    try:
        result = subprocess.run(
            ['choco', 'config', 'set', '--name', 'cacheLocation', '--value', path],
            capture_output=True, text=True, timeout=timeout,
        )
        if log_callback:
            for line in (result.stdout or '').splitlines():
                log_callback(f"  [choco config] {line}")
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as e:
        if log_callback:
            log_callback(f"Couldn't set choco cache location: {e}")
        return False


def run_choco_install_visible(choco_ids, log_callback=None, transcript_callback=None,
                               timeout=3600, force=False):
    """Runs one `choco install id1 id2 ... -y` (optionally with
    --force) for the whole list, in a visible console window. Returns
    the transcript text. Raises BatchInstallUnavailable if choco isn't
    present - callers should fall back to the per-app loop."""
    if not shutil.which('choco'):
        raise BatchInstallUnavailable("choco not found on PATH")
    if not choco_ids:
        raise BatchInstallUnavailable("No choco package IDs given")

    ps_line = "choco install " + " ".join(choco_ids) + " -y"
    if force:
        ps_line += " --force"
    if log_callback:
        verb = "Force-reinstalling" if force else "Batch-installing"
        log_callback(f"{verb} {len(choco_ids)} app(s) via choco install...")

    return _run_in_visible_console(ps_line, log_callback=log_callback,
                                    transcript_callback=transcript_callback,
                                    timeout=timeout, label="choco")


def parse_choco_batch_output(choco_ids, stdout, returncode=0, expected_count=None):
    """Attributes per-package success/failure from choco's batch output
    (the transcript text, when called from the visible-console path).

    Strategy (most to least confident):
    1. If the "Chocolatey installed X/Y packages." summary line says
       X == Y, and Y is at least expected_count (the number of packages
       we actually asked for), every requested package succeeded - no
       further parsing needed. Y is commonly *larger* than
       expected_count when choco pulls in dependencies alongside what you
       asked for (e.g. asking for "7zip" also installs "7zip.install") -
       that's normal and doesn't make the result untrustworthy.
    2. If X < Y, choco prints a "Failures" section listing the failed
       package names - extract those, treat everything else as success.
    3. If the summary line can't be found, or its total is LOWER than
       expected_count, returns None ("inconclusive") - the caller should
       fall back to verify_choco_installed() rather than guess.

    The "total < expected_count" check matters: a dependency/extension
    crashing before choco even attempts the packages you asked for can
    produce "Chocolatey installed 0/0 packages." - 0 == 0 would trivially
    (and wrongly) satisfy "all succeeded" without this check, silently
    reporting success on a run that installed nothing. But a total
    *higher* than expected_count is just dependencies and must not be
    treated the same way, or a completely normal successful install gets
    needlessly flagged as inconclusive.

    Returns {choco_id: bool} or None if inconclusive.
    """
    m = _CHOCO_SUMMARY_RE.search(stdout or '')
    if not m:
        return None

    succeeded_count, total_count = int(m.group(1)), int(m.group(2))
    if expected_count is not None and total_count < expected_count:
        # Fewer packages attempted than we actually asked for (e.g. a
        # dependency crash aborted the run before reaching our packages
        # at all) - don't trust it, not even X==Y==0.
        return None
    if succeeded_count == total_count:
        return {pid: True for pid in choco_ids}

    # Some failed - find the Failures section and pull out package names.
    failed_ids = set()
    in_failures = False
    for line in (stdout or '').splitlines():
        stripped = line.strip()
        if stripped.lower() == 'failures':
            in_failures = True
            continue
        if in_failures:
            if not stripped:
                break
            # Typical line: " - somepkg (exited 1) - ..."
            fm = re.match(r'-\s*([^\s(]+)', stripped)
            if fm:
                candidate = fm.group(1)
                for pid in choco_ids:
                    if pid.lower() == candidate.lower():
                        failed_ids.add(pid)
                        break

    if not failed_ids:
        # Summary said some failed but we couldn't identify which ones -
        # inconclusive, let the caller verify instead of guessing wrong.
        return None

    return {pid: (pid not in failed_ids) for pid in choco_ids}


def verify_choco_installed(choco_ids, max_workers=6, timeout_per_item=30):
    """Same idea as verify_winget_installed: a cheap local query per
    package, used when output parsing is inconclusive. Returns
    {choco_id: bool}."""
    results = {}

    def check_one(pid):
        try:
            r = subprocess.run(
                ['choco', 'list', '--local-only', pid, '--exact', '-r'],
                capture_output=True, text=True, timeout=timeout_per_item,
            )
            found = r.returncode == 0 and any(
                line.split('|')[0].strip().lower() == pid.lower()
                for line in (r.stdout or '').splitlines() if line.strip()
            )
            return pid, found
        except (subprocess.TimeoutExpired, OSError):
            return pid, False

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="choco-verify") as executor:
        for pid, found in executor.map(check_one, choco_ids):
            results[pid] = found
    return results
