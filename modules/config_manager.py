"""
ConfigManager - Handles loading and saving of JSON configuration files.
"""

import json
import os
import sys
import shutil

class ConfigManager:
    def __init__(self, base_dir=None):
        if base_dir is None:
            if getattr(sys, 'frozen', False):
                # When frozen, the executable's directory is used for saving
                self.base_dir = os.path.dirname(sys.executable)
                # The bundled data files are extracted to sys._MEIPASS
                self.resource_dir = sys._MEIPASS
            else:
                self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                self.resource_dir = self.base_dir
        else:
            self.base_dir = base_dir
            self.resource_dir = base_dir

        self.settings_file = os.path.join(self.base_dir, 'settings.json')
        self.apps_file = os.path.join(self.base_dir, 'apps.json')
        self.backup_file = os.path.join(self.base_dir, 'backup.json')
        self.tweaks_file = os.path.join(self.base_dir, 'tweaks.json')
        self.activators_file = os.path.join(self.base_dir, 'activators.json')

        self._ensure_defaults()

        self.settings = self._load_json(self.settings_file)
        self.apps = self._load_json(self.apps_file)
        self.backup = self._load_json(self.backup_file)
        self.tweaks = self._load_json(self.tweaks_file)
        self.activators = self._load_json(self.activators_file)

    def _load_json(self, filepath):
        """Try loading from base_dir (user's local files), then from resource_dir (bundled if frozen)."""
        # 1. Try local file
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        # 2. If frozen, try bundled file
        if getattr(sys, 'frozen', False):
            bundled_path = os.path.join(self.resource_dir, os.path.basename(filepath))
            if os.path.exists(bundled_path):
                try:
                    with open(bundled_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    pass
        return {}

    def _ensure_defaults(self):
        """
        Ensures that all JSON configuration files exist in the base_dir.
        If the app is frozen and a bundled file exists in sys._MEIPASS,
        it copies the bundled file to base_dir (user's directory).
        Otherwise, it creates a default configuration.
        """
        config_files = [
            'settings.json',
            'apps.json',
            'backup.json',
            'tweaks.json',
            'activators.json'
        ]

        for filename in config_files:
            local_path = os.path.join(self.base_dir, filename)

            # If local file already exists, skip
            if os.path.exists(local_path):
                continue

            # If frozen, try to copy the bundled file
            if getattr(sys, 'frozen', False):
                bundled_path = os.path.join(self.resource_dir, filename)
                if os.path.exists(bundled_path):
                    try:
                        shutil.copy2(bundled_path, local_path)
                        print(f"Copied bundled {filename} to {local_path}")
                        continue  # Successfully copied, move to next file
                    except Exception as e:
                        print(f"Failed to copy bundled {filename}: {e}")

            # No bundled file or copy failed; create default
            self._create_default_config(filename)

    def _create_default_config(self, filename):
        """Create a default JSON file for the given filename."""
        if filename == 'settings.json':
            default = {
                "general": {
                    "default_provider": "winget",
                    "log_level": "verbose",
                    "backup_destination": "backups",
                    "auto_save": True,
                    "archive_format": "zip"
                },
                "command_templates": {
                    "winget_install": "winget install {id} --silent",
                    "winget_upgrade": "winget upgrade {id} --silent",
                    "winget_list": "winget list {id}",
                    "choco_install": "choco install {package} -y",
                    "choco_upgrade": "choco upgrade {package} -y",
                    "choco_list": "choco list {package} --limit-output",
                    "offline_msi": "msiexec /i \"{path}\" {switch}",
                    "offline_exe": "\"{path}\" {switch}",
                    "winget_version": "winget show {id}",
                    "choco_version": "choco list {package} --limit-output",
                    "tweak_ps1": "powershell -ExecutionPolicy Bypass -File \"{path}\"",
                    "tweak_bat": "\"{path}\"",
                    "tweak_py": "python \"{path}\"",
                    "tweak_reg": "reg import \"{path}\"",
                },
                "available_operations": [
                    {"internal": "silent", "display": "Install Silent Apps", "enabled": True, "description": "Installs apps with silent switches"},
                    {"internal": "winget", "display": "Install Winget Apps", "enabled": True, "description": "Installs apps via Windows Package Manager"},
                    {"internal": "chocolatey", "display": "Install Chocolatey Apps", "enabled": True, "description": "Installs apps via Chocolatey"},
                    {"internal": "non_silent", "display": "Install Non-Silent Apps", "enabled": True, "description": "Installs apps that require manual interaction"},
                    {"internal": "drivers", "display": "Install Drivers", "enabled": True, "description": "Installs driver packages"},
                    {"internal": "restore", "display": "Restore Backup", "enabled": True, "description": "Restores the latest backup zip"},
                    {"internal": "tweaks", "display": "Apply Tweaks", "enabled": True, "description": "Applies all enabled tweaks"},
                    {"internal": "activators", "display": "Run Activators", "enabled": True, "description": "Runs selected activators"},
                    {"internal": "scripts", "display": "Run External Scripts", "enabled": True, "description": "Executes PowerShell/Batch scripts"},
                ]
            }
            filepath = os.path.join(self.base_dir, filename)
            self._save_json(filepath, default)

        elif filename == 'apps.json':
            default = {
                "apps": [
                    {
                        "display_name": "Google Chrome",
                        "category": "Browser",
                        "offline_path": "install\\chrome_installer.exe",
                        "offline_switch": "/silent /install",
                        "offline_download_url": "",
                        "winget_id": "Google.Chrome",
                        "choco_id": "googlechrome",
                        "install_type": "silent",
                        "tags": ["browser", "essential"]
                    },
                    {
                        "display_name": "7-Zip",
                        "category": "Utilities",
                        "offline_path": "install\\7zip.msi",
                        "offline_switch": "/quiet /norestart",
                        "offline_download_url": "",
                        "winget_id": "7zip.7zip",
                        "choco_id": "7zip",
                        "install_type": "silent",
                        "tags": ["archive", "essential"]
                    }
                ]
            }
            filepath = os.path.join(self.base_dir, filename)
            self._save_json(filepath, default)

        elif filename == 'backup.json':
            default = {
                "sources": [
                    "%USERPROFILE%\\Documents",
                    "%USERPROFILE%\\Desktop",
                    "%USERPROFILE%\\Downloads"
                ],
                "destination": "backups"
            }
            filepath = os.path.join(self.base_dir, filename)
            self._save_json(filepath, default)

        elif filename == 'tweaks.json':
            default = {
                "tweaks": [
                    {
                        "name": "Install Custom Scripts (EcMenu)",
                        "category": "Shell Extensions",
                        "description": "Copies Custom Scripts folder, imports registry entries, registers EcMenu shell extension.",
                        "script_type": "ps1",
                        "enable_script": "backup\\custom_scripts\\Custom_scripts_install.ps1",
                        "disable_script": "",
                        "arguments": "",
                        "enabled": False
                    },
                    {
                        "name": "Install Power Tools",
                        "category": "System",
                        "description": "Extracts PowerTools archive to %SystemDrive%\\PowerTools.",
                        "script_type": "ps1",
                        "enable_script": "backup\\powertools\\PowerTools_install.ps1",
                        "disable_script": "",
                        "arguments": "",
                        "enabled": False
                    }
                ]
            }
            filepath = os.path.join(self.base_dir, filename)
            self._save_json(filepath, default)

        elif filename == 'activators.json':
            default = {
                "activators": [
                    {
                        "name": "MAS HWID Activation (Windows)",
                        "category": "Windows",
                        "description": "Permanent HWID activation for Windows 10/11 (MAS)",
                        "executable": "MAS_AIO.cmd",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/HWID-NoEditionChange",
                        "download_url": "https://github.com/massgravel/Microsoft-Activation-Scripts/archive/refs/heads/master.zip",
                        "github_repo": "massgravel/Microsoft-Activation-Scripts",
                        "github_asset_pattern": "*.zip"
                    },
                    {
                        "name": "MAS KMS38 Activation (Windows)",
                        "category": "Windows",
                        "description": "KMS38 activation for Windows 10/11 (valid until 2038)",
                        "executable": "MAS_AIO.cmd",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/KMS38-NoEditionChange",
                        "download_url": "https://github.com/massgravel/Microsoft-Activation-Scripts/archive/refs/heads/master.zip",
                        "github_repo": "massgravel/Microsoft-Activation-Scripts",
                        "github_asset_pattern": "*.zip"
                    },
                    {
                        "name": "MAS Ohook Activation (Office)",
                        "category": "Office",
                        "description": "Permanent Ohook activation for Office (MAS)",
                        "executable": "MAS_AIO.cmd",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/Ohook",
                        "download_url": "https://github.com/massgravel/Microsoft-Activation-Scripts/archive/refs/heads/master.zip",
                        "github_repo": "massgravel/Microsoft-Activation-Scripts",
                        "github_asset_pattern": "*.zip"
                    },
                    {
                        "name": "MAS Online KMS (Windows/Office)",
                        "category": "Windows",
                        "description": "Online KMS activation for Windows/Office (180 days)",
                        "executable": "MAS_AIO.cmd",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/OnlineKMS",
                        "download_url": "https://github.com/massgravel/Microsoft-Activation-Scripts/archive/refs/heads/master.zip",
                        "github_repo": "massgravel/Microsoft-Activation-Scripts",
                        "github_asset_pattern": "*.zip"
                    },
                    {
                        "name": "MAS Renewal (KMS)",
                        "category": "Windows",
                        "description": "Renew KMS activation for Windows/Office",
                        "executable": "MAS_AIO.cmd",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/Renewal",
                        "download_url": "https://github.com/massgravel/Microsoft-Activation-Scripts/archive/refs/heads/master.zip",
                        "github_repo": "massgravel/Microsoft-Activation-Scripts",
                        "github_asset_pattern": "*.zip"
                    },
                    {
                        "name": "KMS_VL_ALL (Windows/Office)",
                        "category": "Windows",
                        "description": "All-in-one KMS activator for Windows and Office (open-source)",
                        "executable": "KMS_VL_ALL.cmd",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/s",
                        "download_url": "https://github.com/abbodi1406/KMS_VL_ALL/archive/refs/heads/master.zip",
                        "github_repo": "abbodi1406/KMS_VL_ALL",
                        "github_asset_pattern": "*.zip"
                    },
                    {
                        "name": "KMS_VL_ALL Office Only",
                        "category": "Office",
                        "description": "KMS_VL_ALL - Office only activation",
                        "executable": "KMS_VL_ALL.cmd",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/s /o",
                        "download_url": "https://github.com/abbodi1406/KMS_VL_ALL/archive/refs/heads/master.zip",
                        "github_repo": "abbodi1406/KMS_VL_ALL",
                        "github_asset_pattern": "*.zip"
                    },
                    {
                        "name": "KMS_VL_ALL Windows Only",
                        "category": "Windows",
                        "description": "KMS_VL_ALL - Windows only activation",
                        "executable": "KMS_VL_ALL.cmd",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/s /w",
                        "download_url": "https://github.com/abbodi1406/KMS_VL_ALL/archive/refs/heads/master.zip",
                        "github_repo": "abbodi1406/KMS_VL_ALL",
                        "github_asset_pattern": "*.zip"
                    },
                    {
                        "name": "KMSpico (Windows/Office)",
                        "category": "Windows",
                        "description": "Popular KMS activator for Windows and Office (GUI)",
                        "executable": "KMSpico.exe",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/silent",
                        "download_url": "",
                        "github_repo": "",
                        "github_asset_pattern": ""
                    },
                    {
                        "name": "Windows Loader (Windows 7)",
                        "category": "Windows",
                        "description": "Classic Windows 7 activation loader (by Daz)",
                        "executable": "WindowsLoader.exe",
                        "folder": "",
                        "archive": "",
                        "default_switches": "/silent",
                        "download_url": "",
                        "github_repo": "",
                        "github_asset_pattern": ""
                    }
                ]
            }
            filepath = os.path.join(self.base_dir, filename)
            self._save_json(filepath, default)

    def _save_json(self, filepath, data):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def save_settings(self):
        self._save_json(self.settings_file, self.settings)

    def save_apps(self):
        self._save_json(self.apps_file, self.apps)

    def save_backup(self):
        self._save_json(self.backup_file, self.backup)

    def save_tweaks(self):
        self._save_json(self.tweaks_file, self.tweaks)

    def save_activators(self):
        self._save_json(self.activators_file, self.activators)

    def get_command(self, template_name, **kwargs):
        templates = self.settings.get('command_templates', {})
        template = templates.get(template_name, '')
        if not template:
            fallbacks = {
                'winget_install': 'winget install {id} --silent',
                'winget_upgrade': 'winget upgrade {id} --silent',
                'winget_list': 'winget list {id}',
                'choco_install': 'choco install {package} -y',
                'choco_upgrade': 'choco upgrade {package} -y',
                'choco_list': 'choco list {package} --limit-output',
                'offline_msi': 'msiexec /i "{path}" {switch}',
                'offline_exe': '"{path}" {switch}',
                'winget_version': 'winget show {id}',
                'choco_version': 'choco list {package} --limit-output',
                'tweak_ps1': 'powershell -ExecutionPolicy Bypass -File "{path}"',
                'tweak_bat': '"{path}"',
                'tweak_py': 'python "{path}"',
                'tweak_reg': 'reg import "{path}"',
            }
            template = fallbacks.get(template_name, '')
        return template.format(**kwargs)

    def get_operations(self):
        return [op for op in self.settings.get('available_operations', []) if op.get('enabled', True)]

    def expand_path(self, path):
        return os.path.expandvars(path)

    def get_archive_format(self):
        """Return 'zip' or '7z' from settings."""
        return self.settings.get('general', {}).get('archive_format', 'zip')