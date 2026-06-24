"""
InstallEngine - Core worker that executes the deployment operations in the background.
"""

import threading
import queue
import subprocess
import time
import os
import logging
from modules.script_runner import ScriptRunner
from modules.script_engine import ScriptEngine

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

    def _log(self, message, level='INFO'):
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
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
                    continue

                stdout_thread.join(timeout=2)
                stderr_thread.join(timeout=2)

                if process.returncode == 0:
                    self._log(f"OK {display} installed successfully", 'INFO')
                    success_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SUCCESS')
                    # --- Run post-install script if any ---
                    app_obj = self.app_catalog.get_app(display)
                    if app_obj:
                        self._run_post_install_script(app_obj)
                else:
                    error_msg = stderr_lines[-1] if stderr_lines else f"Exit code {process.returncode}"
                    self._log(f"FAIL {display} (exit {process.returncode}): {error_msg}", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: FAILED')
            except Exception as e:
                self._log(f"FAIL {display}: {str(e)}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: ERROR')

        if fail_count == 0:
            self._update_status(idx, 'success', f'All {success_count} apps installed')
        elif success_count == 0:
            self._update_status(idx, 'failed', f'All {fail_count} apps failed')
        else:
            self._update_status(idx, 'failed', f'{success_count} installed, {fail_count} failed')

    def _run_online_operation(self, provider, idx):
        self._log(f"Starting {provider} installs...", 'INFO')
        commands = self.app_catalog.get_installable_for_operation(provider)
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
            command = cmd_info['command']
            if not command:
                self._log(f"SKIP {display}: No {provider} ID", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SKIPPED')
                continue
            
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
                
                stderr_lines = []
                
                def read_stderr():
                    for line in iter(process.stderr.readline, ''):
                        if line:
                            stderr_lines.append(line)
                            self._log(f"[{display}] {line.strip()}", 'DEBUG')
                
                stderr_thread = threading.Thread(target=read_stderr, daemon=True)
                stderr_thread.start()
                
                try:
                    process.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    process.kill()
                    self._log(f"FAIL {display}: installation timed out", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: TIMED OUT')
                    continue
                
                stderr_thread.join(timeout=2)
                
                if process.returncode == 0:
                    
                    self._log(f"OK {display} installed successfully", 'INFO')
                    success_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SUCCESS')
                    app_obj = self.app_catalog.get_app(display)
                    if app_obj:
                        self._run_post_install_script(app_obj)                    
                    
                else:
                    error_msg = stderr_lines[-1] if stderr_lines else f"Exit code {process.returncode}"
                    self._log(f"FAIL {display} (exit {process.returncode}): {error_msg}", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: FAILED')
            except Exception as e:
                self._log(f"FAIL {display}: {str(e)}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: ERROR')
        
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
                    continue
                
                if process.returncode == 0:
                    self._log(f"OK {display} driver installed", 'INFO')
                    success_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: SUCCESS')
                else:
                    self._log(f"FAIL {display} driver (exit {process.returncode})", 'ERROR')
                    fail_count += 1
                    self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: FAILED')
            except Exception as e:
                self._log(f"FAIL {display}: {str(e)}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {display}: ERROR')
        
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
                continue

            self._log(f"Running script {name}...", 'INFO')
            self._update_status(idx, 'running', f'[{i+1}/{total}] Running {name}...')

            def log_cb(msg):
                self._log(msg, 'INFO')

            # Use ScriptEngine.test_script which handles both file paths and inline text
            success, msg = engine.test_script(content, script_type, log_cb, arguments='')
            if success:
                self._log(f"OK {name} script succeeded", 'INFO')
                success_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: SUCCESS')
            else:
                self._log(f"FAIL {name}: {msg}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: FAILED')

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
            return
        self._log(f"Restoring from {os.path.basename(backup_path)}...", 'INFO')
        self._log(f"Full restore path: {backup_path}", 'DEBUG')
        success, msg = self.backup_engine.restore_backup(backup_path, sources_to_restore=self.restore_sources)
        if success:
            self._log("Restore completed successfully", 'INFO')
            self._update_status(idx, 'success', 'Restored successfully')
        else:
            self._log(f"Restore failed: {msg}", 'ERROR')
            self._update_status(idx, 'failed', msg)

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
                continue

            script_type = tweak.get('script_type', 'ps1')
            arguments = tweak.get('arguments', '')

            def log_cb(msg):
                self._log(msg, 'INFO')

            self._log(f"▶️ {name}: Running {action} script...", 'INFO')
            self._update_status(idx, 'running', f'[{i+1}/{total}] Running {action} for {name}...')
            success, msg = engine._run_script(script_path, script_type, log_cb, tweak_name=name, arguments=arguments)
            if success:
                self._log(f"✅ {name}: {action} script succeeded", 'INFO')
                success_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: SUCCESS')
            else:
                self._log(f"❌ {name}: {action} script failed: {msg}", 'ERROR')
                fail_count += 1
                self._update_status(idx, 'running', f'[{i+1}/{total}] {name}: FAILED')

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
        success, msg = engine._run_script(abs_path, script_type, log_cb, tweak_name=app.display_name)
        if success:
            self._log(f"Post-install script for {app.display_name} completed successfully.", 'INFO')
        else:
            self._log(f"Post-install script for {app.display_name} failed: {msg}", 'ERROR')            
            
            
