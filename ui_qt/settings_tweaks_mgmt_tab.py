"""
Tweaks Management settings tab - port of settings_dialog.py's
_build_tweaks_tab / _edit_tweak_dialog / _test_tweak_script.

Note: this is a different tab from ui_qt/tweaks_tab.py (the main app's
Tweaks tab, which selects enable/disable actions on existing tweaks). This
one creates/edits/deletes the tweak *definitions* themselves.
"""
from __future__ import annotations
import os
import shutil
import threading

from ui_qt.thread_utils import run_on_main_thread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog, QDialog, QAbstractItemView, QTextEdit
)

SCRIPT_TYPES = ['ps1', 'bat', 'py', 'reg']


class ScriptEditDialog(QDialog):
    """Small popup for inline-editing a script's text content."""

    def __init__(self, parent, content: str):
        super().__init__(parent)
        self.setWindowTitle("Edit Script")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Edit Script Content (inline):"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(content)
        layout.addWidget(self.text_edit, stretch=1)
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def content(self) -> str:
        return self.text_edit.toPlainText().strip()


class TweakEditDialog(QDialog):
    def __init__(self, parent, config, tweak: dict | None = None):
        super().__init__(parent)
        self.config = config
        self.tweak = tweak
        self.enable_script = tweak.get('enable_script', '') if tweak else ''
        self.disable_script = tweak.get('disable_script', '') if tweak else ''

        self.setWindowTitle("Edit Tweak" if tweak else "Add Tweak")
        self.resize(520, 460)

        grid = QGridLayout(self)
        row = 0

        grid.addWidget(QLabel("Name:"), row, 0)
        self.name_edit = QLineEdit(tweak.get('name', '') if tweak else '')
        grid.addWidget(self.name_edit, row, 1)
        row += 1

        grid.addWidget(QLabel("Category:"), row, 0)
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        existing = sorted(set(t.get('category', '') for t in config.tweaks.get('tweaks', []) if t.get('category')))
        self.category_combo.addItems(existing)
        self.category_combo.setCurrentText(tweak.get('category', '') if tweak else '')
        grid.addWidget(self.category_combo, row, 1)
        row += 1

        grid.addWidget(QLabel("Description:"), row, 0)
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlainText(tweak.get('description', '') if tweak else '')
        self.desc_edit.setMaximumHeight(70)
        grid.addWidget(self.desc_edit, row, 1)
        row += 1

        grid.addWidget(QLabel("Script Type:"), row, 0)
        self.script_type_combo = QComboBox()
        self.script_type_combo.addItems(SCRIPT_TYPES)
        self.script_type_combo.setCurrentText(tweak.get('script_type', 'ps1') if tweak else 'ps1')
        grid.addWidget(self.script_type_combo, row, 1)
        row += 1

        grid.addWidget(QLabel("Arguments:"), row, 0)
        self.args_edit = QLineEdit(tweak.get('arguments', '') if tweak else '')
        grid.addWidget(self.args_edit, row, 1)
        row += 1

        grid.addWidget(QLabel("Enable Script:"), row, 0)
        enable_row = QHBoxLayout()
        self.enable_preview = QLabel()
        self.enable_preview.setStyleSheet("border: 1px inset #999; padding: 2px;")
        enable_row.addWidget(self.enable_preview, stretch=1)
        edit_enable_btn = QPushButton("Edit\u2026")
        edit_enable_btn.clicked.connect(lambda: self._edit_script('enable'))
        enable_row.addWidget(edit_enable_btn)
        browse_enable_btn = QPushButton("Browse\u2026")
        browse_enable_btn.clicked.connect(lambda: self._browse_script('enable'))
        enable_row.addWidget(browse_enable_btn)
        grid.addLayout(enable_row, row, 1)
        row += 1

        grid.addWidget(QLabel("Disable Script:"), row, 0)
        disable_row = QHBoxLayout()
        self.disable_preview = QLabel()
        self.disable_preview.setStyleSheet("border: 1px inset #999; padding: 2px;")
        disable_row.addWidget(self.disable_preview, stretch=1)
        edit_disable_btn = QPushButton("Edit\u2026")
        edit_disable_btn.clicked.connect(lambda: self._edit_script('disable'))
        disable_row.addWidget(edit_disable_btn)
        browse_disable_btn = QPushButton("Browse\u2026")
        browse_disable_btn.clicked.connect(lambda: self._browse_script('disable'))
        disable_row.addWidget(browse_disable_btn)
        grid.addLayout(disable_row, row, 1)
        row += 1

        self._update_preview('enable')
        self._update_preview('disable')

        test_btn = QPushButton("Test Script")
        test_btn.clicked.connect(self._test_script)
        grid.addWidget(test_btn, row, 1)
        row += 1

        self.test_output = QLabel("")
        grid.addWidget(self.test_output, row, 0, 1, 2)
        row += 1

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        grid.addLayout(btn_row, row, 0, 1, 2)

    def _update_preview(self, which: str):
        text = self.enable_script if which == 'enable' else self.disable_script
        label = self.enable_preview if which == 'enable' else self.disable_preview
        if text:
            preview = text[:50] + ('...' if len(text) > 50 else '')
        else:
            preview = "(empty)"
        label.setText(preview)

    def _edit_script(self, which: str):
        current = self.enable_script if which == 'enable' else self.disable_script
        dlg = ScriptEditDialog(self, current)
        if dlg.exec() == QDialog.Accepted:
            if which == 'enable':
                self.enable_script = dlg.content()
            else:
                self.disable_script = dlg.content()
            self._update_preview(which)

    def _browse_script(self, which: str):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Script File", "",
            "Script files (*.ps1 *.bat *.cmd *.py *.reg);;All files (*.*)"
        )
        if not filename:
            return
        if which == 'enable':
            self.enable_script = filename
        else:
            self.disable_script = filename
        self._update_preview(which)
        ext = os.path.splitext(filename)[1].lower()
        ext_map = {'.ps1': 'ps1', '.bat': 'bat', '.cmd': 'bat', '.py': 'py', '.reg': 'reg'}
        if ext in ext_map:
            self.script_type_combo.setCurrentText(ext_map[ext])

    def _test_script(self):
        from modules.script_engine import ScriptEngine
        engine = ScriptEngine(self.config)

        script = self.enable_script or self.disable_script
        if not script:
            QMessageBox.critical(self, "Error", "No script to test (enable or disable) is defined.")
            return
        script_type = self.script_type_combo.currentText()
        arguments = self.args_edit.text().strip()

        self.test_output.setText("Running... (a new console window may open for interactive scripts)")

        def run_test():
            def log_cb(msg):
                pass  # console output already visible in the spawned window
            success, msg = engine.test_script(script, script_type, log_cb, arguments)

            def finish():
                if success:
                    self.test_output.setText("\u2705 SUCCESS")
                else:
                    self.test_output.setText(f"\u274c FAILED: {msg}")
            run_on_main_thread(finish)

        threading.Thread(target=run_test, daemon=True).start()

    def _copy_script_file(self, path: str, name: str, suffix: str) -> str:
        if not path:
            return path
        if os.path.isabs(path) and os.path.isfile(path):
            folder = os.path.join(self.config.base_dir, 'tweaks', name)
            os.makedirs(folder, exist_ok=True)
            ext = os.path.splitext(path)[1]
            dest = os.path.join(folder, f"script_{suffix}{ext}")
            shutil.copy2(path, dest)
            return os.path.join('tweaks', name, f"script_{suffix}{ext}")
        return path

    def _save(self):
        description = self.desc_edit.toPlainText().strip()
        data = {
            'name': self.name_edit.text().strip(),
            'category': self.category_combo.currentText().strip(),
            'description': description,
            'script_type': self.script_type_combo.currentText(),
            'arguments': self.args_edit.text().strip(),
            'enable_script': self.enable_script.strip(),
            'disable_script': self.disable_script.strip(),
            'enabled': False,
        }
        if not data['name']:
            QMessageBox.critical(self, "Error", "Name is required")
            return
        if self.tweak:
            data['enabled'] = self.tweak.get('enabled', False)

        data['enable_script'] = self._copy_script_file(data['enable_script'], data['name'], 'enable')
        data['disable_script'] = self._copy_script_file(data['disable_script'], data['name'], 'disable')

        tweaks_list = self.config.tweaks.get('tweaks', [])
        if self.tweak:
            for i, t in enumerate(tweaks_list):
                if t.get('name') == self.tweak.get('name'):
                    tweaks_list[i] = data
                    break
        else:
            if any(t.get('name') == data['name'] for t in tweaks_list):
                QMessageBox.critical(self, "Error", "Tweak with this name already exists.")
                return
            tweaks_list.append(data)

        self.config.tweaks['tweaks'] = tweaks_list
        self.config.save_tweaks()
        self.accept()


