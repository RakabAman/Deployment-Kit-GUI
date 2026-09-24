"""
Tweaks tab - port of gui_main.py's _build_tweaks_tab / _on_tweak_click /
_refresh_tweaks_tab / _apply_all_tweaks / _clear_all_tweaks.

Disable/Enable are two independent checkbox columns per row, but only one
can be active at a time per tweak (selecting one clears the other) - same
mutually-exclusive behavior as the Tkinter version.
"""
from __future__ import annotations
import threading
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QTreeWidget, QTreeWidgetItem, QPushButton, QMessageBox, QAbstractItemView,
    QHeaderView
)

from ui_qt.busy_tracker import BusyMixin

COLUMNS = ["Disable", "Enable", "Name", "Description", "Category", "Type"]


class TweaksTab(QWidget, BusyMixin):
    def __init__(self, config, log_bus, parent=None):
        super().__init__(parent)
        self.config = config
        self.log_bus = log_bus
        self._refreshing = False

        self._build_ui()
        self._init_busy([self.apply_btn])
        self._refresh()

    def _log(self, text: str):
        self.log_bus.log(text)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._refresh)
        top.addWidget(self.search_edit)
        top.addWidget(QLabel("Filter by Category:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All")
        self.filter_combo.currentTextChanged.connect(self._refresh)
        top.addWidget(self.filter_combo)
        top.addStretch(1)
        layout.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setAllColumnsShowFocus(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(0, 60)
        self.tree.setColumnWidth(1, 60)
        self.tree.setColumnWidth(2, 200)
        self.tree.setColumnWidth(3, 320)
        self.tree.setColumnWidth(4, 110)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, stretch=1)

        btn_row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Selected")
        self.apply_btn.clicked.connect(self._apply_all_tweaks)
        btn_row.addWidget(self.apply_btn)
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_all_tweaks)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

    def _refresh(self, *_):
        self._refreshing = True
        try:
            self.tree.clear()

            self.config.tweaks = self.config._load_json(self.config.tweaks_file)
            tweaks = self.config.tweaks.get('tweaks', [])

            categories = sorted(set(t.get('category', 'Uncategorized') for t in tweaks if t.get('category')))
            current_filter = self.filter_combo.currentText()
            self.filter_combo.blockSignals(True)
            self.filter_combo.clear()
            self.filter_combo.addItems(['All'] + categories)
            idx = self.filter_combo.findText(current_filter)
            self.filter_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.filter_combo.blockSignals(False)

            search_text = self.search_edit.text().strip().lower()
            filter_category = self.filter_combo.currentText()

            for tweak in tweaks:
                name = tweak.get('name', '')
                if search_text and search_text not in name.lower():
                    continue
                if filter_category != 'All' and tweak.get('category', '') != filter_category:
                    continue

                selected_action = tweak.get('selected_action', None)
                has_disable = bool(tweak.get('disable_script', '').strip())
                has_enable = bool(tweak.get('enable_script', '').strip())

                script_type = "Built-in" if tweak.get('is_builtin', False) else tweak.get('script_type', 'ps1').upper()

                item = QTreeWidgetItem(["", "", name, tweak.get('description', ''),
                                         tweak.get('category', ''), script_type])
                item.setData(2, Qt.UserRole, name)

                flags = item.flags()
                if has_disable:
                    item.setFlags(flags | Qt.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.Checked if selected_action == 'disable' else Qt.Unchecked)
                else:
                    item.setText(0, "\u2011")

                if has_enable:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(1, Qt.Checked if selected_action == 'enable' else Qt.Unchecked)
                else:
                    item.setText(1, "\u2011")

                self.tree.addTopLevelItem(item)
        finally:
            self._refreshing = False

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if self._refreshing or column not in (0, 1):
            return
        name = item.data(2, Qt.UserRole)
        tweaks_list = self.config.tweaks.get('tweaks', [])
        tweak = next((t for t in tweaks_list if t.get('name') == name), None)
        if not tweak:
            return

        if column == 0:
            if not tweak.get('disable_script', '').strip():
                QMessageBox.information(self, "Not Available", "This tweak has no disable script.")
                self._refresh()
                return
            current = tweak.get('selected_action')
            wants_checked = item.checkState(0) == Qt.Checked
            action = 'disable' if wants_checked else None
            if current == 'disable' and not wants_checked:
                action = None
        else:
            if not tweak.get('enable_script', '').strip():
                QMessageBox.information(self, "Not Available", "This tweak has no enable script.")
                self._refresh()
                return
            current = tweak.get('selected_action')
            wants_checked = item.checkState(1) == Qt.Checked
            action = 'enable' if wants_checked else None
            if current == 'enable' and not wants_checked:
                action = None

        tweak['selected_action'] = action
        self.config.tweaks['tweaks'] = tweaks_list
        self.config.save_tweaks()
        self._refresh()

    def _apply_all_tweaks(self):
        if self.is_busy():
            QMessageBox.information(self, "Busy", "Tweaks are already being applied.")
            return

        from modules.script_engine import ScriptEngine

        tweaks = self.config.tweaks.get('tweaks', [])
        if not tweaks:
            self._log("No tweaks configured.\n")
            return

        selected_tweaks = [t for t in tweaks if t.get('selected_action')]
        if not selected_tweaks:
            self._log("No tweaks selected. Nothing to apply.\n")
            return

        self._set_busy(True)

        def task():
            engine = ScriptEngine(self.config)
            engine.load_tweaks()

            def log_cb(msg):
                self._log(f"[Tweaks] {msg}\n")

            self._log(f"Applying {len(selected_tweaks)} selected tweak actions...\n")
            success_count = fail_count = 0

            for tweak in selected_tweaks:
                name = tweak.get('name', 'Unnamed')
                action = tweak.get('selected_action')
                script_path = tweak.get(f'{action}_script', '')
                if not script_path:
                    self._log(f"\u26a0\ufe0f {name}: No {action} script defined (skipped)\n")
                    fail_count += 1
                    continue

                script_type = tweak.get('script_type', 'ps1')
                arguments = tweak.get('arguments', '')

                self._log(f"\u25b6\ufe0f {name}: Running {action} script...\n")
                success, msg = engine._run_script(script_path, script_type, log_cb,
                                                   tweak_name=name, arguments=arguments)
                if success:
                    self._log(f"\u2705 {name}: {action} script succeeded\n")
                    success_count += 1
                else:
                    self._log(f"\u274c {name}: {action} script failed: {msg}\n")
                    fail_count += 1

            self._log(f"Tweak actions completed: {success_count} succeeded, {fail_count} failed.\n")
            self._set_busy_threadsafe(False)

        threading.Thread(target=task, daemon=True).start()

    def _clear_all_tweaks(self):
        tweaks_list = self.config.tweaks.get('tweaks', [])
        for tweak in tweaks_list:
            tweak['selected_action'] = None
        self.config.tweaks['tweaks'] = tweaks_list
        self.config.save_tweaks()
        self._refresh()

    def apply_tweaks_state(self, tweaks_state: dict) -> list[str]:
        """Apply a saved {name: action} dict, persist, and refresh. Returns
        names present in the profile but not found in the current config."""
        tweaks_list = self.config.tweaks.get('tweaks', [])
        name_to_index = {t['name']: i for i, t in enumerate(tweaks_list)}
        missing = []
        for tweak_name, action in tweaks_state.items():
            if tweak_name in name_to_index:
                tweaks_list[name_to_index[tweak_name]]['selected_action'] = action
            else:
                missing.append(tweak_name)
        self.config.tweaks['tweaks'] = tweaks_list
        self.config.save_tweaks()
        self._refresh()
        return missing
