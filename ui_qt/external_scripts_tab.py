"""
External Scripts tab - port of gui_main.py's _build_external_tab and
handlers. These scripts are per-session only (not persisted to config),
matching the original self.external_scripts list living on the GUI object.
"""
from __future__ import annotations
import os
import threading
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QMessageBox, QAbstractItemView, QDialog,
    QTextEdit, QComboBox, QFileDialog, QGridLayout, QDialogButtonBox
)

from ui_qt.busy_tracker import BusyMixin

COLUMNS = ["", "Name", "Type", "Source", "Description"]
SCRIPT_TYPES = ['ps1', 'bat', 'cmd', 'reg', 'py']


class TextScriptDialog(QDialog):
    """Add/Edit Text Script popup, ported from _add_external_text_script /
    _edit_external_script."""

    def __init__(self, parent, title: str, initial: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 400)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Script Content:"))
        self.text_edit = QTextEdit()
        if initial:
            self.text_edit.setPlainText(initial.get('content', ''))
        layout.addWidget(self.text_edit, stretch=1)

        grid = QGridLayout()
        grid.addWidget(QLabel("Name:"), 0, 0)
        self.name_edit = QLineEdit(initial.get('name', '') if initial else '')
        grid.addWidget(self.name_edit, 0, 1)
        grid.addWidget(QLabel("Type:"), 0, 2)
        self.type_combo = QComboBox()
        self.type_combo.addItems(SCRIPT_TYPES)
        if initial:
            idx = self.type_combo.findText(initial.get('type', 'ps1'))
            self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        grid.addWidget(self.type_combo, 0, 3)
        grid.addWidget(QLabel("Description:"), 1, 0)
        self.desc_edit = QLineEdit(initial.get('description', '') if initial else '')
        grid.addWidget(self.desc_edit, 1, 1, 1, 3)
        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.result_data = None

    def _on_ok(self):
        content = self.text_edit.toPlainText().strip()
        if not content:
            QMessageBox.critical(self, "Error", "Script content cannot be empty.")
            return
        self.result_data = {
            'name': self.name_edit.text().strip() or "Inline Script",
            'type': self.type_combo.currentText(),
            'content': content,
            'source': 'Text',
            'description': self.desc_edit.text().strip() or "Inline script",
        }
        self.accept()