class TweaksManagementTab(QWidget):
    def __init__(self, config, on_saved, parent=None):
        super().__init__(parent)
        self.config = config
        self.on_saved = on_saved  # called after any change, so the main Tweaks tab refreshes too

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Script Type", "Category"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        layout.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Tweak")
        add_btn.clicked.connect(self._add_tweak)
        btn_row.addWidget(add_btn)
        edit_btn = QPushButton("Edit Tweak")
        edit_btn.clicked.connect(self._edit_tweak)
        btn_row.addWidget(edit_btn)
        delete_btn = QPushButton("Delete Tweak")
        delete_btn.clicked.connect(self._delete_tweak)
        btn_row.addWidget(delete_btn)
        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._move_up)
        btn_row.addWidget(move_up_btn)
        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._move_down)
        btn_row.addWidget(move_down_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self):
        self.config.tweaks = self.config._load_json(self.config.tweaks_file)
        self.table.setRowCount(0)
        for tweak in self.config.tweaks.get('tweaks', []):
            script_type = "Built-in" if tweak.get('is_builtin', False) else tweak.get('script_type', 'ps1').upper()
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate([tweak.get('name', ''), tweak.get('description', ''),
                                          script_type, tweak.get('category', '')]):
                self.table.setItem(row, col, QTableWidgetItem(value))

    def _selected_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _find_tweak(self, name: str) -> dict | None:
        return next((t for t in self.config.tweaks.get('tweaks', []) if t.get('name') == name), None)

    def _add_tweak(self):
        dlg = TweakEditDialog(self, self.config, tweak=None)
        if dlg.exec() == QDialog.Accepted:
            self._refresh()
            if self.on_saved:
                self.on_saved()

    def _edit_tweak(self):
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "No Selection", "Please select a tweak to edit.")
            return
        tweak = self._find_tweak(name)
        if not tweak:
            return
        if tweak.get('is_builtin', False):
            QMessageBox.information(self, "Info", "Built-in tweaks cannot be edited.")
            return
        dlg = TweakEditDialog(self, self.config, tweak=tweak)
        if dlg.exec() == QDialog.Accepted:
            self._refresh()
            if self.on_saved:
                self.on_saved()

    def _delete_tweak(self):
        name = self._selected_name()
        if not name:
            return
        tweak = self._find_tweak(name)
        if tweak and tweak.get('is_builtin', False):
            QMessageBox.information(self, "Info", "Built-in tweaks cannot be deleted.")
            return
        if QMessageBox.question(self, "Confirm Delete", "Delete selected tweak?") == QMessageBox.Yes:
            tweaks_list = self.config.tweaks.get('tweaks', [])
            self.config.tweaks['tweaks'] = [t for t in tweaks_list if t.get('name') != name]
            self.config.save_tweaks()
            self._refresh()
            if self.on_saved:
                self.on_saved()

    def _move_up(self):
        row = self.table.currentRow()
        if row <= 0:
            return
        tweaks_list = self.config.tweaks.get('tweaks', [])
        tweaks_list[row], tweaks_list[row - 1] = tweaks_list[row - 1], tweaks_list[row]
        self.config.tweaks['tweaks'] = tweaks_list
        self.config.save_tweaks()
        self._refresh()
        self.table.setCurrentCell(row - 1, 0)
        if self.on_saved:
            self.on_saved()

    def _move_down(self):
        row = self.table.currentRow()
        tweaks_list = self.config.tweaks.get('tweaks', [])
        if row < 0 or row >= len(tweaks_list) - 1:
            return
        tweaks_list[row], tweaks_list[row + 1] = tweaks_list[row + 1], tweaks_list[row]
        self.config.tweaks['tweaks'] = tweaks_list
        self.config.save_tweaks()
        self._refresh()
        self.table.setCurrentCell(row + 1, 0)
        if self.on_saved:
            self.on_saved()
