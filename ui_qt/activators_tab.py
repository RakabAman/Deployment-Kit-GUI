"""
Activators tab - port of gui_main.py's _build_activators_tab and handlers.
Unavailable activators (not found offline) are shown grayed-out and refuse
to be checked, same as the Tkinter version's 'unavailable' tag.
"""
from __future__ import annotations
import os
import threading
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QTreeWidget, QTreeWidgetItem, QPushButton, QMessageBox, QInputDialog,
    QAbstractItemView, QHeaderView
)

from ui_qt.busy_tracker import BusyMixin

COLUMNS = ["Select", "Name", "Description", "Switches", "Category"]


class ActivatorsTab(QWidget, BusyMixin):
    def __init__(self, config, log_bus, parent=None):
        super().__init__(parent)
        self.config = config
        self.log_bus = log_bus

        self._build_ui()
        self._init_busy([self.run_btn])
        self._refresh()

    def _log(self, text: str):
        self.log_bus.log(text)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        note = QLabel("\u26a0\ufe0f Only one activator can run at a time.")
        note.setProperty("role", "muted")
        layout.addWidget(note)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._refresh)
        filter_row.addWidget(self.search_edit)
        filter_row.addWidget(QLabel("Filter by Category:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All")
        self.filter_combo.currentTextChanged.connect(self._refresh)
        filter_row.addWidget(self.filter_combo)
        filter_row.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        filter_row.addWidget(refresh_btn)
        layout.addLayout(filter_row)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.setColumnWidth(0, 60)
        self.tree.setColumnWidth(1, 220)
        self.tree.setColumnWidth(2, 260)
        self.tree.setColumnWidth(3, 180)
        self.tree.itemDoubleClicked.connect(self._edit_switches)
        layout.addWidget(self.tree, stretch=1)

        btn_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        btn_row.addWidget(select_all_btn)
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(select_none_btn)
        self.run_btn = QPushButton("Run Selected")
        self.run_btn.clicked.connect(self._run_selected)
        btn_row.addWidget(self.run_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _refresh(self, *_):
        self.tree.clear()

        self.config.activators = self.config._load_json(self.config.activators_file)
        activators = self.config.activators.get('activators', [])

        categories = sorted(set(a.get('category', 'Uncategorized') for a in activators if a.get('category')))
        current_filter = self.filter_combo.currentText()
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItems(['All'] + categories)
        idx = self.filter_combo.findText(current_filter)
        self.filter_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.filter_combo.blockSignals(False)

        search_text = self.search_edit.text().strip().lower()
        filter_category = self.filter_combo.currentText()

        for act in activators:
            name = act.get('name', '')
            if search_text and search_text not in name.lower():
                continue
            if filter_category != 'All' and act.get('category', '') != filter_category:
                continue

            is_available = self._is_available(act)
            item = QTreeWidgetItem(["\u2610", name, act.get('description', ''),
                                     act.get('default_switches', ''), act.get('category', '')])
            item.setData(0, Qt.UserRole, {'available': is_available})
            if not is_available:
                gray = QBrush(QColor("#8a8a8a"))
                for col in range(len(COLUMNS)):
                    item.setForeground(col, gray)
            self.tree.addTopLevelItem(item)

    def _is_available(self, activator: dict) -> bool:
        exec_path = activator.get('executable', '')
        if not exec_path:
            return False

        archive = activator.get('archive', '')
        if archive:
            archive_path = os.path.join(self.config.base_dir, 'activators', archive)
            if os.path.isfile(archive_path):
                return True

        folder = activator.get('folder', '')
        if folder and os.path.isdir(folder):
            if os.path.isfile(os.path.join(folder, exec_path)):
                return True

        if os.path.isabs(exec_path) and os.path.isfile(exec_path):
            return True

        full_path = os.path.join(self.config.base_dir, 'activators', exec_path)
        if os.path.isfile(full_path):
            return True

        activators_dir = os.path.join(self.config.base_dir, 'activators')
        if os.path.isdir(activators_dir):
            for f in os.listdir(activators_dir):
                if f == exec_path:
                    return True
                for root, dirs, files in os.walk(activators_dir):
                    if exec_path in files:
                        return True
        return False

    def _item_available(self, item: QTreeWidgetItem) -> bool:
        data = item.data(0, Qt.UserRole) or {}
        return bool(data.get('available'))

    def _toggle(self, item: QTreeWidgetItem):
        if not self._item_available(item):
            QMessageBox.information(self, "Not Available",
                                     "This activator is not available offline. Download it first or use online mode.")
            return
        item.setText(0, "\u2611" if item.text(0) == "\u2610" else "\u2610")

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        super().mousePressEvent(event)

    def _edit_switches(self, item: QTreeWidgetItem, column: int):
        if column == 0:
            self._toggle(item)
            return
        if not self._item_available(item):
            QMessageBox.information(self, "Not Available",
                                     "This activator is not available offline. Download it first.")
            return
        name = item.text(1)
        current = item.text(3)
        text, ok = QInputDialog.getText(self, "Edit Switches", f"Enter switches for {name}:", text=current)
        if ok:
            item.setText(3, text)

    def _select_all(self):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if self._item_available(item):
                item.setText(0, "\u2611")

    def _select_none(self):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setText(0, "\u2610")

    def _run_selected(self):
        if self.is_busy():
            QMessageBox.information(self, "Busy", "An activator is already running.")
            return

        from modules.activator_engine import ActivatorEngine
        engine = ActivatorEngine(self.config)
        engine.load_activators()

        # Gather everything from the tree on the main thread first - Qt
        # widgets shouldn't be read from a background thread.
        selected = []
        for a, switches in self.get_selected_activators_raw():
            activator = next((x for x in engine.activators if x.get('name') == a), None)
            if activator:
                if not self._is_available(activator):
                    self._log(f"\u26a0\ufe0f {a}: Skipping - not available offline.\n")
                    continue
                selected.append((activator, switches))

        if not selected:
            QMessageBox.information(self, "No Selection", "Please select at least one available activator.")
            return

        self._set_busy(True)

        def task():
            def log_cb(msg):
                self._log(f"[Activator] {msg}\n")

            self._log("Running selected activators...\n")
            self._log("\u26a0\ufe0f Only one activator runs at a time.\n")

            results = engine.run_selected(selected, log_cb)
            for name, success, msg in results:
                if success:
                    self._log(f"\u2705 {name}: {msg}\n")
                else:
                    self._log(f"\u274c {name}: {msg}\n")

            self._set_busy_threadsafe(False)

        threading.Thread(target=task, daemon=True).start()

    # ---------------- public getters ----------------
    def get_selected_activators_raw(self) -> list[tuple[str, str]]:
        result = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.text(0) == "\u2611":
                result.append((item.text(1), item.text(3)))
        return result

    def get_selected_activators(self) -> list[dict]:
        """Used by MainTab's deploy flow: install_engine.set_selected_activators()."""
        return [{'name': name, 'switches': switches} for name, switches in self.get_selected_activators_raw()]

    def get_activators_state_for_save(self) -> dict:
        """name -> {'selected': bool, 'switches': str}, for rows that are
        either selected or have a non-default switches value. Mirrors the
        Tkinter version's profile-save logic exactly."""
        state = {}
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            name = item.text(1)
            selected = item.text(0) == "\u2611"
            switches = item.text(3)
            if selected or switches:
                state[name] = {'selected': selected, 'switches': switches}
        return state

    def apply_activators_state(self, state: dict) -> list[str]:
        """Apply a saved {name: {'selected','switches'}} dict onto the
        current tree (which was already rebuilt from the current activators
        config). Returns names present in the profile but not found here."""
        current_names = set()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            name = item.text(1)
            current_names.add(name)
            if name in state:
                entry = state[name]
                item.setText(0, "\u2611" if entry.get('selected') else "\u2610")
                item.setText(3, entry.get('switches', ''))
            else:
                item.setText(0, "\u2610")
        return [name for name in state.keys() if name not in current_names]