class ExternalScriptsTab(QWidget, BusyMixin):
    def __init__(self, config, log_bus, parent=None):
        super().__init__(parent)
        self.config = config
        self.log_bus = log_bus
        self.external_scripts: list[dict] = []

        self._build_ui()
        self._init_busy([self.run_btn])

    def _log(self, text: str):
        self.log_bus.log(text)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._refresh)
        top.addWidget(self.search_edit)
        top.addStretch(1)
        layout.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.setColumnWidth(0, 30)
        self.tree.setColumnWidth(1, 150)
        self.tree.setColumnWidth(2, 50)
        self.tree.setColumnWidth(3, 60)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree, stretch=1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Script")
        add_btn.clicked.connect(self._add_script)
        btn_row.addWidget(add_btn)
        add_text_btn = QPushButton("Add Text Script")
        add_text_btn.clicked.connect(self._add_text_script)
        btn_row.addWidget(add_text_btn)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_script)
        btn_row.addWidget(edit_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_script)
        btn_row.addWidget(remove_btn)
        up_btn = QPushButton("Move Up")
        up_btn.clicked.connect(self._move_up)
        btn_row.addWidget(up_btn)
        down_btn = QPushButton("Move Down")
        down_btn.clicked.connect(self._move_down)
        btn_row.addWidget(down_btn)
        run_btn = QPushButton("Run Selected")
        run_btn.clicked.connect(self._run_selected)
        btn_row.addWidget(run_btn)
        self.run_btn = run_btn
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self, *_):
        self.tree.clear()
        search = self.search_edit.text().strip().lower()
        for idx, script in enumerate(self.external_scripts):
            name = script.get('name', '')
            if search and search not in name.lower():
                continue
            check = "\u2611" if script.get('enabled', False) else "\u2610"
            item = QTreeWidgetItem([check, name, script.get('type', ''),
                                     script.get('source', ''), script.get('description', '')])
            item.setData(0, Qt.UserRole, idx)
            self.tree.addTopLevelItem(item)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        if column != 0:
            return
        idx = item.data(0, Qt.UserRole)
        if idx is None:
            return
        self.external_scripts[idx]['enabled'] = not self.external_scripts[idx]['enabled']
        self._refresh()

    def _add_script(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Script File", "",
            "Script files (*.ps1 *.bat *.cmd *.py *.reg);;All files (*.*)"
        )
        if not filename:
            return
        ext = os.path.splitext(filename)[1].lower()
        type_map = {'.ps1': 'ps1', '.bat': 'bat', '.cmd': 'cmd', '.py': 'py', '.reg': 'reg'}
        script_type = type_map.get(ext, 'ps1')
        name = os.path.basename(filename)
        self.external_scripts.append({
            'name': name, 'type': script_type, 'content': filename,
            'source': 'File', 'description': f"File: {name}", 'enabled': False
        })
        self._refresh()

    def _add_text_script(self):
        dlg = TextScriptDialog(self, "Add Text Script")
        if dlg.exec() == QDialog.Accepted and dlg.result_data:
            data = dlg.result_data
            data['enabled'] = False
            self.external_scripts.append(data)
            self._refresh()

    def _selected_index(self) -> int | None:
        item = self.tree.currentItem()
        if not item:
            return None
        return item.data(0, Qt.UserRole)

    def _edit_script(self):
        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "No Selection", "Please select a script to edit.")
            return
        script = self.external_scripts[idx]
        dlg = TextScriptDialog(self, "Edit Script", initial=script)
        if dlg.exec() == QDialog.Accepted and dlg.result_data:
            data = dlg.result_data
            data['enabled'] = script.get('enabled', False)
            self.external_scripts[idx] = data
            self._refresh()

    def _remove_script(self):
        idx = self._selected_index()
        if idx is None:
            return
        del self.external_scripts[idx]
        self._refresh()

    def _move_up(self):
        idx = self._selected_index()
        if idx is None or idx <= 0:
            return
        self.external_scripts[idx], self.external_scripts[idx - 1] = \
            self.external_scripts[idx - 1], self.external_scripts[idx]
        self._refresh()

    def _move_down(self):
        idx = self._selected_index()
        if idx is None or idx >= len(self.external_scripts) - 1:
            return
        self.external_scripts[idx], self.external_scripts[idx + 1] = \
            self.external_scripts[idx + 1], self.external_scripts[idx]
        self._refresh()

    def _run_selected(self):
        if self.is_busy():
            QMessageBox.information(self, "Busy", "External scripts are already running.")
            return

        checked = self.get_checked_scripts()
        if not checked:
            QMessageBox.information(self, "No Selection", "No scripts are checked.")
            return

        self._set_busy(True)

        def task():
            from modules.script_engine import ScriptEngine
            engine = ScriptEngine(self.config)

            def log_cb(msg):
                self._log(f"[External Script] {msg}\n")

            self._log("Running selected external scripts...\n")
            for script in checked:
                name = script.get('name', 'Unnamed')
                script_type = script.get('type', 'ps1')
                content = script.get('content', '')
                self._log(f"Running: {name} ({script_type})\n")
                success, msg = engine.test_script(content, script_type, log_cb, arguments='')
                if success:
                    self._log(f"\u2705 {name}: OK\n")
                else:
                    self._log(f"\u274c {name}: {msg}\n")

            self._set_busy_threadsafe(False)

        threading.Thread(target=task, daemon=True).start()

    # ---------------- public getter ----------------
    def get_checked_scripts(self) -> list[dict]:
        return [s for s in self.external_scripts if s.get('enabled', False)]

    def get_all_scripts(self) -> list[dict]:
        return self.external_scripts[:]

    def apply_scripts(self, scripts: list[dict]):
        self.external_scripts = scripts
        self._refresh()
