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

class AppEntry:
    """Represents a single application entry."""
    def __init__(self, data, config_manager):
        self.config = config_manager  # <-- ADDED
        self.display_name = data.get('display_name', '')
        self.category = data.get('category', '')
        self.offline_path = data.get('offline_path', '')
        self.offline_switch = data.get('offline_switch', '')
        self.offline_version = data.get('offline_version', '')
        self.offline_download_url = data.get('offline_download_url', '')
        self.winget_id = data.get('winget_id', '')
        self.choco_id = data.get('choco_id', '')
        self.install_type = data.get('install_type', 'silent')  # silent, non_silent, driver, script, redist
        self.tags = data.get('tags', [])
        self.selected_provider = None  # 'offline', 'winget', 'choco' - set by GUI
        self.is_offline_available = False  # set after scanning
        self.post_install_script = data.get('post_install_script', '')
        
        # Cached versions
        self._winget_version = None
        self._choco_version = None
        self._version_cache_time = 0

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

    def get_winget_version(self):
        if not self.winget_id:
            return ""
        if self._winget_version and (time.time() - self._version_cache_time) < 300:
            return self._winget_version
        if not shutil.which('winget'):
            self._winget_version = "Winget not found"
            self._version_cache_time = time.time()
            return self._winget_version
        try:
            cmd = self.config.get_command('winget_version', id=self.winget_id)
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Version' in line and ':' in line:
                        version = line.split(':', 1)[1].strip()
                        self._winget_version = version
                        self._version_cache_time = time.time()
                        return version
                self._winget_version = "No version found"
            else:
                self._winget_version = f"Error ({result.returncode})"
            self._version_cache_time = time.time()
            return self._winget_version
        except Exception as e:
            self._winget_version = f"Error: {str(e)[:20]}"
            self._version_cache_time = time.time()
            return self._winget_version

    def get_choco_version(self):
        if not self.choco_id:
            return ""
        if self._choco_version and (time.time() - self._version_cache_time) < 300:
            return self._choco_version
        if not shutil.which('choco'):
            self._choco_version = "Choco not installed"
            self._version_cache_time = time.time()
            return self._choco_version
        try:
            cmd = self.config.get_command('choco_version', package=self.choco_id)
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if self.choco_id in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            version = parts[1].strip()
                            self._choco_version = version
                            self._version_cache_time = time.time()
                            return version
                self._choco_version = "No version found"
            else:
                self._choco_version = f"Error ({result.returncode})"
            self._version_cache_time = time.time()
            return self._choco_version
        except Exception as e:
            self._choco_version = f"Error: {str(e)[:20]}"
            self._version_cache_time = time.time()
            return self._choco_version

    def get_display_version(self, provider):
        """Get version for the selected provider."""
        if provider == 'offline':
            return self.offline_version or "N/A"
        elif provider == 'winget':
            return self.get_winget_version()
        elif provider == 'choco':
            return self.get_choco_version()
        return ""

    def clear_version_cache(self):
        """Clear cached versions."""
        self._winget_version = None
        self._choco_version = None
        self._version_cache_time = 0


class AppCatalog:
    def __init__(self, config_manager):
        self.config = config_manager
        self.apps = []  # list of AppEntry objects
        self._fetching_versions = False

    def refresh(self):
        """Reload app list from config and scan for offline availability."""
        self.apps = []
        data = self.config.apps.get('apps', [])
        for entry_data in data:
            app = AppEntry(entry_data, self.config)  # <-- PASS CONFIG
            if app.offline_path:
                full_path = os.path.join(self.config.base_dir, app.offline_path)
                if os.path.isfile(full_path):
                    app.is_offline_available = True
            self.apps.append(app)

    def get_app(self, display_name):
        """Find app by display name."""
        for app in self.apps:
            if app.display_name == display_name:
                return app
        return None

    def get_apps_by_filter(self, filter_type):
        """
        Return list of apps that match the filter_type:
        'all', 'silent', 'non_silent', 'winget', 'choco', 'offline', 'driver', 'script', 'redist'
        """
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
        """
        Given an operation internal name (e.g., 'silent', 'winget', 'non_silent'),
        return a list of dicts with the actual installation commands based on user radio selection.
        """
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
                        'is_silent': True
                    })
        elif operation == 'chocolatey':
            for app in self.apps:
                if app.selected_provider == 'choco' and app.choco_id:
                    cmd = self.config.get_command('choco_install', package=app.choco_id)
                    commands.append({
                        'display_name': app.display_name,
                        'command': cmd,
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
        """Update an existing app entry in the catalog."""
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
        """Add a new app to the catalog."""
        new_app = AppEntry(app_data, self.config)  # <-- PASS CONFIG
        self.apps.append(new_app)
        self._save_apps_to_config()
        return new_app

    def delete_app(self, display_name):
        """Remove an app from the catalog."""
        for i, app in enumerate(self.apps):
            if app.display_name == display_name:
                del self.apps[i]
                self._save_apps_to_config()
                return True
        return False

    def _save_apps_to_config(self):
        """Write the current apps list back to config and save."""
        data = {'apps': [app.to_dict() for app in self.apps]}
        self.config.apps = data
        self.config.save_apps()

    def download_offline_installer(self, display_name, progress_callback=None):
        """Download the offline installer from the URL."""
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