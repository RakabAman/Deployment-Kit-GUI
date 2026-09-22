"""
ScriptEngine - Handles applying and reverting system tweaks.
"""

import os
import subprocess
import logging
import shutil
import tempfile
import datetime
import sys
import threading

class ScriptEngine:
    def __init__(self, config_manager):
        self.config = config_manager
        self.logger = logging.getLogger('DeploymentKit')
        self.tweaks = []

    def load_tweaks(self):
        self.tweaks = self.config.tweaks.get('tweaks', [])

    def _resolve_script_path(self, script_content):
        if os.path.isfile(script_content):
            return script_content
        rel_path = os.path.join(self.config.base_dir, script_content)
        if os.path.isfile(rel_path):
            return rel_path
        return None

    def _build_invoke_line(self, script_path, script_type, arguments):
        """Build the PowerShell line that actually invokes the target script.
        Uses Invoke-Expression so an unquoted $Arguments string still splits
        into separate tokens the same way it did under the old cmd.exe /
        shell=True approach."""
        # Escape backticks/double-quotes for safe embedding inside a
        # double-quoted PowerShell string.
        safe_path = script_path.replace('`', '``').replace('"', '`"')
        args = arguments or ''

        if script_type == 'reg':
            return f'reg import "{safe_path}"'
        elif script_type == 'ps1':
            return f'& "{safe_path}" {args}'.rstrip()
        elif script_type in ('bat', 'cmd'):
            return f'cmd /c ""{safe_path}" {args}"'.rstrip()
        elif script_type == 'py':
            safe_py = sys.executable.replace('`', '``').replace('"', '`"')
            return f'& "{safe_py}" "{safe_path}" {args}'.rstrip()
        else:
            return f'cmd /c ""{safe_path}" {args}"'.rstrip()

    def _run_script(self, script_content, script_type, log_callback=None, tweak_name="Unknown",
                     arguments="", timeout=None, interactive=True):
        """
        interactive=True (the default): runs the target script in a real,
        visible console window so prompts/confirmations the script shows
        still work, which closes on its own when the script finishes and
        which this call properly waits on before returning. Everything
        written to that console is additionally captured via a PowerShell
        transcript, so the deployment log still gets full output/error
        detail even though we never touch stdin/stdout directly (touching
        them would break the interactive prompts). This is the safe
        default because we can't know in advance whether a given tweak or
        script will show a prompt.

        interactive=False: for tweaks/scripts that are known to never need
        a window (most registry-only tweaks, most cleanup scripts). Runs
        hidden with stdout/stderr piped directly, skipping the new-console
        and PowerShell-transcript overhead entirely - faster, and no
        window flash. Only use this when the script is known not to need
        user input; if it does and this path is used, the script will
        appear to hang since there's no window for the user to respond in.

        timeout=None (default) means "wait indefinitely" - this is
        intentional since interactive scripts may be sitting there waiting
        on the user. Pass a number of seconds if you want a hard cap
        (typically paired with interactive=False for a fully automated,
        non-interactive tweak).
        """
        start_time = datetime.datetime.now()
        script_path = self._resolve_script_path(script_content)

        if script_path is None:
            ext_map = {'ps1': '.ps1', 'bat': '.bat', 'cmd': '.cmd', 'py': '.py', 'reg': '.reg'}
            ext = ext_map.get(script_type, '.txt')
            with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as f:
                f.write(script_content)
                script_path = f.name
            is_temp = True
        else:
            is_temp = False

        if sys.platform != 'win32':
            # Non-Windows dev/test fallback: no interactive console concept
            # either way, just run and capture normally.
            return self._run_script_non_windows(script_path, script_type, log_callback,
                                                 tweak_name, arguments, is_temp, start_time)

        if not interactive:
            return self._run_script_hidden_fast(script_path, script_type, log_callback, tweak_name,
                                                 arguments, is_temp, start_time, timeout)

        transcript_path = None
        runner_path = None
        try:
            fd, transcript_path = tempfile.mkstemp(suffix='.log', prefix='dk_transcript_')
            os.close(fd)
            os.unlink(transcript_path)  # Start-Transcript needs to create it itself

            invoke_line = self._build_invoke_line(script_path, script_type, arguments)
            safe_transcript = transcript_path.replace('`', '``').replace('"', '`"')

            runner_ps1 = f'''$ErrorActionPreference = 'Continue'
try {{ Start-Transcript -Path "{safe_transcript}" -Force | Out-Null }} catch {{ }}
$__code = 1
try {{
    {invoke_line}
    if ($LASTEXITCODE -ne $null) {{ $__code = $LASTEXITCODE }} else {{ $__code = 0 }}
}} catch {{
    Write-Host "DEPLOYMENT_KIT_ERROR: $($_.Exception.Message)"
    $__code = 1
}} finally {{
    try {{ Stop-Transcript | Out-Null }} catch {{ }}
}}
exit $__code
'''
            fd, runner_path = tempfile.mkstemp(suffix='.ps1', prefix='dk_runner_')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(runner_ps1)

            cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', runner_path]
            if log_callback:
                log_callback(f"Opening interactive console for {tweak_name}...")

            # CREATE_NEW_CONSOLE = a real, visible window, but as a *direct*
            # child process (unlike the old "cmd /c start /wait" which
            # detached into an unrelated console). Because it's a direct
            # child, process.wait() blocks correctly until the user closes
            # out of / the script finishes in that window, and the window
            # closes itself automatically when the script exits (no manual
            # closing needed) - so sequencing to the next script still works.
            process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)

            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                error_msg = f"Timeout after {timeout} seconds (window force-closed)"
                if log_callback:
                    log_callback(f"⏱️ {tweak_name}: {error_msg}")
                return False, error_msg

            elapsed = (datetime.datetime.now() - start_time).total_seconds()
            transcript_text = self._read_transcript(transcript_path)

            if log_callback and transcript_text:
                for line in transcript_text.splitlines():
                    log_callback(f"  [{tweak_name}] {line}")

            if returncode == 0:
                msg = f"Success (exit 0) in {elapsed:.2f}s"
                if log_callback:
                    log_callback(f"✅ {tweak_name}: {msg}")
                return True, msg
            else:
                tail = "\n".join(transcript_text.splitlines()[-15:]) if transcript_text else "(no transcript captured)"
                error_msg = f"Failed (exit {returncode}) in {elapsed:.2f}s:\n{tail}"
                if log_callback:
                    log_callback(f"❌ {tweak_name}: {error_msg}")
                return False, error_msg

        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            if log_callback:
                log_callback(f"⚠️ {tweak_name}: {error_msg}")
            return False, error_msg
        finally:
            if is_temp and os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
            for p in (runner_path, transcript_path):
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    @staticmethod
    def _read_transcript(path):
        """Read a PowerShell transcript and strip the boilerplate
        header/footer banner lines so the captured log is just the
        script's own output."""
        if not path or not os.path.exists(path):
            return ""
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except OSError:
            return ""
        content_lines = [
            ln.rstrip('\n') for ln in lines
            if not ln.startswith('**********************')
            and not ln.startswith('Windows PowerShell transcript')
            and not ln.lstrip().startswith('Start time:')
            and not ln.lstrip().startswith('End time:')
            and not ln.lstrip().startswith('Username:')
            and not ln.lstrip().startswith('RunAs User:')
            and not ln.lstrip().startswith('Configuration Name:')
            and not ln.lstrip().startswith('Machine:')
            and not ln.lstrip().startswith('Host Application:')
            and not ln.lstrip().startswith('Process ID:')
            and not ln.lstrip().startswith('PSVersion:')
            and not ln.lstrip().startswith('PSEdition:')
            and not ln.lstrip().startswith('PSCompatibleVersions:')
            and not ln.lstrip().startswith('BuildVersion:')
            and not ln.lstrip().startswith('CLRVersion:')
            and not ln.lstrip().startswith('WSManStackVersion:')
            and not ln.lstrip().startswith('PSRemotingProtocolVersion:')
            and not ln.lstrip().startswith('SerializationVersion:')
        ]
        return "\n".join(content_lines).strip()

    def _run_script_hidden_fast(self, script_path, script_type, log_callback, tweak_name,
                                 arguments, is_temp, start_time, timeout):
        """The interactive=False path: no new console window, no PowerShell
        transcript overhead - just run hidden with stdout/stderr piped
        directly. This is the right tool for anything known not to need a
        window (most registry-only tweaks, most cleanup scripts). Only
        called for non-interactive items; if a script that actually needs
        input ends up here it will appear to hang, since there's no window
        for the user to respond in."""
        stdout_lines, stderr_lines = [], []
        try:
            if script_type == 'reg':
                cmd = ['reg', 'import', script_path]
            elif script_type == 'ps1':
                cmd = ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                       '-Command', f"$ErrorActionPreference='Stop'; & \"{script_path}\""
                       + (f" {arguments}" if arguments else "") + "; exit $LASTEXITCODE"]
            elif script_type in ('bat', 'cmd'):
                cmd = ['cmd', '/c', script_path] + (arguments.split() if arguments else [])
            elif script_type == 'py':
                cmd = [sys.executable, script_path] + (arguments.split() if arguments else [])
            else:
                cmd = ['cmd', '/c', script_path] + (arguments.split() if arguments else [])

            if log_callback:
                log_callback(f"Running {tweak_name} (hidden, non-interactive)...")

            process = subprocess.Popen(
                cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW,
            )

            def _drain(pipe, sink, tag):
                for line in iter(pipe.readline, ''):
                    if not line:
                        break
                    line = line.rstrip('\n')
                    sink.append(line)
                    if log_callback:
                        log_callback(f"  [{tag}] {line}")
                pipe.close()

            t_out = threading.Thread(target=_drain, args=(process.stdout, stdout_lines, 'out'), daemon=True)
            t_err = threading.Thread(target=_drain, args=(process.stderr, stderr_lines, 'err'), daemon=True)
            t_out.start()
            t_err.start()

            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                t_out.join(timeout=2)
                t_err.join(timeout=2)
                error_msg = f"Timeout after {timeout} seconds"
                if log_callback:
                    log_callback(f"⏱️ {tweak_name}: {error_msg}")
                return False, error_msg

            t_out.join(timeout=5)
            t_err.join(timeout=5)

            elapsed = (datetime.datetime.now() - start_time).total_seconds()
            tail_err = "\n".join(stderr_lines[-10:])
            tail_out = "\n".join(stdout_lines[-10:])

            if returncode == 0:
                msg = f"Success (exit 0) in {elapsed:.2f}s"
                if tail_out:
                    msg += f"\n{tail_out}"
                if log_callback:
                    log_callback(f"✅ {tweak_name}: {msg}")
                return True, msg
            else:
                detail = tail_err or tail_out or "(no output captured)"
                error_msg = f"Failed (exit {returncode}) in {elapsed:.2f}s:\n{detail}"
                if log_callback:
                    log_callback(f"❌ {tweak_name}: {error_msg}")
                return False, error_msg

        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            if log_callback:
                log_callback(f"⚠️ {tweak_name}: {error_msg}")
            return False, error_msg
        finally:
            if is_temp and os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

    def _run_script_non_windows(self, script_path, script_type, log_callback, tweak_name,
                                 arguments, is_temp, start_time):
        try:
            if script_type == 'reg':
                cmd = f'reg import "{script_path}"'
            elif script_type == 'ps1':
                cmd = f'pwsh -File "{script_path}"'
            elif script_type in ('bat', 'cmd'):
                cmd = f'"{script_path}"'
            elif script_type == 'py':
                cmd = f'"{sys.executable}" "{script_path}"'
            else:
                cmd = f'"{script_path}"'
            if arguments:
                cmd += f" {arguments}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            output = (result.stdout or '') + (result.stderr or '')
            elapsed = (datetime.datetime.now() - start_time).total_seconds()
            if log_callback and output:
                for line in output.splitlines():
                    log_callback(f"  [{tweak_name}] {line}")
            if result.returncode == 0:
                return True, f"Success (exit 0) in {elapsed:.2f}s"
            return False, f"Failed (exit {result.returncode}) in {elapsed:.2f}s:\n{output[-1500:]}"
        except subprocess.TimeoutExpired:
            return False, "Timeout after 300 seconds"
        except Exception as e:
            return False, f"Exception: {str(e)}"
        finally:
            if is_temp and os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

    def apply_tweak(self, tweak, log_callback=None):
        if not tweak.get('enabled', False):
            return False, "Tweak is not enabled"
        if tweak.get('is_builtin', False):
            builtin_type = tweak.get('builtin_type', '')
            if builtin_type == 'custom_scripts':
                return self.install_custom_scripts(log_callback)
            elif builtin_type == 'power_tools':
                return self.install_power_tools(log_callback)
            else:
                return False, f"Unknown built-in type: {builtin_type}"

        script = tweak.get('enable_script', '')
        if not script:
            return False, "No enable script defined"
        script_type = tweak.get('script_type', 'ps1')
        arguments = tweak.get('arguments', '')
        interactive = tweak.get('interactive', True)
        return self._run_script(script, script_type, log_callback, tweak.get('name', 'Unknown'), arguments,
                                 interactive=interactive)

    def revert_tweak(self, tweak, log_callback=None):
        script = tweak.get('disable_script', '')
        if not script:
            return False, "No disable script defined"
        script_type = tweak.get('script_type', 'ps1')
        arguments = tweak.get('arguments', '')
        interactive = tweak.get('interactive', True)
        return self._run_script(script, script_type, log_callback, tweak.get('name', 'Unknown'), arguments,
                                 interactive=interactive)

    def test_script(self, script_content, script_type, log_callback=None, arguments="", interactive=True):
        return self._run_script(script_content, script_type, log_callback, "Test", arguments,
                                 interactive=interactive)

    def apply_all_enabled(self, log_callback=None):
        results = []
        for tweak in self.tweaks:
            if tweak.get('enabled', False):
                success, msg = self.apply_tweak(tweak, log_callback)
                results.append((tweak.get('name', 'Unknown'), success, msg))
        return results

    # ---------- Built-in tweaks ----------
    def install_custom_scripts(self, log_callback=None):
        """Install custom scripts (EcMenu etc.) like the old batch file."""
        base_dir = self.config.base_dir
        src_dir = os.path.join(base_dir, 'Custom_Scripts')
        dest_dir = os.path.join(os.environ.get('SystemDrive', 'C:'), 'Scripts')

        if log_callback:
            log_callback("Installing Custom Scripts...")

        try:
            if os.path.exists(src_dir):
                shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)
                if log_callback:
                    log_callback(f"Copied {src_dir} to {dest_dir}")
            else:
                if log_callback:
                    log_callback(f"Source folder not found: {src_dir}")

            reg_files = ['Ezm_File_Shell.reg', 'Ezm_Folder_Shell.reg']
            for reg in reg_files:
                reg_path = os.path.join(dest_dir, reg)
                if os.path.isfile(reg_path):
                    subprocess.run(['reg', 'import', reg_path], capture_output=True, check=False)
                    if log_callback:
                        log_callback(f"Imported {reg_path}")

            ecmenu_exe = os.path.join(dest_dir, 'tools', 'EcMenu', 'EcMenu_x64.exe')
            if os.path.isfile(ecmenu_exe):
                proc = subprocess.Popen([ecmenu_exe], shell=True)
                import time
                time.sleep(2)
                proc.kill()
                if log_callback:
                    log_callback("Registered EcMenu shell extension")

            lnk_src = os.path.join(dest_dir, 'tools', 'EcMenu', 'EcMenu.lnk')
            lnk_dest = os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'EcMenu.lnk')
            if os.path.isfile(lnk_src):
                shutil.copy2(lnk_src, lnk_dest)
                if log_callback:
                    log_callback("Copied shortcut to Start Menu")

            return True, "Custom Scripts installed successfully"
        except Exception as e:
            return False, str(e)

    def install_power_tools(self, log_callback=None):
        """Extract PowerTools archive to %SystemDrive%\\PowerTools."""
        base_dir = self.config.base_dir
        archive_path = os.path.join(base_dir, 'PowerTools.7z')
        dest_dir = os.path.join(os.environ.get('SystemDrive', 'C:'), 'PowerTools')
        if log_callback:
            log_callback(f"Extracting PowerTools to {dest_dir}...")
        if not os.path.isfile(archive_path):
            return False, f"Archive not found: {archive_path}"
        try:
            import py7zr
            os.makedirs(dest_dir, exist_ok=True)
            with py7zr.SevenZipFile(archive_path, 'r') as archive:
                archive.extractall(dest_dir)
            if log_callback:
                log_callback("PowerTools extracted successfully.")
            return True, "PowerTools installed"
        except ImportError:
            if archive_path.endswith('.zip'):
                import zipfile
                with zipfile.ZipFile(archive_path, 'r') as zipf:
                    zipf.extractall(dest_dir)
                return True, "PowerTools installed (zip)"
            else:
                return False, "py7zr module required for .7z files. Install: pip install py7zr"
        except Exception as e:
            return False, str(e)