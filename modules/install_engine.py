"""
InstallEngine - Core worker that executes the deployment operations in the background.
"""

import threading
import queue
import subprocess
import time
import os
import datetime
import logging
from modules.script_runner import ScriptRunner
from modules.script_engine import ScriptEngine
from modules.results import ResultsCollector, STATUS_SUCCESS, STATUS_FAILED, STATUS_SKIPPED
from modules import batch_install

class InstallEngine:
    def __init__(self, app_catalog, backup_engine, config_manager):
        self.app_catalog = app_catalog
        self.backup_engine = backup_engine
        self.config = config_manager
        self.operations = []
        self.status_list = []
        self.current_index = -1
        self.next_index = -1
        self._running = False
        self._cancelled = False
        self._thread = None
        self._log_queue = queue.Queue()
        self.logger = logging.getLogger('DeploymentKit')
        self.selected_activators = []  # list of {'name': '...', 'switches': '...'}
        self.external_scripts = []  # list of script dicts from GUI
        self.restore_sources = None  # list of sources to restore, or None for all
        # One record per individual item (app/tweak/script/activator) for
        # the whole run - status_list above only ever tracked an aggregate
        # count per *operation category*, so a per-item outcome was lost
        # the moment the next item's turn started. This is what feeds the
        # post-run HTML report and "Retry Failed".
        self.results = ResultsCollector()

    def set_external_scripts(self, scripts):
        self.external_scripts = scripts
        
    def set_operations(self, ops_list):
        self.operations = ops_list
        op_display = {
            'silent': 'Install Silent Apps',
            'non_silent': 'Install Non-Silent Apps',
            'winget': 'Install Winget Apps',
            'chocolatey': 'Install Chocolatey Apps',
            'drivers': 'Install Drivers',           
            'restore': 'Restore Backup',
            'tweaks': 'Apply Windows Tweaks',
            'activators': 'Run Activators',
            'scripts': 'Run External Scripts'
        }
        self.status_list = []
        for op in ops_list:
            self.status_list.append({
                'op': op,
                'display': op_display.get(op, op),
                'status': 'pending',
                'message': ''
            })

    def start_deployment(self, on_finished=None):
        if self._running:
            return False
        self._cancelled = False
        self._running = True
        self._thread = threading.Thread(target=self._run_deployment, args=(on_finished,))
        self._thread.daemon = True
        self._thread.start()
        return True

    def cancel(self):
        if self._running:
            self._cancelled = True

    def is_running(self):
        return self._running

    def _new_live_log_path(self):
        """Timestamped path under logs/ for this run's live, append-as-you-go
        structured results (see results.py). Kept alongside the prose
        session log rather than overwriting anything."""
        logs_dir = os.path.join(self.config.base_dir, 'logs')
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
        return os.path.join(logs_dir, f'results_{timestamp}.jsonl')

    def _log(self, message, level='INFO'):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        if level != 'DEBUG':
            # DEBUG-level messages still go to the file log below (for
            # later troubleshooting) and stdout above, just not into the
            # GUI's visible log panel - used for high-volume detail (e.g.
            # a full winget/choco transcript) that's already visible live
            # in its own console window, where relaying it a second time
            # into the app's main log would just be noise.
            self._log_queue.put((message, level))
        if level == 'INFO':
            self.logger.info(message)
        elif level == 'WARNING':
            self.logger.warning(message)
        elif level == 'ERROR':
            self.logger.error(message)
        else:
            self.logger.debug(message)

    def _update_status(self, idx, status, message=''):
        if idx < 0 or idx >= len(self.status_list):
            return
        self.status_list[idx]['status'] = status
        self.status_list[idx]['message'] = message
        status_msg = f"STATUS|{idx}|{status}|{message}"
        self._log_queue.put((status_msg, 'STATUS'))

    def get_logs(self):
        logs = []
        while not self._log_queue.empty():
            logs.append(self._log_queue.get())
        return logs

    def _run_deployment(self, on_finished):
        self.results.reset(live_log_path=self._new_live_log_path())
        try:
            self._log("=== Deployment Started ===", 'INFO')
            self.current_index = 0
            self.next_index = 0
            for i, op in enumerate(self.operations):
                if self._cancelled:
                    self._log("Deployment cancelled by user", 'WARNING')
                    for j in range(i, len(self.operations)):
                        if self.status_list[j]['status'] == 'pending':
                            self._update_status(j, 'skipped', 'Cancelled')
                    break

                self.current_index = i
                self.next_index = i + 1 if i + 1 < len(self.operations) else -1
                self._update_status(i, 'running', 'Starting...')

                if op in ['silent', 'non_silent']:
                    self._run_offline_operation(op, i)
                elif op == 'winget':
                    self._run_online_operation('winget', i)
                elif op == 'chocolatey':
                    self._run_online_operation('choco', i)
                elif op == 'drivers':
                    self._run_drivers(i)
                elif op == 'scripts':
                    self._run_scripts(i)
                elif op == 'restore':
                    self._run_restore(i)
                elif op == 'tweaks':
                    self._run_tweaks(i)
                elif op == 'activators':
                    self._run_activators(i)
                  
                else:
                    self._log(f"Unknown operation: {op}", 'ERROR')
                    self._update_status(i, 'failed', f'Unknown operation: {op}')

                if self.status_list[i]['status'] == 'running':
                    self._update_status(i, 'success', 'Completed')

            self._log("=== Deployment Finished ===", 'INFO')
        except Exception as e:
            self._log(f"Deployment crashed: {str(e)}", 'ERROR')
            if self.current_index >= 0 and self.current_index < len(self.status_list):
                self._update_status(self.current_index, 'failed', str(e))
        finally:
            self._running = False
            self.current_index = -1
            self.next_index = -1
            self.results.mark_finished()
            if on_finished:
                on_finished()

    def _run_offline_operation(self, op_type, idx):
        self._log(f"Starting {op_type} installs...", 'INFO')
        commands = self.app_catalog.get_installable_for_operation(op_type)
        if not commands:
            self._update_status(idx, 'success', 'No apps to install')
            return
        success_count = 0
        fail_count = 0
        total = len(commands)

        for i, cmd_info in enumerate(commands):
            if self._cancelled:
                break
            display = cmd_info['display_name']
            command = cmd_info.get('command')
            if not command:
                error = cmd_info.get('error', 'Unknown error')
                self._log(f"SKIP {display}: {error}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SKIPPED')
                self.results.add('App', display, STATUS_SKIPPED, error, source='Offline installer')
                continue

            self._log(f"Installing {display}...", 'INFO')
            self._update_status(idx, 'running', f'[{i+1}/{total}] Installing {display}...')

            try:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

                stdout_lines = []
                stderr_lines = []

                def read_stdout():
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            stdout_lines.append(line)
                            self._log(f"[{display}] {line.strip()}", 'DEBUG')

                def read_stderr():
                    for line in iter(process.stderr.readline, ''):
                        if line:
                            stderr_lines.append(line)
                            self._log(f"[{display}] {line.strip()}", 'DEBUG')

                stdout_thread = threading.Thread(target=read_stdout, daemon=True)
                stderr_thread = threading.Thread(target=read_stderr, daemon=True)
                stdout_thread.start()
                stderr_thread.start()

                try:
                    process.wait(timeout=3600)
                except subprocess.TimeoutExpired:
                    process.kill()
                    self._log(f"FAIL {display}: installation timed out", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: TIMED OUT')
                    self.results.add('App', display, STATUS_FAILED, "Installation timed out (3600s)",
                                      source='Offline installer',
                                      retry_data={'type': 'app_command', 'display_name': display,
                                                  'command': command, 'timeout': 3600, 'op_type': op_type})
                    continue

                stdout_thread.join(timeout=2)
                stderr_thread.join(timeout=2)

                if process.returncode == 0:
                    self._log(f"OK {display} installed successfully", 'INFO')
                    success_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SUCCESS')
                    self.results.add('App', display, STATUS_SUCCESS, "Installed successfully",
                                      source='Offline installer')
                    # --- Run post-install script if any ---
                    app_obj = self.app_catalog.get_app(display)
                    if app_obj:
                        self._run_post_install_script(app_obj)
                else:
                    error_detail = stderr_lines[-1].strip() if stderr_lines else ""
                    decoded = batch_install.decode_windows_exit_code(process.returncode)
                    error_msg = f"{decoded}" + (f": {error_detail}" if error_detail else "")
                    self._log(f"FAIL {display} ({decoded}): {error_detail}", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: FAILED')
                    self.results.add('App', display, STATUS_FAILED, error_msg,
                                      source='Offline installer',
                                      retry_data={'type': 'app_command', 'display_name': display,
                                                  'command': command, 'timeout': 3600, 'op_type': op_type})
            except Exception as e:
                self._log(f"FAIL {display}: {str(e)}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: ERROR')
                self.results.add('App', display, STATUS_FAILED, f"Exception: {str(e)}",
                                  source='Offline installer',
                                  retry_data={'type': 'app_command', 'display_name': display,
                                              'command': command, 'timeout': 3600, 'op_type': op_type})

        if fail_count == 0:
            self._update_status(idx, 'success', f'All {success_count} apps installed')
        elif success_count == 0:
            self._update_status(idx, 'failed', f'All {fail_count} apps failed')
        else:
            self._update_status(idx, 'failed', f'{success_count} installed, {fail_count} failed')

    def _run_online_operation(self, provider, idx):
        """provider: 'winget' or 'choco'.

        Batches the whole list into one winget/choco invocation instead of
        one process per app (each winget call alone pays ~2-5s of COM
        startup overhead before doing anything, so N apps meant N times
        that cost just spinning up processes). Offline .msi/.exe installs
        are NOT batched - Windows Installer's system-wide mutex means a
        second concurrent msiexec just errors out rather than queuing, and
        there's no batch primitive for arbitrary offline installers anyway
        - those keep running through _run_offline_operation exactly as
        before.

        Per-app success/failure is decided by actually verifying what's
        installed afterward (winget list / choco list --local-only),
        rather than trusting free-text batch progress output alone -
        that's the more reliable way to attribute individual outcomes
        after a shared batch call. If the batch command can't even be
        started (tool missing, unexpected launch failure), this falls
        back automatically to the proven one-app-at-a-time loop so a
        machine where batching doesn't work doesn't lose the ability to
        install at all.
        """
        self._log(f"Starting {provider} installs...", 'INFO')

        if not batch_install.is_elevated():
            self._log(
                f"⚠️ Not running as Administrator - {provider} installs commonly fail without "
                f"elevation (permission errors writing to system folders, UAC prompts on installers "
                f"getting cancelled since there's no elevated context to answer them). If installs "
                f"below fail, that's the first thing to check.", 'WARNING'
            )

        def log_cb(msg):
            self._log(msg, 'INFO')

        def transcript_cb(msg):
            # Full per-line winget/choco transcript detail - already
            # visible live in that command's own console window, so this
            # only goes to the file log (for later troubleshooting), not
            # the GUI's main log panel.
            self._log(msg, 'DEBUG')

        if provider == 'winget':
            if not batch_install.ensure_winget_installed(log_callback=log_cb, transcript_callback=transcript_cb):
                self._log("winget isn't available and couldn't be installed automatically - "
                          "skipping winget installs for this run", 'ERROR')
                self._update_status(idx, 'failed', 'winget not available')
                return
        elif provider == 'choco':
            if not batch_install.ensure_choco_installed(log_callback=log_cb, transcript_callback=transcript_cb):
                self._log("Chocolatey isn't available and couldn't be installed automatically - "
                          "skipping choco installs for this run", 'ERROR')
                self._update_status(idx, 'failed', 'Chocolatey not available')
                return

        commands = self.app_catalog.get_installable_for_operation(provider)
        if not commands:
            self._update_status(idx, 'success', 'No apps to install')
            return

        valid = []
        for i, cmd_info in enumerate(commands):
            if not cmd_info.get('command'):
                display = cmd_info['display_name']
                self._log(f"SKIP {display}: No {provider} ID", 'ERROR')
                self._update_status(idx, 'running', f'{display}: SKIPPED')
                self.results.add('App', display, STATUS_SKIPPED, f"No {provider} ID configured",
                                  source=provider.capitalize())
            else:
                valid.append(cmd_info)

        if not valid:
            self._update_status(idx, 'success', 'No apps to install')
            return

        ids = [c['id'] for c in valid]
        outcome_map = None
        try:
            outcome_map = self._batch_install(provider, ids, log_cb, transcript_cb)
        except (batch_install.BatchInstallUnavailable, batch_install.WingetBatchFailed) as e:
            self._log(f"Batch install unavailable ({e}) - falling back to installing one at a time", 'WARNING')

        if outcome_map is None:
            self._run_online_operation_per_app(provider, idx, valid)
            return

        total = len(valid)
        success_count = 0
        fail_count = 0
        for i, cmd_info in enumerate(valid):
            display = cmd_info['display_name']
            pid = cmd_info['id']
            command = cmd_info['command']
            success, msg = outcome_map.get(pid, (False, "Not verified after batch install"))
            if success:
                success_count += 1
                self._log(f"OK {display} installed successfully (batch)", 'INFO')
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SUCCESS')
                self.results.add('App', display, STATUS_SUCCESS, msg, source=provider.capitalize())
                app_obj = self.app_catalog.get_app(display)
                if app_obj:
                    self._run_post_install_script(app_obj)
            else:
                fail_count += 1
                if batch_install.looks_like_elevation_failure(msg):
                    msg += " (this looks like a missing-Administrator-privileges failure, not a problem with the app itself)"
                self._log(f"FAIL {display}: {msg}", 'ERROR')
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: FAILED')
                self.results.add('App', display, STATUS_FAILED, msg, source=provider.capitalize(),
                                  retry_data={'type': 'app_command', 'display_name': display,
                                              'command': command, 'timeout': 600, 'op_type': provider})

        if fail_count == 0:
            self._update_status(idx, 'success', f'All {success_count} apps installed via {provider}')
        elif success_count == 0:
            self._update_status(idx, 'failed', f'All {fail_count} apps failed via {provider}')
        else:
            self._update_status(idx, 'failed', f'{success_count} succeeded, {fail_count} failed')

    def _diff_install_results(self, ids, before, after, label, transcript_text=""):
        """Turns before/after 'is it installed' snapshots into an honest
        per-package (success, message) map. This exists specifically
        because a plain point-in-time check after the batch command
        can't tell "this run installed it" apart from "it was already
        there before we did anything" - which previously let a
        completely failed batch install get silently credited as a
        success just because the app happened to already be installed
        from earlier testing.

        There's no single reliable exit code to key off here - winget
        runs as several statements chained in one console, and choco's
        wrapping console doesn't propagate its exit code either. The
        visible console itself is the safety net for exact diagnosis;
        this only decides the summary each item gets in the app's log
        and report."""
        result = {}
        elevation_note = ""
        if batch_install.looks_like_elevation_failure(transcript_text) and not batch_install.is_elevated():
            elevation_note = " - likely caused by missing Administrator privileges, not the app itself"
        for pid in ids:
            was_before = before.get(pid, False)
            is_after = after.get(pid, False)
            if is_after and not was_before:
                result[pid] = (True, f"Installed successfully (batch via {label})")
            elif is_after and was_before:
                result[pid] = (True, f"Already installed (verified present after {label} ran - "
                                      f"check the console window if you expected a fresh install)")
            else:
                result[pid] = (False, f"Not installed after {label} ran{elevation_note} - "
                                       f"see the console window output above for the actual error")
        return result

    def _batch_install(self, provider, ids, log_cb, transcript_cb=None):
        """Runs the actual batch command for one provider and returns
        {package_id: (success_bool, message_str)}. Raises
        BatchInstallUnavailable/WingetBatchFailed if the tool couldn't be
        run at all, or failed at a level where none of its output can be
        trusted - callers should fall back to the per-app loop in that
        case, not treat it as a per-app failure.

        Both providers now run in a visible console window (so live
        progress is directly visible and any unexpected prompt can
        actually be answered) with a parallel transcript for our own
        structured log. Per-app attribution uses a before/after "is it
        actually installed" snapshot rather than trusting a single
        point-in-time check or a returncode that no longer exists in a
        meaningful per-app sense once multiple statements run chained in
        one console.
        """
        if provider == 'winget':
            log_cb("Checking current install state before batch install...")
            before = batch_install.verify_winget_installed(ids)
            transcript_text = batch_install.run_winget_installs_chained(
                ids, log_callback=log_cb, transcript_callback=transcript_cb)
            log_cb("Verifying which apps actually installed...")
            after = batch_install.verify_winget_installed(ids)
            return self._diff_install_results(ids, before, after, 'winget', transcript_text=transcript_text)
        elif provider == 'choco':
            log_cb("Checking current install state before batch install...")
            before = batch_install.verify_choco_installed(ids)
            transcript_text = batch_install.run_choco_install_visible(
                ids, log_callback=log_cb, transcript_callback=transcript_cb)

            # Choco's own ledger can go stale if a package was removed
            # through a channel choco doesn't track (e.g. uninstalled via
            # Windows Settings instead of `choco uninstall`) - it then
            # reports "already installed" and refuses to do anything,
            # even though the app is genuinely gone. Force a real
            # reinstall for exactly that subset to correct it, rather
            # than trusting choco's stale belief at face value.
            stale_ids = list(batch_install.find_choco_stale_already_installed(ids, transcript_text))
            forced_transcript = ""
            if stale_ids:
                log_cb(f"Choco reports {len(stale_ids)} package(s) as already in its records - "
                      f"forcing a reinstall to confirm, in case one was actually removed outside "
                      f"choco (e.g. via Windows Settings), which choco's own records wouldn't show...")
                forced_transcript = batch_install.run_choco_install_visible(
                    stale_ids, log_callback=log_cb, transcript_callback=transcript_cb, force=True)

            fresh_ids = [pid for pid in ids if pid not in stale_ids]
            result = {}

            if fresh_ids:
                parsed = batch_install.parse_choco_batch_output(fresh_ids, transcript_text,
                                                                  expected_count=len(fresh_ids))
                if parsed is not None:
                    elevation_note = ""
                    if batch_install.looks_like_elevation_failure(transcript_text) and not batch_install.is_elevated():
                        elevation_note = " - likely caused by missing Administrator privileges"
                    result.update({
                        pid: (ok, "Installed successfully (batch via choco install)" if ok
                              else f"Failed (see console window output above){elevation_note}")
                        for pid, ok in parsed.items()
                    })
                else:
                    after_fresh = batch_install.verify_choco_installed(fresh_ids)
                    result.update(self._diff_install_results(fresh_ids, before, after_fresh, 'choco install',
                                                               transcript_text=transcript_text))

            if stale_ids:
                parsed_forced = batch_install.parse_choco_batch_output(stale_ids, forced_transcript,
                                                                        expected_count=len(stale_ids))
                if parsed_forced is not None:
                    result.update({
                        pid: (ok, "Reinstalled successfully (choco's records said 'already installed', "
                                  "confirmed with a forced reinstall)" if ok
                              else "Force-reinstall failed - see the console window output above")
                        for pid, ok in parsed_forced.items()
                    })
                else:
                    after_forced = batch_install.verify_choco_installed(stale_ids)
                    result.update(self._diff_install_results(stale_ids, before, after_forced,
                                                               'choco install --force',
                                                               transcript_text=forced_transcript))

            return result
        else:
            raise batch_install.BatchInstallUnavailable(f"No batch path defined for provider '{provider}'")

    def _run_online_operation_per_app(self, provider, idx, commands):
        """The original one-app-at-a-time loop, kept as the automatic
        fallback for when batch installation isn't available on this
        machine (tool missing, or the batch call failed to even launch).
        `commands` is the already-filtered list of items that do have a
        command (skips were already recorded by the caller)."""
        success_count = 0
        fail_count = 0
        total = len(commands)

        for i, cmd_info in enumerate(commands):
            if self._cancelled:
                break
            display = cmd_info['display_name']
            command = cmd_info['command']
            if provider == 'winget' and '--disable-interactivity' not in command:
                # Without this, winget can block indefinitely on a prompt
                # it has no way to receive an answer to here (observed in
                # testing: a msstore terms-of-service Y/N prompt that
                # never gets an answer) - append it regardless of what
                # the command template in settings.json says, so this
                # holds even for an existing settings.json saved before
                # this fix.
                command = f"{command} --disable-interactivity"

            self._log(f"Installing {display} via {provider}...", 'INFO')
            self._update_status(idx, 'running', f'[{i+1}/{total}] Installing {display} via {provider}...')

            try:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

                stdout_lines = []
                stderr_lines = []

                def read_stdout():
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            stdout_lines.append(line)
                            self._log(f"[{display}] {line.strip()}", 'DEBUG')

                def read_stderr():
                    for line in iter(process.stderr.readline, ''):
                        if line:
                            stderr_lines.append(line)
                            self._log(f"[{display}] {line.strip()}", 'DEBUG')

                stdout_thread = threading.Thread(target=read_stdout, daemon=True)
                stderr_thread = threading.Thread(target=read_stderr, daemon=True)
                stdout_thread.start()
                stderr_thread.start()

                try:
                    process.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    process.kill()
                    self._log(f"FAIL {display}: installation timed out", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: TIMED OUT')
                    self.results.add('App', display, STATUS_FAILED, "Installation timed out (600s)",
                                      source=provider.capitalize(),
                                      retry_data={'type': 'app_command', 'display_name': display,
                                                  'command': command, 'timeout': 600, 'op_type': provider})
                    continue

                stdout_thread.join(timeout=2)
                stderr_thread.join(timeout=2)

                if process.returncode == 0:

                    self._log(f"OK {display} installed successfully", 'INFO')
                    success_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SUCCESS')
                    self.results.add('App', display, STATUS_SUCCESS, "Installed successfully",
                                      source=provider.capitalize())
                    app_obj = self.app_catalog.get_app(display)
                    if app_obj:
                        self._run_post_install_script(app_obj)

                else:
                    error_detail = stderr_lines[-1].strip() if stderr_lines else (
                        stdout_lines[-1].strip() if stdout_lines else "")
                    decoded = batch_install.decode_windows_exit_code(process.returncode)
                    error_msg = f"{decoded}" + (f": {error_detail}" if error_detail else "")
                    self._log(f"FAIL {display} ({decoded}): {error_detail}", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: FAILED')
                    self.results.add('App', display, STATUS_FAILED, error_msg,
                                      source=provider.capitalize(),
                                      retry_data={'type': 'app_command', 'display_name': display,
                                                  'command': command, 'timeout': 600, 'op_type': provider})
            except Exception as e:
                self._log(f"FAIL {display}: {str(e)}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: ERROR')
                self.results.add('App', display, STATUS_FAILED, f"Exception: {str(e)}",
                                  source=provider.capitalize(),
                                  retry_data={'type': 'app_command', 'display_name': display,
                                              'command': command, 'timeout': 600, 'op_type': provider})
        
        if fail_count == 0:
            self._update_status(idx, 'success', f'All {success_count} apps installed')
        elif success_count == 0:
            self._update_status(idx, 'failed', f'All {fail_count} apps failed')
        else:
            self._update_status(idx, 'failed', f'{success_count} installed, {fail_count} failed')

    def _run_drivers(self, idx):
        self._log("Starting driver installations...", 'INFO')
        commands = self.app_catalog.get_installable_for_operation('drivers')
        if not commands:
            self._update_status(idx, 'success', 'No drivers to install')
            return
        success_count = 0
        fail_count = 0
        total = len(commands)
        
        for i, cmd_info in enumerate(commands):
            if self._cancelled:
                break
            display = cmd_info['display_name']
            command = cmd_info['command']
            if not command:
                self._log(f"SKIP {display}: Driver not available", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SKIPPED')
                self.results.add('Driver', display, STATUS_SKIPPED, "Driver not available")
                continue
            
            self._log(f"Installing driver {display}...", 'INFO')
            self._update_status(idx, 'running', f'[{i+1}/{total}] Installing driver {display}...')
            
            try:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                
                try:
                    process.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    process.kill()
                    self._log(f"FAIL {display}: driver installation timed out", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: TIMED OUT')
                    self.results.add('Driver', display, STATUS_FAILED, "Installation timed out (600s)",
                                      retry_data={'type': 'app_command', 'display_name': display,
                                                  'command': command, 'timeout': 600, 'op_type': 'drivers'})
                    continue
                
                if process.returncode == 0:
                    self._log(f"OK {display} driver installed", 'INFO')
                    success_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SUCCESS')
                    self.results.add('Driver', display, STATUS_SUCCESS, "Installed successfully")
                else:
                    decoded = batch_install.decode_windows_exit_code(process.returncode)
                    self._log(f"FAIL {display} driver ({decoded})", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: FAILED')
                    self.results.add('Driver', display, STATUS_FAILED, decoded,
                                      retry_data={'type': 'app_command', 'display_name': display,
                                                  'command': command, 'timeout': 600, 'op_type': 'drivers'})
            except Exception as e:
                self._log(f"FAIL {display}: {str(e)}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: ERROR')
                self.results.add('Driver', display, STATUS_FAILED, f"Exception: {str(e)}",
                                  retry_data={'type': 'app_command', 'display_name': display,
                                              'command': command, 'timeout': 600, 'op_type': 'drivers'})
        
        if fail_count == 0:
            self._update_status(idx, 'success', f'All {success_count} drivers installed')
        elif success_count == 0:
            self._update_status(idx, 'failed', f'All {fail_count} drivers failed')
        else:
            self._update_status(idx, 'failed', f'{success_count} installed, {fail_count} failed')

    def _run_scripts(self, idx):
        """Run both catalog scripts and temporary external scripts."""
        self._log("Running scripts...", 'INFO')

        # --- Collect all script items ---
        script_items = []

        # 1. Catalog scripts (from apps.json)
        catalog_commands = self.app_catalog.get_installable_for_operation('scripts')
        for cmd_info in catalog_commands:
            script_items.append({
                'name': cmd_info['display_name'],
                'type': 'auto',          # will be auto-detected by ScriptEngine
                'content': cmd_info['command'],
                'source': 'catalog',
                'description': cmd_info.get('description', '')
            })

        # 2. Temporary external scripts (from GUI)
        for script in self.external_scripts:
            script_items.append({
                'name': script.get('name', 'Unnamed'),
                'type': script.get('type', 'ps1'),
                'content': script.get('content', ''),
                'source': 'external',
                'description': script.get('description', '')
            })

        if not script_items:
            self._update_status(idx, 'success', 'No scripts to run')
            return

        total = len(script_items)
        success_count = 0
        fail_count = 0

        from modules.script_engine import ScriptEngine
        engine = ScriptEngine(self.config)

        for i, item in enumerate(script_items):
            if self._cancelled:
                break
            name = item['name']
            script_type = item['type']
            content = item['content']
            source = item['source']

            if not content:
                self._log(f"SKIP {name}: empty content", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: SKIPPED')
                self.results.add('Script', name, STATUS_SKIPPED, "Empty script content", source=source)
                continue

            self._log(f"Running script {name}...", 'INFO')
            self._update_status(idx, 'running', f'[{i+1}/{total}] Running {name}...')

            def log_cb(msg):
                self._log(msg, 'INFO')

            # Use ScriptEngine.test_script which handles both file paths and inline text
            success, msg = engine.test_script(content, script_type, log_cb, arguments='',
                                               interactive=item.get('interactive', True))
            if success:
                self._log(f"OK {name} script succeeded", 'INFO')
                success_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: SUCCESS')
                self.results.add('Script', name, STATUS_SUCCESS, msg, source=source)
            else:
                self._log(f"FAIL {name}: {msg}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: FAILED')
                self.results.add('Script', name, STATUS_FAILED, msg, source=source,
                                  retry_data={'type': 'script_item', 'item': item})

        if fail_count == 0:
            self._update_status(idx, 'success', f'All {success_count} scripts succeeded')
        elif success_count == 0:
            self._update_status(idx, 'failed', f'All {fail_count} scripts failed')
        else:
            self._update_status(idx, 'failed', f'{success_count} succeeded, {fail_count} failed')

    def _run_restore(self, idx):
        self._log("Starting restore...", 'INFO')
        self._log("Looking for backup to restore...", 'DEBUG')
        backup_path = self.backup_engine.get_selected_or_latest()
        self._log(f"get_selected_or_latest() returned: {backup_path}", 'DEBUG')
        if not backup_path:
            self._log("No backup found to restore", 'WARNING')
            self._update_status(idx, 'failed', 'No backup found')
            self.results.add('Backup Restore', 'Restore from backup', STATUS_FAILED, "No backup found")
            return
        self._log(f"Restoring from {os.path.basename(backup_path)}...", 'INFO')
        self._log(f"Full restore path: {backup_path}", 'DEBUG')
        success, msg = self.backup_engine.restore_backup(backup_path, sources_to_restore=self.restore_sources)
        if success:
            self._log("Restore completed successfully", 'INFO')
            self._update_status(idx, 'success', 'Restored successfully')
            self.results.add('Backup Restore', f'Restore from {os.path.basename(backup_path)}',
                              STATUS_SUCCESS, msg or "Restored successfully", source=backup_path)
        else:
            self._log(f"Restore failed: {msg}", 'ERROR')
            self._update_status(idx, 'failed', msg)
            self.results.add('Backup Restore', f'Restore from {os.path.basename(backup_path)}',
                              STATUS_FAILED, msg, source=backup_path,
                              retry_data={'type': 'restore', 'backup_path': backup_path,
                                          'sources_to_restore': self.restore_sources})

    def _run_tweaks(self, idx):
        """Apply selected tweak actions (enable/disable) based on GUI selections."""
        self._log("Applying selected tweak actions...", 'INFO')
        from modules.script_engine import ScriptEngine
        engine = ScriptEngine(self.config)
        engine.load_tweaks()

        tweaks = self.config.tweaks.get('tweaks', [])
        if not tweaks:
            self._update_status(idx, 'success', 'No tweaks configured')
            return

        # Filter tweaks that have a selected action
        selected_tweaks = [t for t in tweaks if t.get('selected_action')]
        if not selected_tweaks:
            self._log("No tweaks selected. Nothing to apply.", 'INFO')
            self._update_status(idx, 'success', 'No tweaks selected')
            return

        total = len(selected_tweaks)
        success_count = 0
        fail_count = 0

        for i, tweak in enumerate(selected_tweaks):
            if self._cancelled:
                break
            name = tweak.get('name', 'Unnamed')
            action = tweak.get('selected_action')
            script_path = tweak.get(f'{action}_script', '')
            if not script_path:
                self._log(f"⚠️ {name}: No {action} script defined (skipped)", 'WARNING')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: SKIPPED (no script)')
                self.results.add('Tweak', name, STATUS_SKIPPED, f"No {action} script defined",
                                  source=f"{action} script")
                continue

            script_type = tweak.get('script_type', 'ps1')
            arguments = tweak.get('arguments', '')

            def log_cb(msg):
                self._log(msg, 'INFO')

            self._log(f"▶️ {name}: Running {action} script...", 'INFO')
            self._update_status(idx, 'running', f'[{i+1}/{total}] Running {action} for {name}...')
            success, msg = engine._run_script(script_path, script_type, log_cb, tweak_name=name, arguments=arguments,
                                               interactive=tweak.get('interactive', True))
            if success:
                self._log(f"✅ {name}: {action} script succeeded", 'INFO')
                success_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: SUCCESS')
                self.results.add('Tweak', name, STATUS_SUCCESS, msg, source=f"{action} script")
            else:
                self._log(f"❌ {name}: {action} script failed: {msg}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: FAILED')
                self.results.add('Tweak', name, STATUS_FAILED, msg, source=f"{action} script",
                                  retry_data={'type': 'tweak', 'tweak': tweak})

        # Final status
        if fail_count == 0:
            self._update_status(idx, 'success', f'All {success_count} tweaks applied')
        elif success_count == 0:
            self._update_status(idx, 'failed', f'All {fail_count} tweaks failed')
        else:
            self._update_status(idx, 'failed', f'{success_count} applied, {fail_count} failed')
        self._log(f"Tweak actions completed: {success_count} succeeded, {fail_count} failed.", 'INFO')
        
    def set_selected_activators(self, selected_list):
        self.selected_activators = selected_list

    def _run_activators(self, idx):
        self._log("Running activators...", 'INFO')
        from modules.activator_engine import ActivatorEngine
        engine = ActivatorEngine(self.config)
        engine.load_activators()

        if self.selected_activators:
            selected = []
            for sel in self.selected_activators:
                name = sel.get('name')
                switches = sel.get('switches')
                activator = None
                for a in engine.activators:
                    if a.get('name') == name:
                        activator = a
                        break
                if activator:
                    selected.append((activator, switches))
        else:
            # fallback: run all with default switches
            selected = [(act, act.get('default_switches', '')) for act in engine.activators]

        if not selected:
            self._update_status(idx, 'failed', 'No activators to run')
            return

        def log_cb(msg):
            self._log(msg, 'INFO')
        self._update_status(idx, 'running', 'Running activators...')
        results = engine.run_selected(selected, log_cb)
        success_count = sum(1 for _, s, _ in results if s)
        fail_count = len(results) - success_count

        # results here is [(name, success, msg), ...] in the same order as
        # `selected` ([(activator_dict, switch), ...]), so zip them to keep
        # the switch/activator dict for retry.
        for (activator, switch), (name, success, msg) in zip(selected, results):
            if success:
                self.results.add('Activator', name, STATUS_SUCCESS, msg)
            else:
                self.results.add('Activator', name, STATUS_FAILED, msg,
                                  retry_data={'type': 'activator', 'activator': activator, 'switch': switch})

        if fail_count == 0:
            self._update_status(idx, 'success', f'All {success_count} activators succeeded')
        elif success_count == 0:
            self._update_status(idx, 'failed', f'All {fail_count} activators failed')
        else:
            self._update_status(idx, 'failed', f'{success_count} succeeded, {fail_count} failed')
            
    def _run_post_install_script(self, app, log_callback=None):
        """Run the post-install script for an app if defined."""
        script_path = app.post_install_script
        if not script_path:
            return
        # Resolve absolute path
        abs_path = os.path.join(self.config.base_dir, script_path)
        if not os.path.isfile(abs_path):
            self._log(f"Post-install script not found: {abs_path}", 'WARNING')
            return

        # Determine script type from extension
        ext = os.path.splitext(script_path)[1].lower()
        ext_map = {'.ps1': 'ps1', '.bat': 'bat', '.cmd': 'bat', '.py': 'py', '.reg': 'reg'}
        script_type = ext_map.get(ext, 'bat')
        engine = ScriptEngine(self.config)
        # We'll use the same interactive logic as tweaks.
        # But we need a log callback that uses self._log.
        def log_cb(msg):
            self._log(msg, 'INFO')
        log_cb(f"Running post-install script for {app.display_name}: {abs_path}")
        success, msg = engine._run_script(abs_path, script_type, log_cb, tweak_name=app.display_name,
                                           interactive=getattr(app, 'post_install_interactive', True))
        if success:
            self._log(f"Post-install script for {app.display_name} completed successfully.", 'INFO')
            self.results.add('Post-Install Script', f"{app.display_name} post-install", STATUS_SUCCESS,
                              msg, source=abs_path)
        else:
            self._log(f"Post-install script for {app.display_name} failed: {msg}", 'ERROR')
            self.results.add('Post-Install Script', f"{app.display_name} post-install", STATUS_FAILED,
                              msg, source=abs_path,
                              retry_data={'type': 'post_install_script', 'app_display_name': app.display_name,
                                          'script_path': abs_path, 'script_type': script_type,
                                          'interactive': getattr(app, 'post_install_interactive', True)})

    # ------------------------------------------------------------------
    # Retry Failed - replays individual ResultItems that carry retry_data,
    # without re-running the entire deployment. Each retry_data['type']
    # maps to one of the small helpers below, which mirror the exact
    # execution logic used the first time (same command, same engine
    # calls) so a retry is a faithful re-attempt, not an approximation.
    #
    # New outcomes are appended to self.results rather than replacing the
    # original failed entry - if a retry succeeds, the report/log will
    # show both the original failure and the successful retry, which is
    # useful audit trail for "what actually happened on this machine."
    # ------------------------------------------------------------------

    def start_retry(self, items, on_finished=None):
        """items: a list of ResultItem (typically from
        self.results.failed_items() or a loaded report) that have
        retry_data set. Returns False without doing anything if a
        deployment/retry is already running, or if none of the given
        items are actually retryable."""
        if self._running:
            return False
        retryable = [i for i in items if i.is_retryable]
        if not retryable:
            return False
        self._cancelled = False
        self._running = True
        self._thread = threading.Thread(target=self._run_retry, args=(retryable, on_finished))
        self._thread.daemon = True
        self._thread.start()
        return True

    def _run_retry(self, items, on_finished):
        self.results.resume_live_log()
        try:
            self._log(f"=== Retrying {len(items)} failed item(s) ===", 'INFO')
            for i, item in enumerate(items):
                if self._cancelled:
                    self._log("Retry cancelled by user", 'WARNING')
                    break
                self.current_index = i
                self._retry_single_item(item)
            self._log("=== Retry Finished ===", 'INFO')
        except Exception as e:
            self._log(f"Retry crashed: {str(e)}", 'ERROR')
        finally:
            self._running = False
            self.current_index = -1
            self.results.mark_finished()
            if on_finished:
                on_finished()

    def _retry_single_item(self, item):
        rd = item.retry_data or {}
        rtype = rd.get('type')
        try:
            handler = {
                'app_command': self._retry_app_command,
                'tweak': self._retry_tweak,
                'script_item': self._retry_script_item,
                'activator': self._retry_activator,
                'post_install_script': self._retry_post_install_script,
                'restore': self._retry_restore,
            }.get(rtype)
            if handler is None:
                self._log(f"Cannot retry '{item.name}': unknown retry type '{rtype}'", 'ERROR')
                self.results.add(item.category, item.name, STATUS_FAILED,
                                  "Retry not supported for this item type", source=item.source)
                return
            handler(rd)
        except Exception as e:
            self._log(f"Retry of {item.name} crashed: {str(e)}", 'ERROR')
            self.results.add(item.category, item.name, STATUS_FAILED, f"Retry exception: {str(e)}",
                              source=item.source)

    def _retry_app_command(self, rd):
        display = rd['display_name']
        command = rd['command']
        timeout = rd.get('timeout', 600)
        op_type = rd.get('op_type', 'app')
        source_label = {
            'silent': 'Offline installer', 'non_silent': 'Offline installer',
            'winget': 'Winget', 'choco': 'Choco', 'drivers': 'Driver',
        }.get(op_type, op_type)
        category = 'Driver' if op_type == 'drivers' else 'App'

        self._log(f"Retrying {display}...", 'INFO')
        try:
            process = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
            stderr_lines = []

            def read_stderr():
                for line in iter(process.stderr.readline, ''):
                    if line:
                        stderr_lines.append(line)
                        self._log(f"[{display}] {line.strip()}", 'DEBUG')

            t = threading.Thread(target=read_stderr, daemon=True)
            t.start()

            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                self._log(f"RETRY FAIL {display}: timed out", 'ERROR')
                self.results.add(category, display, STATUS_FAILED, f"Retry timed out ({timeout}s)",
                                  source=source_label, retry_data=rd)
                return

            t.join(timeout=2)

            if process.returncode == 0:
                self._log(f"RETRY OK {display}", 'INFO')
                self.results.add(category, display, STATUS_SUCCESS, "Installed successfully (retry)",
                                  source=source_label)
                if category == 'App':
                    app_obj = self.app_catalog.get_app(display)
                    if app_obj:
                        self._run_post_install_script(app_obj)
            else:
                error_detail = stderr_lines[-1].strip() if stderr_lines else ""
                decoded = batch_install.decode_windows_exit_code(process.returncode)
                error_msg = f"{decoded}" + (f": {error_detail}" if error_detail else "")
                self._log(f"RETRY FAIL {display}: {error_msg}", 'ERROR')
                self.results.add(category, display, STATUS_FAILED, error_msg,
                                  source=source_label, retry_data=rd)
        except Exception as e:
            self._log(f"RETRY FAIL {display}: {str(e)}", 'ERROR')
            self.results.add(category, display, STATUS_FAILED, f"Exception: {str(e)}",
                              source=source_label, retry_data=rd)

    def _retry_tweak(self, rd):
        tweak = rd['tweak']
        name = tweak.get('name', 'Unnamed')
        action = tweak.get('selected_action')
        script_path = tweak.get(f'{action}_script', '')
        script_type = tweak.get('script_type', 'ps1')
        arguments = tweak.get('arguments', '')
        engine = ScriptEngine(self.config)

        def log_cb(msg):
            self._log(msg, 'INFO')

        self._log(f"Retrying tweak {name}...", 'INFO')
        success, msg = engine._run_script(script_path, script_type, log_cb, tweak_name=name, arguments=arguments,
                                           interactive=tweak.get('interactive', True))
        if success:
            self.results.add('Tweak', name, STATUS_SUCCESS, msg, source=f"{action} script")
        else:
            self.results.add('Tweak', name, STATUS_FAILED, msg, source=f"{action} script", retry_data=rd)

    def _retry_script_item(self, rd):
        item = rd['item']
        name = item['name']
        script_type = item['type']
        content = item['content']
        source = item['source']
        engine = ScriptEngine(self.config)

        def log_cb(msg):
            self._log(msg, 'INFO')

        self._log(f"Retrying script {name}...", 'INFO')
        success, msg = engine.test_script(content, script_type, log_cb, arguments='',
                                           interactive=item.get('interactive', True))
        if success:
            self.results.add('Script', name, STATUS_SUCCESS, msg, source=source)
        else:
            self.results.add('Script', name, STATUS_FAILED, msg, source=source, retry_data=rd)

    def _retry_activator(self, rd):
        activator = rd['activator']
        switch = rd.get('switch', '')
        name = activator.get('name', 'Unknown')
        from modules.activator_engine import ActivatorEngine
        engine = ActivatorEngine(self.config)

        def log_cb(msg):
            self._log(msg, 'INFO')

        self._log(f"Retrying activator {name}...", 'INFO')
        success, msg = engine.run_activator(activator, switch, log_cb)
        if success:
            self.results.add('Activator', name, STATUS_SUCCESS, msg)
        else:
            self.results.add('Activator', name, STATUS_FAILED, msg, retry_data=rd)

    def _retry_post_install_script(self, rd):
        app_display_name = rd['app_display_name']
        script_path = rd['script_path']
        script_type = rd.get('script_type', 'bat')
        engine = ScriptEngine(self.config)

        def log_cb(msg):
            self._log(msg, 'INFO')

        self._log(f"Retrying post-install script for {app_display_name}...", 'INFO')
        success, msg = engine._run_script(script_path, script_type, log_cb, tweak_name=app_display_name,
                                           interactive=rd.get('interactive', True))
        if success:
            self.results.add('Post-Install Script', f"{app_display_name} post-install", STATUS_SUCCESS,
                              msg, source=script_path)
        else:
            self.results.add('Post-Install Script', f"{app_display_name} post-install", STATUS_FAILED,
                              msg, source=script_path, retry_data=rd)

    def _retry_restore(self, rd):
        backup_path = rd['backup_path']
        sources_to_restore = rd.get('sources_to_restore')
        name = f'Restore from {os.path.basename(backup_path)}'
        self._log(f"Retrying restore from {os.path.basename(backup_path)}...", 'INFO')
        success, msg = self.backup_engine.restore_backup(backup_path, sources_to_restore=sources_to_restore)
        if success:
            self.results.add('Backup Restore', name, STATUS_SUCCESS, msg or "Restored successfully",
                              source=backup_path)
        else:
            self.results.add('Backup Restore', name, STATUS_FAILED, msg, source=backup_path, retry_data=rd)
            
            
