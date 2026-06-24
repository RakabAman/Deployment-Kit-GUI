"""
ActivatorEngine - Handles running activators (like MAS) with user-defined switches.
"""

import os
import subprocess
import logging
import shutil
import zipfile
import tempfile
import json
import urllib.request
import re
import sys

try:
    import py7zr
    HAS_7Z = True
except ImportError:
    HAS_7Z = False

class ActivatorEngine:
    def __init__(self, config_manager):
        self.config = config_manager
        self.logger = logging.getLogger('DeploymentKit')
        self.activators = []

    def load_activators(self):
        self.activators = self.config.activators.get('activators', [])

    def run_activator(self, activator, switch, log_callback=None):
        """Run a single activator with the given switch."""
        exec_path = activator.get('executable', '')
        if not exec_path:
            return False, "No executable defined"

        # Determine work directory
        work_dir = None
        folder_path = activator.get('folder', '')
        archive_name = activator.get('archive', '')

        if folder_path and os.path.isdir(folder_path):
            work_dir = folder_path
        elif archive_name:
            archive_path = os.path.join(self.config.base_dir, 'activators', archive_name)
            if os.path.isfile(archive_path):
                temp_dir = tempfile.mkdtemp()
                if archive_path.endswith('.7z') and HAS_7Z:
                    with py7zr.SevenZipFile(archive_path, 'r') as archive:
                        archive.extractall(temp_dir)
                elif archive_path.endswith('.zip'):
                    with zipfile.ZipFile(archive_path, 'r') as zipf:
                        zipf.extractall(temp_dir)
                work_dir = temp_dir
            else:
                return False, f"Archive not found: {archive_path}"
        else:
            # Assume executable is a full path
            work_dir = os.path.dirname(exec_path)

        # Determine full executable path
        if os.path.isabs(exec_path):
            full_exec = exec_path
        else:
            full_exec = os.path.join(work_dir, exec_path)

        if not os.path.isfile(full_exec):
            return False, f"Executable not found: {full_exec}"

        # Build command
        cmd = [full_exec] + (switch.split() if switch else [])
        if log_callback:
            log_callback(f"Running activator: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except Exception as e:
            return False, str(e)
        finally:
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def run_selected(self, selected_activators, log_callback=None):
        """Run all selected activators (list of (activator, switch))."""
        results = []
        for activator, switch in selected_activators:
            success, msg = self.run_activator(activator, switch, log_callback)
            results.append((activator.get('name', 'Unknown'), success, msg))
        return results

    def download_activator(self, activator, progress_callback=None, log_callback=None):
        """
        Download an activator from its download URL or GitHub repository.
        Returns (success, message, file_path).
        """
        download_url = activator.get('download_url', '')
        github_repo = activator.get('github_repo', '')
        asset_pattern = activator.get('github_asset_pattern', '')

        if not download_url and not github_repo:
            return False, "No download URL or GitHub repository configured", None

        activators_dir = os.path.join(self.config.base_dir, 'activators')
        os.makedirs(activators_dir, exist_ok=True)

        temp_dir = tempfile.mkdtemp()
        try:
            # If we have a GitHub repo, try to get the latest release download URL
            if github_repo and not download_url:
                download_url = self._get_github_release_url(github_repo, asset_pattern, log_callback)
                if not download_url:
                    return False, f"Failed to get download URL for {github_repo}", None

            if log_callback:
                log_callback(f"Downloading from: {download_url}")

            # Determine filename from URL or activator name
            filename = os.path.basename(download_url)
            if not filename or filename == '/':
                filename = f"{activator.get('name', 'activator').replace(' ', '_')}.zip"

            temp_file = os.path.join(temp_dir, filename)

            # Download with progress
            with urllib.request.urlopen(download_url) as response:
                total_size = int(response.headers.get('content-length', 0))
                block_size = 8192
                downloaded = 0
                with open(temp_file, 'wb') as out_file:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        out_file.write(buffer)
                        downloaded += len(buffer)
                        if progress_callback and total_size > 0:
                            progress_callback(downloaded / total_size * 100)
                        elif progress_callback:
                            progress_callback(50)

            if log_callback:
                log_callback(f"Downloaded {filename}")

            # Extract or copy to activators folder
            final_path = None
            if filename.endswith('.zip'):
                with zipfile.ZipFile(temp_file, 'r') as zipf:
                    zipf.extractall(activators_dir)
                final_path = activators_dir
                if log_callback:
                    log_callback(f"Extracted to {activators_dir}")
            elif filename.endswith('.7z') and HAS_7Z:
                with py7zr.SevenZipFile(temp_file, 'r') as archive:
                    archive.extractall(activators_dir)
                final_path = activators_dir
                if log_callback:
                    log_callback(f"Extracted to {activators_dir}")
            else:
                # Single file: copy to activators folder
                dest_file = os.path.join(activators_dir, filename)
                shutil.copy2(temp_file, dest_file)
                final_path = dest_file
                if log_callback:
                    log_callback(f"Copied to {dest_file}")

            return True, "Download successful", final_path

        except Exception as e:
            return False, f"Download failed: {str(e)}", None
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _get_github_release_url(self, repo, asset_pattern, log_callback=None):
        """Get the download URL for the latest GitHub release asset matching the pattern."""
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            with urllib.request.urlopen(api_url) as response:
                data = json.loads(response.read().decode('utf-8'))
                assets = data.get('assets', [])
                
                if not assets:
                    # Try to find the source code zip
                    zip_url = data.get('zipball_url', '')
                    if zip_url:
                        if log_callback:
                            log_callback(f"No assets found, using source code zip")
                        return zip_url
                    return None

                # Find the asset matching the pattern
                for asset in assets:
                    name = asset.get('name', '')
                    if asset_pattern and re.search(asset_pattern.replace('*', '.*'), name):
                        if log_callback:
                            log_callback(f"Found asset: {name}")
                        return asset.get('browser_download_url', '')

                # If no pattern match, return the first asset
                if log_callback:
                    log_callback(f"No asset matching pattern, using: {assets[0].get('name')}")
                return assets[0].get('browser_download_url', '')

        except Exception as e:
            if log_callback:
                log_callback(f"GitHub API error: {str(e)}")
            return None