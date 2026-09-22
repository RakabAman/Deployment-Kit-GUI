"""
AppCatalog - Manages the application catalog with runtime state.
"""

import os
import json
import subprocess
import threading
import time
import shutil
from modules.config_manager import ConfigManager
from modules.version_cache import VersionCache, DEFAULT_STALE_AFTER_SECONDS

class AppEntry:
    """Represents a single application entry."""
    def __init__(self, data, config_manager, version_cache=None):
        self.config = config_manager
        self.display_name = data.get('display_name', '')
        self.category = data.get('category', '')
        self.offline_path = data.get('offline_path', '')
        self.offline_switch = data.get('offline_switch', '')
        self.offline_version = data.get('offline_version', '')
        self.offline_download_url = data.get('offline_download_url', '')
        self.winget_id = data.get('winget_id', '')
        self.choco_id = data.get('choco_id', '')
        self.install_type = data.get('install_type', 'silent')
        self.tags = data.get('tags', [])
        self.selected_provider = None
        self.is_offline_available = False
        self.post_install_script = data.get('post_install_script', '')
        self.post_install_interactive = data.get('post_install_interactive', True)

        # In-memory cached versions. These used to share one timestamp
        # field between winget and choco, which meant looking up one
        # could make the other appear fresher than it actually was.
        # They're now tracked separately.
        self._winget_version = None
        self._choco_version = None
        self._winget_cache_time = 0
        self._choco_cache_time = 0

        # Shared, disk-persisted cache across sessions/refreshes. AppEntry
        # objects get rebuilt from scratch on every catalog.refresh(), so
        # without this the in-memory cache above was being thrown away
        # constantly and every reload re-scraped winget/choco from zero.
        self._version_cache_store = version_cache
        if version_cache:
            cached = version_cache.get('winget', self.winget_id)
            if cached:
                self._winget_version = cached['version']
                self._winget_cache_time = cached['timestamp']
            cached = version_cache.get('choco', self.choco_id)
            if cached:
                self._choco_version = cached['version']
                self._choco_cache_time = cached['timestamp']

    def to_dict(self):
        return {
            'display_name': self.display_name,
            'category': self.category,
            'offline_path': self.offline_path,
            'offline_switch': self.offline_switch,
            'offline_version': self.offline_version,
            'offline_download_url': self.offline_download_url,
            'winget_id': self.winget_id,
            'choco_id': self.choco_id,
            'install_type': self.install_type,
            'tags': self.tags,
            'post_install_script': self.post_install_script,
        }

    def _cache_winget_result(self, version):
        self._winget_version = version
        self._winget_cache_time = time.time()
        if self._version_cache_store:
            self._version_cache_store.set('winget', self.winget_id, version)
        return version

    def get_winget_version(self, force=False):
        if not self.winget_id:
            return ""
        if not force and self._winget_version and (time.time() - self._winget_cache_time) < 300:
            return self._winget_version
        if not shutil.which('winget'):
            return self._cache_winget_result("Winget not found")

        def extract_version_from_show(stdout):
            for line in stdout.split('\n'):
                if 'Version' in line and ':' in line:
                    version = line.split(':', 1)[1].strip()
                    version = ''.join(c for c in version if c.isprintable())
                    if version:
                        return version
            return None

        # First attempt: winget show
        try:
            cmd = self.config.get_command('winget_version', id=self.winget_id)
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=60
            )
            if result.returncode == 0:
                version = extract_version_from_show(result.stdout)
                if version:
                    return self._cache_winget_result(version)
        except (subprocess.TimeoutExpired, Exception):
            pass

        # Fallback: winget search
        try:
            cmd_search = f"winget search {self.winget_id} --exact"
            result = subprocess.run(
                cmd_search,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=30
            )
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if self.winget_id.lower() in line.lower():
                        parts = line.split()
                        if len(parts) >= 3:
                            version = parts[2].strip()
                            if version:
                                return self._cache_winget_result(version)
        except Exception:
            pass

        return self._cache_winget_result("Not found")

    def _cache_choco_result(self, version):
        self._choco_version = version
        self._choco_cache_time = time.time()
        if self._version_cache_store:
            self._version_cache_store.set('choco', self.choco_id, version)
        return version

    def get_choco_version(self, force=False):
        if not self.choco_id:
            return ""
        if not force and self._choco_version and (time.time() - self._choco_cache_time) < 300:
            return self._choco_version
        if not shutil.which('choco'):
            return self._cache_choco_result("Choco not installed")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                cmd = self.config.get_command('choco_version', package=self.choco_id)
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=60
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if self.choco_id in line:
                            parts = line.split('|')
                            if len(parts) >= 2:
                                version = parts[1].strip()
                                return self._cache_choco_result(version)
                    return self._cache_choco_result("No version found")
                else:
                    error_msg = result.stderr.strip() or result.stdout.strip()
                    # Check if the error suggests a network/retry issue
                    if error_msg and ("try" in error_msg.lower() or "retry" in error_msg.lower()):
                        # Network error – retry if not last attempt
                        if attempt < max_retries - 1:
                            time.sleep(0.5)  # wait 500ms before retry
                            continue
                        else:
                            # Last attempt failed; treat as not found
                            return self._cache_choco_result("Not found")
                    else:
                        # Other error
                        if "not found" in error_msg.lower() or "no such" in error_msg.lower():
                            return self._cache_choco_result("Not found")
                        else:
                            return self._cache_choco_result(
                                f"Error: {error_msg[:30]}" if error_msg else f"Error ({result.returncode})"
                            )
            except subprocess.TimeoutExpired:
                # Timeout: treat as network issue, retry if not last attempt
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                    continue
                else:
                    return self._cache_choco_result("Timeout")
            except FileNotFoundError:
                return self._cache_choco_result("Choco not installed")
            except Exception as e:
                return self._cache_choco_result(f"Error: {str(e)[:30]}")

        # Fallback (should not reach here)
        return self._cache_choco_result("Not found")

    def get_display_version(self, provider):
        if provider == 'offline':
            return self.offline_version or "N/A"
        elif provider == 'winget':
            return self.get_winget_version()
        elif provider == 'choco':
            return self.get_choco_version()
        return ""

    def clear_version_cache(self):
        self._winget_version = None
        self._choco_version = None
        self._winget_cache_time = 0
        self._choco_cache_time = 0
        # Note: this only clears the in-memory value for this instance.
        # It intentionally does not scrub the persistent version_cache
        # entry - the next real fetch will overwrite it anyway, and
        # AppEntry instances get rebuilt (and re-seeded from the
        # persistent cache) on every catalog.refresh().


