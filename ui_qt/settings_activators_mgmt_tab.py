"""
Activators Management settings tab - port of settings_dialog.py's
_build_activators_tab / _edit_activator_dialog / _download_activator.
"""
from __future__ import annotations
import os
import threading
import time

from ui_qt.thread_utils import run_on_main_thread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog, QDialog, QAbstractItemView, QProgressDialog,
    QInputDialog
)


class ActivatorEditDialog(QDialog):
    def __init__(self, parent, config, activator: dict | None = None):
        super().__init__(parent)
        self.config = config
        self.activator = activator

        self.setWindowTitle("Edit Activator" if activator else "Add Activator")
        self.resize(560, 460)

        grid = QGridLayout(self)
        row = 0

        grid.addWidget(QLabel("Name:"), row, 0)
        self.name_edit = QLineEdit(activator.get('name', '') if activator else '')
        grid.addWidget(self.name_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Category:"), row, 0)
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        existing = sorted(set(a.get('category', '') for a in config.activators.get('activators', []) if a.get('category')))
        self.category_combo.addItems(existing)
        self.category_combo.setCurrentText(activator.get('category', '') if activator else '')
        grid.addWidget(self.category_combo, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Description:"), row, 0)
        self.desc_edit = QLineEdit(activator.get('description', '') if activator else '')
        grid.addWidget(self.desc_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Main Executable (filename):"), row, 0)
        self.exec_edit = QLineEdit(activator.get('executable', '') if activator else '')
        grid.addWidget(self.exec_edit, row, 1)
        browse_exec_btn = QPushButton("Browse\u2026")
        browse_exec_btn.clicked.connect(self._browse_exec)
        grid.addWidget(browse_exec_btn, row, 2)
        row += 1

        grid.addWidget(QLabel("Folder (optional - full folder with all files):"), row, 0)
        self.folder_edit = QLineEdit(activator.get('folder', '') if activator else '')
        grid.addWidget(self.folder_edit, row, 1)
        browse_folder_btn = QPushButton("Browse\u2026")
        browse_folder_btn.clicked.connect(self._browse_folder)
        grid.addWidget(browse_folder_btn, row, 2)
        row += 1

        grid.addWidget(QLabel("Archive (if folder selected, will be zipped):"), row, 0)
        self.archive_edit = QLineEdit(activator.get('archive', '') if activator else '')
        grid.addWidget(self.archive_edit, row, 1, 1, 2)
        row += 1
        hint = QLabel("(Leave empty - auto-generated)")
        hint.setStyleSheet("color: gray;")
        grid.addWidget(hint, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Default Switches:"), row, 0)
        self.switches_edit = QLineEdit(activator.get('default_switches', '') if activator else '')
        grid.addWidget(self.switches_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Download URL:"), row, 0)
        self.download_url_edit = QLineEdit(activator.get('download_url', '') if activator else '')
        grid.addWidget(self.download_url_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("GitHub Repo (user/repo):"), row, 0)
        self.github_repo_edit = QLineEdit(activator.get('github_repo', '') if activator else '')
        grid.addWidget(self.github_repo_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("GitHub Asset Pattern (e.g. *.zip):"), row, 0)
        self.github_pattern_edit = QLineEdit(activator.get('github_asset_pattern', '') if activator else '')
        grid.addWidget(self.github_pattern_edit, row, 1, 1, 2)
        row += 1

        download_btn = QPushButton("Download Now (from URL/GitHub)")
        download_btn.clicked.connect(self._download_now)
        grid.addWidget(download_btn, row, 0, 1, 3)
        row += 1

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        grid.addLayout(btn_row, row, 0, 1, 3)

    def _browse_exec(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Main Executable", "",
            "Executable files (*.exe *.cmd *.bat *.ps1);;All files (*.*)"
        )
        if filename:
            self.exec_edit.setText(filename)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Activator Folder")
        if folder:
            self.folder_edit.setText(folder)

    def _download_now(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.critical(self, "Error", "Name is required before downloading.")
            return
        download_dict = {
            'download_url': self.download_url_edit.text().strip(),
            'github_repo': self.github_repo_edit.text().strip(),
            'github_asset_pattern': self.github_pattern_edit.text().strip(),
        }
        if not download_dict['download_url'] and not download_dict['github_repo']:
            QMessageBox.critical(self, "Error", "Download URL or GitHub repo is required.")
            return
        _run_download(self, self.config, name, download_dict, on_success=lambda: None)

    def _save(self):
        data = {
            'name': self.name_edit.text().strip(),
            'category': self.category_combo.currentText().strip(),
            'description': self.desc_edit.text().strip(),
            'executable': self.exec_edit.text().strip(),
            'folder': self.folder_edit.text().strip(),
            'archive': self.archive_edit.text().strip(),
            'default_switches': self.switches_edit.text().strip(),
            'download_url': self.download_url_edit.text().strip(),
            'github_repo': self.github_repo_edit.text().strip(),
            'github_asset_pattern': self.github_pattern_edit.text().strip(),
        }
        if not data['name']:
            QMessageBox.critical(self, "Error", "Name is required")
            return
        if not data['executable']:
            QMessageBox.critical(self, "Error", "Main executable is required")
            return

        if data['folder'] and os.path.isdir(data['folder']):
            proceed = True
            if data['archive']:
                proceed = QMessageBox.question(
                    self, "Compress Folder",
                    "The folder will be compressed to a .7z archive. Continue?"
                ) == QMessageBox.Yes
            if proceed:
                try:
                    import py7zr
                except ImportError:
                    QMessageBox.critical(self, "Error",
                                          "py7zr module is required to compress activator folder. "
                                          "Install: pip install py7zr")
                    return
                archive_name = f"activator_{data['name'].replace(' ', '_')}_{int(time.time())}.7z"
                try:
                    activators_dir = os.path.join(self.config.base_dir, 'activators')
                    os.makedirs(activators_dir, exist_ok=True)
                    with py7zr.SevenZipFile(os.path.join(activators_dir, archive_name), 'w') as archive:
                        archive.writeall(data['folder'], arcname=os.path.basename(data['folder']))
                    data['archive'] = archive_name
                    data['folder'] = ''
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to compress folder: {e}")
                    return

        activators_list = self.config.activators.get('activators', [])
        if self.activator:
            for i, a in enumerate(activators_list):
                if a.get('name') == self.activator.get('name'):
                    activators_list[i] = data
                    break
        else:
            if any(a.get('name') == data['name'] for a in activators_list):
                QMessageBox.critical(self, "Error", "Activator with this name already exists.")
                return
            activators_list.append(data)

        self.config.activators['activators'] = activators_list
        self.config.save_activators()
        self.accept()


def _run_download(parent, config, name: str, download_dict: dict, on_success):
    from modules.activator_engine import ActivatorEngine
    engine = ActivatorEngine(config)
    full_dict = {'name': name, **download_dict}

    progress = QProgressDialog(f"Downloading {name}...", None, 0, 100, parent)
    progress.setWindowTitle("Downloading Activator")
    progress.setCancelButton(None)
    progress.setMinimumDuration(0)
    progress.show()

    def update_progress(value):
        run_on_main_thread(lambda: progress.setValue(int(value)))

    def do_download():
        def log_cb(msg):
            pass
        success, msg, _file_path = engine.download_activator(full_dict, update_progress, log_cb)

        def finish():
            progress.close()
            if success:
                QMessageBox.information(parent, "Success", f"Download of {name} completed.")
                on_success()
            else:
                QMessageBox.critical(parent, "Download Failed", msg)
        run_on_main_thread(finish)

    threading.Thread(target=do_download, daemon=True).start()


class ActivatorsManagementTab(QWidget):
    def __init__(self, config, on_saved, parent=None):
        super().__init__(parent)
        self.config = config
        self.on_saved = on_saved  # called after any change, so the main Activators tab refreshes too

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "Category", "Description", "Executable", "Default Switches"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        layout.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Activator")
        add_btn.clicked.connect(self._add_activator)
        btn_row.addWidget(add_btn)
        edit_btn = QPushButton("Edit Activator")
        edit_btn.clicked.connect(self._edit_activator)
        btn_row.addWidget(edit_btn)
        delete_btn = QPushButton("Delete Activator")
        delete_btn.clicked.connect(self._delete_activator)
        btn_row.addWidget(delete_btn)
        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._move_up)
        btn_row.addWidget(move_up_btn)
        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._move_down)
        btn_row.addWidget(move_down_btn)
        download_btn = QPushButton("Download")
        download_btn.clicked.connect(self._download_selected)
        btn_row.addWidget(download_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self):
        self.config.activators = self.config._load_json(self.config.activators_file)
        self.table.setRowCount(0)
        for act in self.config.activators.get('activators', []):
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate([act.get('name', ''), act.get('category', ''), act.get('description', ''),
                                          act.get('executable', ''), act.get('default_switches', '')]):
                self.table.setItem(row, col, QTableWidgetItem(value))

    def _selected_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _find_activator(self, name: str) -> dict | None:
        return next((a for a in self.config.activators.get('activators', []) if a.get('name') == name), None)

    def _add_activator(self):
        dlg = ActivatorEditDialog(self, self.config, activator=None)
        if dlg.exec() == QDialog.Accepted:
            self._refresh()
            if self.on_saved:
                self.on_saved()

    def _edit_activator(self):
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "No Selection", "Please select an activator to edit.")
            return
        act = self._find_activator(name)
        if act:
            dlg = ActivatorEditDialog(self, self.config, activator=act)
            if dlg.exec() == QDialog.Accepted:
                self._refresh()
                if self.on_saved:
                    self.on_saved()

    def _delete_activator(self):
        name = self._selected_name()
        if not name:
            return
        if QMessageBox.question(self, "Confirm Delete", "Delete selected activator?") == QMessageBox.Yes:
            activators_list = self.config.activators.get('activators', [])
            self.config.activators['activators'] = [a for a in activators_list if a.get('name') != name]
            self.config.save_activators()
            self._refresh()
            if self.on_saved:
                self.on_saved()

    def _move_up(self):
        row = self.table.currentRow()
        if row <= 0:
            return
        activators_list = self.config.activators.get('activators', [])
        activators_list[row], activators_list[row - 1] = activators_list[row - 1], activators_list[row]
        self.config.activators['activators'] = activators_list
        self.config.save_activators()
        self._refresh()
        self.table.setCurrentCell(row - 1, 0)
        if self.on_saved:
            self.on_saved()

    def _move_down(self):
        row = self.table.currentRow()
        activators_list = self.config.activators.get('activators', [])
        if row < 0 or row >= len(activators_list) - 1:
            return
        activators_list[row], activators_list[row + 1] = activators_list[row + 1], activators_list[row]
        self.config.activators['activators'] = activators_list
        self.config.save_activators()
        self._refresh()
        self.table.setCurrentCell(row + 1, 0)
        if self.on_saved:
            self.on_saved()

    def _download_selected(self):
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "No Selection", "Please select an activator to download.")
            return
        act = self._find_activator(name)
        if not act:
            return
        current_url = act.get('download_url', '')
        new_url, ok = QInputDialog.getText(self, f"Download URL for {name}", "Enter Download URL:", text=current_url)
        if not ok:
            return
        if new_url != current_url:
            act['download_url'] = new_url
            self.config.save_activators()
        download_dict = {
            'download_url': new_url,
            'github_repo': act.get('github_repo', ''),
            'github_asset_pattern': act.get('github_asset_pattern', ''),
        }
        _run_download(self, self.config, name, download_dict, on_success=self._refresh)
