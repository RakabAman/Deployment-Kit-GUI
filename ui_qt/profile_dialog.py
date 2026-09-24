"""
Manage Profiles dialog - Qt port of ProfileManager.manage_profiles_dialog /
_show_missing_items_dialog. The underlying ProfileManager class itself
(list_profiles/save_profile/load_profile/delete_profile) is plain Python
with no Tkinter dependency, so it's reused as-is.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QMessageBox,
    QInputDialog, QTextEdit, QApplication
)

from ui_qt.profile_ops import collect_profile_data, apply_profile_data


class MissingItemsDialog(QDialog):
    def __init__(self, parent, missing: dict, profile_name: str | None = None):
        super().__init__(parent)
        title = "Missing Items" + (f" \u2013 {profile_name}" if profile_name else "")
        self.setWindowTitle(title)
        self.resize(550, 350)

        lines = []
        if profile_name:
            lines.append(f"Profile: {profile_name}")
            lines.append("")
        lines.append("The following items from the profile were not found")
        lines.append("in the current configuration and have been skipped:")
        lines.append("")
        for category, items in missing.items():
            if not items:
                continue
            lines.append(f"{category}:")
            for item in items:
                lines.append(f"  \u2022 {item}")
            lines.append("")
        self.message = "\n".join(lines)

        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setPlainText(self.message)
        text.setReadOnly(True)
        text.setStyleSheet("font-family: Consolas, monospace;")
        layout.addWidget(text, stretch=1)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(lambda: self._copy(copy_btn))
        btn_row.addWidget(copy_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _copy(self, btn):
        QApplication.clipboard().setText(self.message)
        btn.setText("Copied!")


class ManageProfilesDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.profile_manager = win.profile_manager
        self.setWindowTitle("Manage Profiles")
        self.resize(450, 400)

        layout = QVBoxLayout(self)
        self.listbox = QListWidget()
        layout.addWidget(self.listbox, stretch=1)
        self._refresh_list()

        btn_row = QHBoxLayout()
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._do_load)
        btn_row.addWidget(load_btn)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._do_save)
        btn_row.addWidget(save_btn)
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._do_delete)
        btn_row.addWidget(delete_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_list)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _refresh_list(self):
        self.listbox.clear()
        self.listbox.addItems(self.profile_manager.list_profiles())

    def _log(self, text: str):
        self.win.log_bus.log(text)

    def _do_load(self):
        item = self.listbox.currentItem()
        if not item:
            QMessageBox.information(self, "No Selection", "Please select a profile to load.")
            return
        name = item.text()
        try:
            data = self.profile_manager.load_profile(name)
            missing = apply_profile_data(self.win, data)
            self._log(f"\u2705 Profile '{name}' loaded successfully.\n")
            if any(missing.values()):
                self._log("\u26a0\ufe0f Missing items:\n")
                for cat, items in missing.items():
                    if items:
                        self._log(f"  {cat}: {', '.join(items)}\n")
                MissingItemsDialog(self.win, missing, name).exec()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load profile: {e}")

    def _do_save(self):
        name, ok = QInputDialog.getText(self, "Save Profile", "Enter a name for this profile:")
        if not ok or not name.strip():
            return
        name = name.strip()
        existing = self.profile_manager.list_profiles()
        if name in existing:
            reply = QMessageBox.question(self, "Overwrite", f"Profile '{name}' already exists. Overwrite?")
            if reply != QMessageBox.Yes:
                return
        data = collect_profile_data(self.win)
        try:
            self.profile_manager.save_profile(name, data)
            self._log(f"\u2705 Profile '{name}' saved successfully.\n")
            self._refresh_list()
            matches = self.listbox.findItems(name, Qt.MatchExactly)
            if matches:
                self.listbox.setCurrentItem(matches[0])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save profile: {e}")

    def _do_delete(self):
        item = self.listbox.currentItem()
        if not item:
            QMessageBox.information(self, "No Selection", "Please select a profile to delete.")
            return
        name = item.text()
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete profile '{name}'?")
        if reply == QMessageBox.Yes:
            self.profile_manager.delete_profile(name)
            self._log(f"Profile '{name}' deleted.\n")
            self._refresh_list()
