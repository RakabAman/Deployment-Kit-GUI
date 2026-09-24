"""
App Management settings tab - port of settings_dialog.py's _build_apps_tab,
_edit_app_dialog, _download_app, _test_offline_installer, _update_offline.

Drag-and-drop reordering (_make_draggable in the original) is replaced with
Move Up/Down buttons, consistent with how the other Qt tabs in this app
handle reordering (see external_scripts_tab.py) - same capability, simpler
interaction model.
"""
from __future__ import annotations
import datetime
import os
import shutil
import subprocess
import threading

from ui_qt.thread_utils import run_on_main_thread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog, QDialog, QAbstractItemView, QTextEdit,
    QProgressDialog
)

from ui_qt.settings_common import test_package_id, sanitize_folder_name

CATEGORIES = ['Browser', 'Utilities', 'Developer Tools', 'Office', 'Multimedia',
              'Security', 'Communication', 'System', 'Other']
INSTALL_TYPES = ['silent', 'non_silent', 'driver', 'script', 'redist']


class AppEditDialog(QDialog):
    def __init__(self, parent, config, catalog, app=None):
        super().__init__(parent)
        self.config = config
        self.catalog = catalog
        self.app = app
        self.original_offline_path = app.offline_path if app else ""
        self.original_post_install_path = app.post_install_script if app else ""

        self.setWindowTitle("Edit App" if app else "Add App")
        self.resize(560, 560)

        grid = QGridLayout(self)
        row = 0

        grid.addWidget(QLabel("Display Name:"), row, 0)
        self.name_edit = QLineEdit(app.display_name if app else "")
        grid.addWidget(self.name_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Category:"), row, 0)
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(CATEGORIES)
        self.category_combo.setCurrentText(app.category if app else "")
        grid.addWidget(self.category_combo, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Offline Path:"), row, 0)
        self.offline_path_edit = QLineEdit(app.offline_path if app else "")
        grid.addWidget(self.offline_path_edit, row, 1)
        browse_offline_btn = QPushButton("Browse\u2026")
        browse_offline_btn.clicked.connect(self._browse_offline_file)
        grid.addWidget(browse_offline_btn, row, 2)
        row += 1

        grid.addWidget(QLabel("Offline Switch:"), row, 0)
        self.offline_switch_edit = QLineEdit(app.offline_switch if app else "")
        grid.addWidget(self.offline_switch_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Offline Version:"), row, 0)
        self.offline_version_edit = QLineEdit(app.offline_version if app else "")
        grid.addWidget(self.offline_version_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Download URL:"), row, 0)
        self.download_url_edit = QLineEdit(app.offline_download_url if app else "")
        grid.addWidget(self.download_url_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(QLabel("Winget ID:"), row, 0)
        self.winget_edit = QLineEdit(app.winget_id if app else "")
        grid.addWidget(self.winget_edit, row, 1)
        winget_test_btn = QPushButton("Test")
        winget_test_btn.clicked.connect(lambda: self._test_package('winget', self.winget_edit.text().strip()))
        grid.addWidget(winget_test_btn, row, 2)
        row += 1

        grid.addWidget(QLabel("Choco ID:"), row, 0)
        self.choco_edit = QLineEdit(app.choco_id if app else "")
        grid.addWidget(self.choco_edit, row, 1)
        choco_test_btn = QPushButton("Test")
        choco_test_btn.clicked.connect(lambda: self._test_package('choco', self.choco_edit.text().strip()))
        grid.addWidget(choco_test_btn, row, 2)
        row += 1

        grid.addWidget(QLabel("Install Type:"), row, 0)
        self.install_type_combo = QComboBox()
        self.install_type_combo.addItems(INSTALL_TYPES)
        self.install_type_combo.setCurrentText(app.install_type if app else "silent")
        grid.addWidget(self.install_type_combo, row, 1, 1, 2)
        row += 1

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #2563eb;")
        grid.addWidget(self.status_label, row, 0, 1, 3)
        row += 1

        grid.addWidget(QLabel("Post-Install Script:"), row, 0)
        self.post_install_edit = QLineEdit(app.post_install_script if app else "")
        grid.addWidget(self.post_install_edit, row, 1)
        browse_post_btn = QPushButton("Browse\u2026")
        browse_post_btn.clicked.connect(self._browse_post_install)
        grid.addWidget(browse_post_btn, row, 2)
        row += 1

        action_row = QHBoxLayout()
        test_installer_btn = QPushButton("Test Installer")
        test_installer_btn.clicked.connect(self._test_offline_installer)
        action_row.addWidget(test_installer_btn)
        download_btn = QPushButton("Download Now")
        download_btn.clicked.connect(self._download_now)
        action_row.addWidget(download_btn)
        action_row.addWidget(QLabel("(uses URL above)"))
        action_row.addStretch(1)
        grid.addLayout(action_row, row, 0, 1, 3)
        row += 1

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        grid.addLayout(btn_row, row, 0, 1, 3)

    def _browse_offline_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Offline Installer", "",
            "Executable files (*.exe);;MSI files (*.msi);;MSIX files (*.msix);;"
            "Batch files (*.bat *.cmd);;PowerShell scripts (*.ps1);;All files (*.*)"
        )
        if filename:
            self.offline_path_edit.setText(filename)

    def _browse_post_install(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Post-Install Script", "",
            "Script files (*.ps1 *.bat *.cmd *.py *.reg);;All files (*.*)"
        )
        if filename:
            self.post_install_edit.setText(filename)

    def _test_package(self, provider: str, package_id: str):
        if not package_id:
            self.status_label.setText("Please enter a package ID")
            self.status_label.setStyleSheet("color: #b26a00;")
            return
        self.status_label.setText(f"\u23f3 Checking {provider}...")
        self.status_label.setStyleSheet("color: #2563eb;")

        def run_test():
            success, msg, _version = test_package_id(provider, package_id)

            def update_label():
                if success:
                    self.status_label.setText(f"\u2705 {msg}")
                    self.status_label.setStyleSheet("color: #1a7f37;")
                else:
                    self.status_label.setText(f"\u274c {msg}")
                    self.status_label.setStyleSheet("color: #c0392b;")
            run_on_main_thread(update_label)

        threading.Thread(target=run_test, daemon=True).start()

    def _test_offline_installer(self):
        offline_path = self.offline_path_edit.text().strip()
        switch = self.offline_switch_edit.text().strip()
        if not offline_path:
            QMessageBox.critical(self, "Error", "No offline path specified.")
            return
        full_path = offline_path if os.path.isabs(offline_path) else os.path.join(self.config.base_dir, offline_path)
        if not os.path.isfile(full_path):
            QMessageBox.critical(self, "Error", f"Installer file not found: {full_path}")
            return
        cmd = f'msiexec /i "{full_path}" {switch}' if full_path.lower().endswith('.msi') else f'"{full_path}" {switch}'

        dlg = QDialog(self)
        dlg.setWindowTitle("Testing Installer")
        dlg.resize(500, 400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"Testing: {os.path.basename(full_path)}"))
        layout.addWidget(QLabel(f"Command: {cmd}"))
        output = QTextEdit()
        output.setReadOnly(True)
        layout.addWidget(output, stretch=1)
        status = QLabel("Running...")
        layout.addWidget(status)
        dlg.show()

        def run_test():
            try:
                start = datetime.datetime.now()
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
                elapsed = (datetime.datetime.now() - start).total_seconds()

                def update():
                    output.append(f"Exit code: {result.returncode}\n")
                    output.append(f"Time: {elapsed:.2f} seconds\n")
                    if result.stdout:
                        output.append("--- STDOUT ---")
                        output.append(result.stdout)
                    if result.stderr:
                        output.append("--- STDERR ---")
                        output.append(result.stderr)
                    if result.returncode == 0:
                        status.setText("\u2705 SUCCESS")
                        status.setStyleSheet("color: #1a7f37;")
                    else:
                        status.setText(f"\u274c FAILED (exit {result.returncode})")
                        status.setStyleSheet("color: #c0392b;")
                run_on_main_thread(update)
            except subprocess.TimeoutExpired:
                run_on_main_thread(lambda: (output.append("\u23f1\ufe0f Test timed out after 120 seconds."),
                                               status.setText("\u23f1\ufe0f TIMEOUT")))
            except Exception as e:
                run_on_main_thread(lambda: (output.append(f"\u26a0\ufe0f Error: {e}"),
                                               status.setText("\u26a0\ufe0f ERROR")))

        threading.Thread(target=run_test, daemon=True).start()

    def _download_now(self):
        display_name = self.name_edit.text().strip()
        url = self.download_url_edit.text().strip()
        if not display_name:
            QMessageBox.critical(self, "Error", "Display name is required before downloading.")
            return
        if not url:
            QMessageBox.critical(self, "Error", "Download URL is empty.")
            return

        app = self.catalog.get_app(display_name)
        temp_app = None
        if not app:
            temp_app = self.catalog.add_app({'display_name': display_name, 'offline_download_url': url, 'offline_path': ''})
            app = temp_app
        elif url != app.offline_download_url:
            app.offline_download_url = url
            self.catalog._save_apps_to_config()

        progress = QProgressDialog(f"Downloading {display_name}...", None, 0, 100, self)
        progress.setWindowTitle("Downloading...")
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()

        def update_progress(value):
            run_on_main_thread(lambda: progress.setValue(int(value)))

        def do_download():
            success, msg = self.catalog.download_offline_installer(display_name, progress_callback=update_progress)

            def finish():
                progress.close()
                if success:
                    QMessageBox.information(self, "Success", f"Download of {display_name} completed.")
                    app_after = self.catalog.get_app(display_name)
                    if app_after:
                        self.offline_path_edit.setText(app_after.offline_path)
                    if temp_app:
                        self.catalog.delete_app(display_name)
                else:
                    QMessageBox.critical(self, "Download Failed", msg)
                    if temp_app:
                        self.catalog.delete_app(display_name)
            run_on_main_thread(finish)

        threading.Thread(target=do_download, daemon=True).start()

    def _save(self):
        data = {
            'display_name': self.name_edit.text().strip(),
            'category': self.category_combo.currentText().strip(),
            'offline_path': self.offline_path_edit.text().strip(),
            'offline_switch': self.offline_switch_edit.text().strip(),
            'offline_version': self.offline_version_edit.text().strip(),
            'offline_download_url': self.download_url_edit.text().strip(),
            'winget_id': self.winget_edit.text().strip(),
            'choco_id': self.choco_edit.text().strip(),
            'install_type': self.install_type_combo.currentText(),
            'post_install_script': self.post_install_edit.text().strip(),
        }
        if not data['display_name']:
            QMessageBox.critical(self, "Error", "Display name is required")
            return

        offline_path = data['offline_path']
        if offline_path and os.path.isabs(offline_path) and offline_path != self.original_offline_path:
            if os.path.isfile(offline_path):
                try:
                    folder_name = sanitize_folder_name(data['display_name'])
                    target_dir = os.path.join(self.config.base_dir, 'install', folder_name)
                    os.makedirs(target_dir, exist_ok=True)
                    original_filename = os.path.basename(offline_path)
                    target_file = os.path.join(target_dir, original_filename)
                    if os.path.abspath(offline_path) != os.path.abspath(target_file):
                        shutil.copy2(offline_path, target_file)
                    data['offline_path'] = os.path.join('install', folder_name, original_filename)
                except PermissionError:
                    if QMessageBox.question(
                        self, "File Locked",
                        "Cannot copy the file because it is in use.\n\n"
                        "Continue saving without copying the installer?"
                    ) != QMessageBox.Yes:
                        return
            else:
                if QMessageBox.question(
                    self, "File Not Found", f"The file '{offline_path}' does not exist. Continue saving?"
                ) != QMessageBox.Yes:
                    return

        post_script = data['post_install_script']
        if post_script and os.path.isabs(post_script) and os.path.isfile(post_script) \
                and post_script != self.original_post_install_path:
            try:
                folder_name = sanitize_folder_name(data['display_name'])
                target_dir = os.path.join(self.config.base_dir, 'install', folder_name)
                os.makedirs(target_dir, exist_ok=True)
                ext = os.path.splitext(post_script)[1]
                dest = os.path.join(target_dir, f"post_install{ext}")
                shutil.copy2(post_script, dest)
                data['post_install_script'] = os.path.join('install', folder_name, f"post_install{ext}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to copy post-install script: {e}")

        if self.app:
            if self.catalog.update_app(self.app.display_name, data):
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Update failed.")
        else:
            if self.catalog.get_app(data['display_name']):
                QMessageBox.critical(self, "Error", "App with this name already exists.")
                return
            self.catalog.add_app(data)
            self.accept()


class AppManagementTab(QWidget):
    def __init__(self, config, catalog, parent=None):
        super().__init__(parent)
        self.config = config
        self.catalog = catalog

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Name", "Category", "Type", "Offline Path", "Winget ID", "Choco ID"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        layout.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add App")
        add_btn.clicked.connect(self._add_app)
        btn_row.addWidget(add_btn)
        edit_btn = QPushButton("Edit App")
        edit_btn.clicked.connect(self._edit_app)
        btn_row.addWidget(edit_btn)
        delete_btn = QPushButton("Delete App")
        delete_btn.clicked.connect(self._delete_app)
        btn_row.addWidget(delete_btn)
        update_offline_btn = QPushButton("Update Offline")
        update_offline_btn.clicked.connect(self._update_offline)
        btn_row.addWidget(update_offline_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self):
        self.catalog.refresh()
        self.table.setRowCount(0)
        for app in self.catalog.apps:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate([app.display_name, app.category, app.install_type,
                                          app.offline_path, app.winget_id, app.choco_id]):
                self.table.setItem(row, col, QTableWidgetItem(value or ""))

    def _selected_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _add_app(self):
        dlg = AppEditDialog(self, self.config, self.catalog, app=None)
        if dlg.exec() == QDialog.Accepted:
            self._refresh()

    def _edit_app(self):
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "No Selection", "Please select an app to edit.")
            return
        app = self.catalog.get_app(name)
        if app:
            dlg = AppEditDialog(self, self.config, self.catalog, app=app)
            if dlg.exec() == QDialog.Accepted:
                self._refresh()

    def _delete_app(self):
        name = self._selected_name()
        if not name:
            return
        if QMessageBox.question(self, "Confirm Delete", "Delete selected app?") == QMessageBox.Yes:
            self.catalog.delete_app(name)
            self._refresh()

    def _update_offline(self):
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "No Selection", "Please select an app to update.")
            return
        app = self.catalog.get_app(name)
        if app:
            dlg = AppEditDialog(self, self.config, self.catalog, app=app)
            dlg._download_now()
