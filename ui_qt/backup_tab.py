"""
Backup/Restore tab - port of gui_main.py's _build_backup_tab, _do_backup,
_do_restore, and the sources tree helpers.

Backup/restore actually touch the filesystem and can take a while, so they
run on a plain background thread (matching the Tkinter version) and report
back through Qt signals, which are safely queued onto the GUI thread even
though emitted from a worker thread.
"""
from __future__ import annotations
import os
import shutil
import threading
import zipfile

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QComboBox, QCheckBox, QFileDialog,
    QMessageBox, QAbstractItemView
)

from ui_qt.busy_tracker import BusyMixin

SPECIAL_SOURCES = [
    ('\u2b50 Custom Scripts', os.path.expandvars('%SystemDrive%\\Scripts'), 'custom_scripts'),
    ('\u2b50 PowerTools', os.path.expandvars('%SystemDrive%\\PowerTools'), 'powertools'),
]


class BackupTab(QWidget, BusyMixin):
    backup_finished = Signal()
    restore_finished = Signal()

    def __init__(self, config, backup_engine, log_bus, parent=None):
        super().__init__(parent)
        self.config = config
        self.backup_engine = backup_engine
        self.log_bus = log_bus
        self.item_meta: dict[str, dict] = {}  # src_path -> {'item', 'special', 'subfolder'}

        self._build_ui()
        self._init_busy([self.backup_btn, self.restore_btn])
        self.backup_finished.connect(lambda: (self._refresh_backup_list(), self._set_busy(False)))
        self.restore_finished.connect(lambda: self._set_busy(False))

    def _log(self, text: str):
        self.log_bus.log(text)

    # ---------------- UI ----------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- destination ---
        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Backup Destination:"))
        self.dest_edit = QLineEdit(self.backup_engine.destination_dir)
        self.dest_edit.editingFinished.connect(self._update_destination_from_entry)
        dest_row.addWidget(self.dest_edit, stretch=1)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_dest)
        dest_row.addWidget(browse_btn)
        default_btn = QPushButton("Default")
        default_btn.clicked.connect(self._reset_dest_default)
        dest_row.addWidget(default_btn)
        refresh_btn = QPushButton("Refresh List")
        refresh_btn.clicked.connect(self._refresh_backup_list)
        dest_row.addWidget(refresh_btn)
        layout.addLayout(dest_row)

        # --- sources tree ---
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Source Path"])
        self.tree.setRootIsDecorated(False)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setAllColumnsShowFocus(True)
        layout.addWidget(self.tree, stretch=1)

        # --- available backups + buttons ---
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(QLabel("Available Backups:"))
        self.backup_combo = QComboBox()
        self.backup_combo.setMinimumWidth(220)
        bottom_row.addWidget(self.backup_combo)
        bottom_row.addStretch(1)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_source)
        bottom_row.addWidget(add_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_selected_sources)
        bottom_row.addWidget(remove_btn)
        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._move_source_up)
        bottom_row.addWidget(move_up_btn)
        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._move_source_down)
        bottom_row.addWidget(move_down_btn)
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all_sources)
        bottom_row.addWidget(select_all_btn)
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self._select_none_sources)
        bottom_row.addWidget(select_none_btn)

        self.restore_selected_only_cb = QCheckBox("Restore selected only")
        self.restore_selected_only_cb.setChecked(True)
        bottom_row.addWidget(self.restore_selected_only_cb)

        self.backup_btn = QPushButton("Backup")
        self.backup_btn.clicked.connect(self._do_backup)
        bottom_row.addWidget(self.backup_btn)
        self.restore_btn = QPushButton("Restore")
        self.restore_btn.clicked.connect(self._do_restore)
        bottom_row.addWidget(self.restore_btn)

        layout.addLayout(bottom_row)

        self._refresh_sources_list()
        self._refresh_backup_list()

    # ---------------- sources tree ----------------
    def _refresh_sources_list(self):
        self.tree.clear()
        self.item_meta.clear()

        for display, src_path, subfolder in SPECIAL_SOURCES:
            item = QTreeWidgetItem([display])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            self.tree.addTopLevelItem(item)
            self.item_meta[src_path] = {'item': item, 'special': True, 'subfolder': subfolder}

        for src in self.backup_engine.sources:
            item = QTreeWidgetItem([src])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            self.tree.addTopLevelItem(item)
            self.item_meta[src] = {'item': item, 'special': False}

    def _add_source(self):
        path = QFileDialog.getExistingDirectory(self, "Select folder to back up")
        if path:
            converted = self.backup_engine._convert_to_env_var(path)
            self.backup_engine.add_source(converted)
            self._refresh_sources_list()

    def _remove_selected_sources(self):
        to_remove = []
        for src_path, meta in self.item_meta.items():
            if meta['special']:
                continue
            if meta['item'].checkState(0) != Qt.Checked:
                to_remove.append(src_path)

        if not to_remove:
            QMessageBox.information(
                self, "Info",
                "No user sources are unchecked. To remove a source, uncheck it first, then click 'Remove'."
            )
            return

        reply = QMessageBox.question(
            self, "Confirm Remove", f"Remove {len(to_remove)} unchecked user source(s)?"
        )
        if reply == QMessageBox.Yes:
            for src in to_remove:
                self.backup_engine.remove_source(src)
            self._refresh_sources_list()

    def _select_all_sources(self):
        for meta in self.item_meta.values():
            meta['item'].setCheckState(0, Qt.Checked)

    def _select_none_sources(self):
        for src_path, meta in self.item_meta.items():
            if meta['special']:
                continue  # special sources always remain checked, same as Tkinter version
            meta['item'].setCheckState(0, Qt.Unchecked)

    def _selected_user_source(self) -> str | None:
        current = self.tree.currentItem()
        if not current:
            return None
        for src_path, meta in self.item_meta.items():
            if meta['item'] is current and not meta['special']:
                return src_path
        return None

    def _move_source_up(self):
        src = self._selected_user_source()
        if not src or src not in self.backup_engine.sources:
            return
        idx = self.backup_engine.sources.index(src)
        if idx <= 0:
            return
        sources = self.backup_engine.sources
        sources[idx], sources[idx - 1] = sources[idx - 1], sources[idx]
        self.backup_engine._save_backup_config()
        self._refresh_sources_list()
        if src in self.item_meta:
            self.tree.setCurrentItem(self.item_meta[src]['item'])

    def _move_source_down(self):
        src = self._selected_user_source()
        if not src or src not in self.backup_engine.sources:
            return
        idx = self.backup_engine.sources.index(src)
        if idx >= len(self.backup_engine.sources) - 1:
            return
        sources = self.backup_engine.sources
        sources[idx], sources[idx + 1] = sources[idx + 1], sources[idx]
        self.backup_engine._save_backup_config()
        self._refresh_sources_list()
        if src in self.item_meta:
            self.tree.setCurrentItem(self.item_meta[src]['item'])

    # ---------------- destination ----------------
    def _update_destination_from_entry(self):
        new_dest = self.dest_edit.text().strip()
        if new_dest and (os.path.isdir(new_dest) or not os.path.exists(new_dest)):
            self.backup_engine.set_destination(new_dest)
            self._refresh_backup_list()

    def _browse_dest(self):
        path = QFileDialog.getExistingDirectory(self, "Select backup destination")
        if path:
            self.dest_edit.setText(path)
            self.backup_engine.set_destination(path)
            self._refresh_backup_list()

    def _reset_dest_default(self):
        default_path = self.backup_engine.reset_destination_to_default()
        self.dest_edit.setText(default_path)
        self._refresh_backup_list()
        self._log(f"Backup destination reset to: {default_path}\n")

    def _refresh_backup_list(self):
        current_dest = self.dest_edit.text().strip()
        if current_dest and current_dest != self.backup_engine.destination_dir:
            self.backup_engine.set_destination(current_dest)

        backups = self.backup_engine.get_backup_list()
        self.backup_combo.clear()
        if backups:
            self.backup_combo.addItems([f for f, _, _ in backups])
            self.backup_combo.setCurrentIndex(0)
            self.backup_engine.set_selected_by_filename(backups[0][0])
        else:
            self.backup_engine.selected_backup_path = None

    # ---------------- backup / restore ----------------
    def _do_backup(self):
        if self.is_busy():
            QMessageBox.information(self, "Busy", "A backup or restore is already running.")
            return

        user_sources = []
        special_sources = []
        for src_path, meta in self.item_meta.items():
            if meta['item'].checkState(0) != Qt.Checked:
                continue
            if meta['special']:
                special_sources.append((src_path, meta['subfolder']))
            else:
                user_sources.append(src_path)

        if not user_sources and not special_sources:
            QMessageBox.warning(self, "No Sources Selected",
                                 "No backup sources are checked. Please select at least one source.")
            return

        self._set_busy(True)

        def task():
            self._log("Backup started...\n")
            if user_sources:
                self._log("Backing up user sources...\n")
                success, msg = self.backup_engine.create_backup(source_list=user_sources, subfolder=None)
                if success:
                    self._log(f"User backup successful: {os.path.basename(msg)}\n")
                else:
                    self._log(f"User backup failed: {msg}\n")

            for src_path, subfolder in special_sources:
                if not os.path.isdir(src_path):
                    self._log(f"Warning: Special folder '{src_path}' not found, skipping.\n")
                    continue
                self._log(f"Backing up {os.path.basename(src_path)} to {subfolder}/\n")
                success, msg = self.backup_engine.create_backup(source_list=[src_path], subfolder=subfolder)
                if success:
                    self._log(f"Backup of {os.path.basename(src_path)} successful.\n")
                else:
                    self._log(f"Backup of {os.path.basename(src_path)} failed: {msg}\n")

            self.backup_finished.emit()

        threading.Thread(target=task, daemon=True).start()

    def _do_restore(self):
        if self.is_busy():
            QMessageBox.information(self, "Busy", "A backup or restore is already running.")
            return

        selected = self.backup_combo.currentText()
        if not selected:
            QMessageBox.information(self, "No Backup", "No backup selected in the dropdown.")
            return
        zip_path = os.path.join(self.backup_engine.destination_dir, selected)
        if not os.path.isfile(zip_path):
            QMessageBox.critical(self, "Error", "Backup file not found.")
            return

        restore_selected_only = self.restore_selected_only_cb.isChecked()

        user_sources_to_restore = None
        special_sources_to_restore = []

        if restore_selected_only:
            checked_user, checked_special = [], []
            for src_path, meta in self.item_meta.items():
                if meta['item'].checkState(0) != Qt.Checked:
                    continue
                if meta['special']:
                    checked_special.append((src_path, meta['subfolder']))
                else:
                    checked_user.append(src_path)

            if not checked_user and not checked_special:
                QMessageBox.warning(self, "No Sources Selected",
                                     "No sources are checked. Please select at least one source to restore.")
                return

            user_sources_to_restore = checked_user if checked_user else []
            special_sources_to_restore = checked_special
        else:
            special_sources_to_restore = [(src, sub) for _, src, sub in SPECIAL_SOURCES]

        reply = QMessageBox.question(
            self, "Confirm Restore",
            f"Restore from '{selected}'?\nThis will overwrite existing files for the selected sources."
        )
        if reply != QMessageBox.Yes:
            return

        self._set_busy(True)

        def task():
            self._log(f"Restoring from {selected}...\n")

            if user_sources_to_restore is not None:
                if user_sources_to_restore:
                    success, msg = self.backup_engine.restore_backup(
                        zip_path, sources_to_restore=user_sources_to_restore)
                else:
                    success, msg = True, "No user sources selected for restore."
            else:
                success, msg = self.backup_engine.restore_backup(zip_path, sources_to_restore=None)

            if success:
                self._log("Root backup restored successfully.\n")
            else:
                self._log(f"Root backup restore failed: {msg}\n")

            for src_path, subfolder in special_sources_to_restore:
                subfolder_path = os.path.join(self.backup_engine.destination_dir, subfolder)
                if not os.path.isdir(subfolder_path):
                    self._log(f"No backup found for {os.path.basename(src_path)} in {subfolder}/. Skipping.\n")
                    continue
                zip_files = [f for f in os.listdir(subfolder_path) if f.endswith('.zip')]
                if not zip_files:
                    self._log(f"No backup found for {os.path.basename(src_path)} in {subfolder}/. Skipping.\n")
                    continue
                zip_files.sort(key=lambda x: os.path.getmtime(os.path.join(subfolder_path, x)), reverse=True)
                special_zip = os.path.join(subfolder_path, zip_files[0])

                self._log(f"Restoring {os.path.basename(src_path)} from {special_zip}...\n")
                try:
                    if not os.path.isdir(src_path):
                        os.makedirs(src_path, exist_ok=True)
                    with zipfile.ZipFile(special_zip, 'r') as zf:
                        temp_dir = os.path.join(self.backup_engine.destination_dir, '_temp_extract')
                        os.makedirs(temp_dir, exist_ok=True)
                        zf.extractall(temp_dir)
                        extracted_items = os.listdir(temp_dir)
                        if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_items[0])):
                            top_folder = os.path.join(temp_dir, extracted_items[0])
                            for item in os.listdir(top_folder):
                                src_item = os.path.join(top_folder, item)
                                dst_item = os.path.join(src_path, item)
                                if os.path.isdir(src_item):
                                    shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
                                else:
                                    shutil.copy2(src_item, dst_item)
                        else:
                            for item in extracted_items:
                                src_item = os.path.join(temp_dir, item)
                                dst_item = os.path.join(src_path, item)
                                if os.path.isdir(src_item):
                                    shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
                                else:
                                    shutil.copy2(src_item, dst_item)
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        self._log(f"{os.path.basename(src_path)} restored successfully.\n")
                except Exception as e:
                    self._log(f"{os.path.basename(src_path)} restore failed: {str(e)}\n")

            self._log("Restore process completed.\n")
            self.restore_finished.emit()

        threading.Thread(target=task, daemon=True).start()

    # ---------------- public getters (used by MainTab's deploy flow) ----------------
    def get_checked_sources(self) -> list[str]:
        """Non-special checked source paths - used both for restore scope
        and for the pre-deploy confirmation summary."""
        return [src for src, meta in self.item_meta.items()
                if not meta['special'] and meta['item'].checkState(0) == Qt.Checked]

    def get_restore_selected_only(self) -> bool:
        return self.restore_selected_only_cb.isChecked()

    def set_restore_selected_only(self, value: bool):
        self.restore_selected_only_cb.setChecked(value)

    def apply_checked_sources(self, checked_sources: list[str]):
        """Used by profile load: check exactly the given user sources,
        leave special sources untouched (they always stay checked)."""
        checked_set = set(checked_sources)
        for src_path, meta in self.item_meta.items():
            if meta['special']:
                continue
            meta['item'].setCheckState(0, Qt.Checked if src_path in checked_set else Qt.Unchecked)

    def get_backup_filename(self) -> str:
        return self.backup_combo.currentText()