class AppCatalog:
    def __init__(self, config_manager):
        self.config = config_manager
        self.apps = []
        self._fetching_versions = False
        # Shared across every AppEntry and across catalog.refresh() calls,
        # and persisted to disk - this is what lets version info survive
        # both a tab reload and an app restart instead of resetting to
        # blank every time AppEntry objects get rebuilt below.
        self.version_cache = VersionCache(self.config.base_dir)

    def refresh(self):
        self.apps = []
        data = self.config.apps.get('apps', [])
        for entry_data in data:
            app = AppEntry(entry_data, self.config, version_cache=self.version_cache)
            if app.offline_path:
                full_path = os.path.join(self.config.base_dir, app.offline_path)
                if os.path.isfile(full_path):
                    app.is_offline_available = True
            self.apps.append(app)

    def get_app(self, display_name):
        for app in self.apps:
            if app.display_name == display_name:
                return app
        return None

    def get_apps_by_filter(self, filter_type):
        result = []
        for app in self.apps:
            if filter_type == 'all':
                result.append(app)
            elif filter_type == 'silent' and app.install_type == 'silent':
                result.append(app)
            elif filter_type == 'non_silent' and app.install_type == 'non_silent':
                result.append(app)
            elif filter_type == 'driver' and app.install_type == 'driver':
                result.append(app)
            elif filter_type == 'script' and app.install_type == 'script':
                result.append(app)
            elif filter_type == 'redist' and app.install_type == 'redist':
                result.append(app)
            elif filter_type == 'winget' and app.winget_id:
                result.append(app)
            elif filter_type == 'choco' and app.choco_id:
                result.append(app)
            elif filter_type == 'offline' and app.offline_path:
                result.append(app)
        return result

    def get_installable_for_operation(self, operation):
        commands = []
        if operation == 'silent' or operation == 'non_silent':
            app_type = operation
            for app in self.apps:
                if app.install_type == app_type and app.selected_provider == 'offline':
                    if app.is_offline_available:
                        path = os.path.join(self.config.base_dir, app.offline_path)
                        if app.offline_path.lower().endswith('.msi'):
                            template = self.config.get_command('offline_msi', path=path, switch=app.offline_switch)
                        else:
                            template = self.config.get_command('offline_exe', path=path, switch=app.offline_switch)
                        commands.append({
                            'display_name': app.display_name,
                            'command': template,
                            'is_silent': (operation == 'silent')
                        })
                    else:
                        commands.append({
                            'display_name': app.display_name,
                            'command': None,
                            'is_silent': (operation == 'silent'),
                            'error': 'Offline installer not found'
                        })
        elif operation == 'winget':
            for app in self.apps:
                if app.selected_provider == 'winget' and app.winget_id:
                    cmd = self.config.get_command('winget_install', id=app.winget_id)
                    commands.append({
                        'display_name': app.display_name,
                        'command': cmd,
                        'id': app.winget_id,
                        'is_silent': True
                    })
        elif operation == 'choco':
            # NOTE: this used to check operation == 'chocolatey', but every
            # caller passes 'choco' - the two never matched, so this
            # branch never ran and choco installs silently reported
            # "success, no apps to install" even when choco apps were
            # selected. Fixed to match what's actually passed in.
            for app in self.apps:
                if app.selected_provider == 'choco' and app.choco_id:
                    cmd = self.config.get_command('choco_install', package=app.choco_id)
                    commands.append({
                        'display_name': app.display_name,
                        'command': cmd,
                        'id': app.choco_id,
                        'is_silent': True
                    })
        elif operation == 'drivers':
            for app in self.apps:
                if app.install_type == 'driver' and app.selected_provider == 'offline' and app.is_offline_available:
                    path = os.path.join(self.config.base_dir, app.offline_path)
                    if app.offline_path.lower().endswith('.msi'):
                        cmd = self.config.get_command('offline_msi', path=path, switch=app.offline_switch)
                    else:
                        cmd = self.config.get_command('offline_exe', path=path, switch=app.offline_switch)
                    commands.append({
                        'display_name': app.display_name,
                        'command': cmd,
                        'is_silent': True
                    })
        elif operation == 'scripts':
            for app in self.apps:
                if app.install_type == 'script' and app.selected_provider == 'offline' and app.is_offline_available:
                    path = os.path.join(self.config.base_dir, app.offline_path)
                    commands.append({
                        'display_name': app.display_name,
                        'command': path,
                        'is_silent': True,
                        'is_script': True
                    })
        return commands

    def update_app(self, display_name, new_data):
        for app in self.apps:
            if app.display_name == display_name:
                app.display_name = new_data.get('display_name', app.display_name)
                app.category = new_data.get('category', app.category)
                app.offline_path = new_data.get('offline_path', app.offline_path)
                app.offline_switch = new_data.get('offline_switch', app.offline_switch)
                app.offline_version = new_data.get('offline_version', app.offline_version)
                app.offline_download_url = new_data.get('offline_download_url', app.offline_download_url)
                app.winget_id = new_data.get('winget_id', app.winget_id)
                app.choco_id = new_data.get('choco_id', app.choco_id)
                app.install_type = new_data.get('install_type', app.install_type)
                app.tags = new_data.get('tags', app.tags)
                app.post_install_script = new_data.get('post_install_script', app.post_install_script)
                app.clear_version_cache()
                self._save_apps_to_config()
                return True
        return False

    def add_app(self, app_data):
        new_app = AppEntry(app_data, self.config, version_cache=self.version_cache)
        self.apps.append(new_app)
        self._save_apps_to_config()
        return new_app

    def delete_app(self, display_name):
        for i, app in enumerate(self.apps):
            if app.display_name == display_name:
                del self.apps[i]
                self._save_apps_to_config()
                return True
        return False

    def _save_apps_to_config(self):
        data = {'apps': [app.to_dict() for app in self.apps]}
        self.config.apps = data
        self.config.save_apps()

    def download_offline_installer(self, display_name, progress_callback=None):
        app = self.get_app(display_name)
        if not app:
            return False, "App not found"
        if not app.offline_download_url:
            return False, "No download URL provided"
        if not app.offline_path:
            return False, "No offline path specified"

        import urllib.request
        import shutil
        try:
            full_path = os.path.join(self.config.base_dir, app.offline_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with urllib.request.urlopen(app.offline_download_url) as response:
                total_size = int(response.headers.get('content-length', 0))
                block_size = 8192
                downloaded = 0
                with open(full_path, 'wb') as out_file:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        out_file.write(buffer)
                        downloaded += len(buffer)
                        if progress_callback and total_size > 0:
                            progress_callback(downloaded / total_size * 100)
            app.is_offline_available = True
            return True, "Download successful"
        except Exception as e:
            return False, f"Download failed: {str(e)}"
            