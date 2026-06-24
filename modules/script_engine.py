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

    def _run_script(self, script_content, script_type, log_callback=None, tweak_name="Unknown", arguments=""):
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

        # Wrap the entire execution in a try block so we can use finally
        try:
            if sys.platform == 'win32':
                quoted_script = f'"{script_path}"'
                
                if script_type == 'reg':
                    # Use cmd /c to ensure the window closes after import
                    inner_cmd = f'cmd /c reg import {quoted_script}'
                elif script_type == 'ps1':
                    # PowerShell: use -File, window closes after script finishes
                    inner_cmd = f'powershell -File {quoted_script}'
                elif script_type in ['bat', 'cmd']:
                    # For batch: use cmd /c to close the window after batch exits
                    inner_cmd = f'cmd /c {quoted_script}'
                elif script_type == 'py':
                    inner_cmd = f'"{sys.executable}" {quoted_script}'
                else:
                    inner_cmd = f'cmd /c {quoted_script}'  # fallback

                if arguments:
                    inner_cmd += f" {arguments}"

                # Open a new console and wait for it to close
                cmd = f'cmd /c start /wait "" {inner_cmd}'
                if log_callback:
                    log_callback(f"Opening new console for {tweak_name}: {cmd}")

                process = subprocess.Popen(cmd, shell=True)
                returncode = process.wait()
            else:
                # Non-Windows: run directly
                if script_type == 'reg':
                    cmd = f'reg import "{script_path}"'
                elif script_type == 'ps1':
                    cmd = f'powershell -File "{script_path}"'
                elif script_type in ['bat', 'cmd']:
                    cmd = f'"{script_path}"'
                elif script_type == 'py':
                    cmd = f'"{sys.executable}" "{script_path}"'
                else:
                    cmd = f'"{script_path}"'
                if arguments:
                    cmd += f" {arguments}"
                result = subprocess.run(cmd, shell=True, timeout=300)
                returncode = result.returncode

            elapsed = (datetime.datetime.now() - start_time).total_seconds()
            if returncode == 0:
                msg = f"Success (exit 0) in {elapsed:.2f}s"
                if log_callback:
                    log_callback(f"✅ {tweak_name}: {msg}")
                return True, msg
            else:
                error_msg = f"Failed (exit {returncode}) in {elapsed:.2f}s"
                if log_callback:
                    log_callback(f"❌ {tweak_name}: {error_msg}")
                return False, error_msg

        except subprocess.TimeoutExpired:
            error_msg = "Timeout after 300 seconds"
            if log_callback:
                log_callback(f"⏱️ {tweak_name}: {error_msg}")
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
                except:
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
        return self._run_script(script, script_type, log_callback, tweak.get('name', 'Unknown'), arguments)

    def revert_tweak(self, tweak, log_callback=None):
        script = tweak.get('disable_script', '')
        if not script:
            return False, "No disable script defined"
        script_type = tweak.get('script_type', 'ps1')
        arguments = tweak.get('arguments', '')
        return self._run_script(script, script_type, log_callback, tweak.get('name', 'Unknown'), arguments)

    def test_script(self, script_content, script_type, log_callback=None, arguments=""):
        return self._run_script(script_content, script_type, log_callback, "Test", arguments)

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