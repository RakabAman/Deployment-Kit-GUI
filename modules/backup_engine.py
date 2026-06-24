"""
BackupEngine - Handles backup and restore of user folders using zip or 7z archives.
"""

import os
import zipfile
import shutil
import datetime
import logging
import subprocess
import sys

# For 7z support, we try to import py7zr (optional dependency)
try:
    import py7zr
    HAS_7Z = True
except ImportError:
    HAS_7Z = False

class BackupEngine:
    def __init__(self, config_manager):
        self.config = config_manager
        self.backup_data = self.config.backup
        self.sources = self.backup_data.get('sources', [])
        self.destination_dir = self.backup_data.get('destination', 'backups')
        self.destination_dir = self.config.expand_path(self.destination_dir)
        if not os.path.isabs(self.destination_dir):
            self.destination_dir = os.path.join(self.config.base_dir, self.destination_dir)

        self.selected_backup_path = None   # full path to the currently selected backup
        self.archive_format = self.config.get_archive_format()  # 'zip' or '7z'

        logger = logging.getLogger('DeploymentKit')
        logger.debug(f"BackupEngine initialized with destination: {self.destination_dir}")
        logger.debug(f"Archive format: {self.archive_format}")

    def get_backup_list(self):
        """
        Return a list of tuples (filename, date_time, size_mb) sorted by date (newest first).
        Only returns files in the root of the destination directory.
        """
        if not os.path.exists(self.destination_dir):
            return []
        files = []
        for f in os.listdir(self.destination_dir):
            full_path = os.path.join(self.destination_dir, f)
            if os.path.isfile(full_path) and (f.endswith('.zip') or f.endswith('.7z')):
                mtime = os.path.getmtime(full_path)
                size_bytes = os.path.getsize(full_path)
                size_mb = round(size_bytes / (1024 * 1024), 1)
                date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                files.append((f, date_str, size_mb, mtime))
        # Sort by mtime descending (newest first)
        files.sort(key=lambda x: x[3], reverse=True)
        # Return without the mtime
        return [(f, d, s) for f, d, s, _ in files]

    def get_latest_backup(self):
        """Return the full path of the latest backup in the root, or None."""
        files = self.get_backup_list()
        if files:
            return os.path.join(self.destination_dir, files[0][0])
        return None

    def set_selected_by_filename(self, filename):
        """
        Set the selected backup by filename (e.g., 'backup_20260619_123456.zip').
        Also accepts full path.
        """
        logger = logging.getLogger('DeploymentKit')
        if not filename:
            self.selected_backup_path = None
            logger.debug("Selected backup cleared")
            return

        # If it's already a full path, use it directly
        if os.path.isfile(filename):
            self.selected_backup_path = filename
            logger.debug(f"Selected backup set to full path: {filename}")
            return

        # Otherwise, assume it's a filename in the destination dir
        full_path = os.path.join(self.destination_dir, filename)
        if os.path.isfile(full_path):
            self.selected_backup_path = full_path
            logger.debug(f"Selected backup set to: {full_path}")
        else:
            logger.warning(f"Selected backup file not found: {full_path}")
            self.selected_backup_path = None

    def get_selected_or_latest(self):
        """Return selected backup path if valid, else latest."""
        if self.selected_backup_path and os.path.isfile(self.selected_backup_path):
            return self.selected_backup_path
        return self.get_latest_backup()

    def _create_archive(self, zip_path, source_folders, progress_callback=None):
        """
        Create an archive (zip or 7z) from a list of source folders.
        Returns (success, message).
        """
        try:
            if self.archive_format == '7z' and HAS_7Z:
                # Use py7zr
                with py7zr.SevenZipFile(zip_path, 'w') as archive:
                    total_folders = len(source_folders)
                    for idx, src in enumerate(source_folders):
                        base_name = os.path.basename(src)
                        # Walk and add files with their relative path
                        for root, dirs, files in os.walk(src):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.join(base_name, os.path.relpath(file_path, src))
                                archive.write(file_path, arcname)
                        if progress_callback:
                            progress_callback((idx + 1) / total_folders * 100)
                return True, "7z archive created"
            else:
                # Use standard zip
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    total_folders = len(source_folders)
                    for idx, src in enumerate(source_folders):
                        base_name = os.path.basename(src)
                        for root, dirs, files in os.walk(src):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.join(base_name, os.path.relpath(file_path, src))
                                zipf.write(file_path, arcname)
                        if progress_callback:
                            progress_callback((idx + 1) / total_folders * 100)
                return True, "Zip archive created"
        except Exception as e:
            return False, str(e)

    def create_backup(self, progress_callback=None, source_list=None, subfolder=None):
        """
        Create a new backup archive of all source folders.
        If source_list is provided, use that list instead of self.sources.
        If subfolder is provided (e.g., 'custom_scripts'), the archive will be placed inside that subfolder.
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = '.7z' if self.archive_format == '7z' else '.zip'
        archive_name = f"backup_{timestamp}{ext}"

        # Determine destination directory (with subfolder if provided)
        dest_dir = self.destination_dir
        if subfolder:
            dest_dir = os.path.join(dest_dir, subfolder)

        # Create destination directory if it doesn't exist
        os.makedirs(dest_dir, exist_ok=True)

        archive_path = os.path.join(dest_dir, archive_name)

        # Determine which sources to use
        sources_to_backup = source_list if source_list is not None else self.sources

        expanded_sources = []
        for src in sources_to_backup:
            expanded = self.config.expand_path(src)
            if os.path.exists(expanded):
                expanded_sources.append(expanded)
            else:
                logger = logging.getLogger('DeploymentKit')
                logger.warning(f"Source folder not found: {expanded}")

        if not expanded_sources:
            return False, "No valid source folders found"

        success, msg = self._create_archive(archive_path, expanded_sources, progress_callback)
        if success:
            # Only set as selected if it's in the root (not a subfolder)
            if not subfolder:
                self.set_selected_by_filename(archive_name)
        return success, archive_path if success else msg

    def _extract_archive(self, archive_path, target_base_dir, progress_callback=None):
        """Extract an archive (zip or 7z) to target_base_dir, preserving folder structure."""
        try:
            if archive_path.endswith('.7z') and HAS_7Z:
                with py7zr.SevenZipFile(archive_path, 'r') as archive:
                    import tempfile
                    with tempfile.TemporaryDirectory() as tmpdir:
                        archive.extractall(tmpdir)
                        for root, dirs, files in os.walk(tmpdir):
                            for file in files:
                                src_file = os.path.join(root, file)
                                rel_path = os.path.relpath(src_file, tmpdir)
                                dest_file = os.path.join(target_base_dir, rel_path)
                                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                                shutil.copy2(src_file, dest_file)
                                if progress_callback:
                                    progress_callback(50)
                    return True, "Extracted successfully"
            else:
                with zipfile.ZipFile(archive_path, 'r') as zipf:
                    top_dirs = set()
                    for name in zipf.namelist():
                        parts = name.split('/')
                        if parts and parts[0]:
                            top_dirs.add(parts[0])

                    for top in top_dirs:
                        matched_source = None
                        for src in self.sources:
                            expanded = self.config.expand_path(src)
                            if os.path.basename(expanded) == top:
                                matched_source = expanded
                                break
                        if matched_source is None:
                            continue
                        for name in zipf.namelist():
                            if name.startswith(top + '/'):
                                rel_path = os.path.relpath(name, top)
                                dest_path = os.path.join(matched_source, rel_path)
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                with zipf.open(name) as src_file:
                                    with open(dest_path, 'wb') as dst_file:
                                        shutil.copyfileobj(src_file, dst_file)
                return True, "Extracted successfully"
        except Exception as e:
            return False, str(e)

    def restore_backup(self, zip_path, progress_callback=None, sources_to_restore=None):
        """Restore a backup archive to the original source locations.
           If sources_to_restore is provided, only restore those sources.
        """
        logger = logging.getLogger('DeploymentKit')
        logger.debug(f"restore_backup called with: {zip_path}")

        if not os.path.isfile(zip_path):
            logger.error(f"Archive file not found: {zip_path}")
            return False, f"Archive file not found: {zip_path}"

        import tempfile
        temp_dir = tempfile.mkdtemp()
        try:
            if zip_path.endswith('.7z') and HAS_7Z:
                with py7zr.SevenZipFile(zip_path, 'r') as archive:
                    archive.extractall(temp_dir)
            else:
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(temp_dir)

            top_folders = [f for f in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, f))]

            # Determine which sources to restore
            source_list = sources_to_restore if sources_to_restore is not None else self.sources

            for folder in top_folders:
                matched_source = None
                for src in source_list:
                    expanded = self.config.expand_path(src)
                    if os.path.basename(expanded) == folder:
                        matched_source = expanded
                        break
                if matched_source is None:
                    logger.warning(f"No matching source for folder '{folder}', skipping")
                    continue

                src_path = os.path.join(temp_dir, folder)
                for root, dirs, files in os.walk(src_path):
                    for file in files:
                        src_file = os.path.join(root, file)
                        rel_path = os.path.relpath(src_file, src_path)
                        dest_file = os.path.join(matched_source, rel_path)
                        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                        shutil.copy2(src_file, dest_file)
                logger.debug(f"Restored folder '{folder}' to {matched_source}")

            return True, "Restore completed successfully"
        except Exception as e:
            import traceback
            logger.error(f"Restore exception: {e}")
            logger.error(traceback.format_exc())
            return False, str(e)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


    def add_source(self, source_path):
        """Add a source folder to the backup list, converting to env var if possible."""
        converted = self._convert_to_env_var(source_path)
        if converted not in self.sources:
            self.sources.append(converted)
            self._save_backup_config()
            return True
        return False

    def remove_source(self, source_path):
        if source_path in self.sources:
            self.sources.remove(source_path)
            self._save_backup_config()
            return True
        return False

    def set_destination(self, dest_path):
        """Set the backup destination directory."""
        self.destination_dir = dest_path
        self.backup_data['destination'] = dest_path
        self._save_backup_config()
        self.selected_backup_path = None
        logger = logging.getLogger('DeploymentKit')
        logger.debug(f"Destination changed to: {dest_path}")

    def reset_destination_to_default(self):
        """Reset destination to [base_dir]/backups."""
        default_path = os.path.join(self.config.base_dir, 'backups')
        self.set_destination(default_path)
        return default_path

    def _save_backup_config(self):
        self.config.backup['sources'] = self.sources
        self.config.backup['destination'] = self.backup_data.get('destination', 'backups')
        self.config.save_backup()

    def _convert_to_env_var(self, path):
        """Convert a full path to use environment variables if possible."""
        norm_path = os.path.normpath(path)
        expanded_path = os.path.expandvars(norm_path)

        env_vars = {
            '%LOCALAPPDATA%': os.path.expandvars('%LOCALAPPDATA%'),
            '%APPDATA%': os.path.expandvars('%APPDATA%'),
            '%USERPROFILE%': os.path.expandvars('%USERPROFILE%'),
            '%PUBLIC%': os.path.expandvars('%PUBLIC%'),
            '%PROGRAMFILES%': os.path.expandvars('%PROGRAMFILES%'),
            '%PROGRAMFILES(X86)%': os.path.expandvars('%PROGRAMFILES(X86)%'),
            '%PROGRAMDATA%': os.path.expandvars('%PROGRAMDATA%'),
            '%WINDIR%': os.path.expandvars('%WINDIR%'),
            '%SYSTEMROOT%': os.path.expandvars('%SYSTEMROOT%'),
            '%SystemDrive%\\': os.path.expandvars('%SystemDrive%') + '\\',
        }

        sorted_vars = sorted(env_vars.items(), key=lambda x: len(x[1]), reverse=True)

        for var, expanded in sorted_vars:
            expanded_norm = os.path.normpath(expanded)
            if not expanded_norm:
                continue
            norm_path_lower = norm_path.lower()
            expanded_lower = expanded_norm.lower()

            if expanded_lower == norm_path_lower:
                return var
            if expanded_lower and norm_path_lower.startswith(expanded_lower + os.sep.lower()):
                remainder = norm_path[len(expanded_norm):]
                if remainder.startswith(os.sep):
                    return var + remainder
                else:
                    return var + os.sep + remainder
        return path