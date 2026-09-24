"""
Apps tab, rebuilt on QTableView + QAbstractTableModel.

Why this permanently fixes the Winget/Choco alignment problem the Tkinter
version had: the checkbox is a real Qt::ItemIsUserCheckable role rendered by
the view itself at a fixed position, completely independent of the version
string's length. There's no more "center a combined glyph+text string" hack
to get wrong.

Click behavior matches the original: clicking a provider's checkbox column
selects that provider for the row (only one provider selected at a time per
app) and unchecks the others - mirrors _on_app_click in gui_main.py.
"""

from __future__ import annotations
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QTableView,
    QPushButton, QLabel, QHeaderView, QAbstractItemView
)

COLUMNS = ["App Name", "Category", "Type", "Offline", "Winget", "Choco"]
PROVIDER_COL = {"Offline": 3, "Winget": 4, "Choco": 5}
PROVIDER_KEY = {3: "offline", 4: "winget", 5: "choco"}


def _available(app, provider: str) -> bool:
    if provider == "offline":
        return bool(app.is_offline_available and app.offline_path)
    if provider == "winget":
        return bool(app.winget_id)
    if provider == "choco":
        return bool(app.choco_id)
    return False


def _version(app, provider: str) -> str:
    if provider == "offline":
        return app.offline_version or ""
    if provider == "winget":
        return app._winget_version or ""
    if provider == "choco":
        return app._choco_version or ""
    return ""


class AppsTableModel(QAbstractTableModel):
    def __init__(self, apps: list, parent=None):
        super().__init__(parent)
        self.apps = apps

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.apps)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        col = index.column()
        if col in PROVIDER_KEY:
            app = self.apps[index.row()]
            provider = PROVIDER_KEY[col]
            if _available(app, provider):
                return base | Qt.ItemIsUserCheckable
        return base

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        app = self.apps[index.row()]
        col = index.column()

        if role == Qt.CheckStateRole and col in PROVIDER_KEY:
            provider = PROVIDER_KEY[col]
            if not _available(app, provider):
                return None
            return Qt.Checked if app.selected_provider == provider else Qt.Unchecked

        if role == Qt.DisplayRole:
            if col == 0:
                return app.display_name
            if col == 1:
                return app.category or "Uncategorized"
            if col == 2:
                return app.install_type.capitalize()
            if col in PROVIDER_KEY:
                provider = PROVIDER_KEY[col]
                if not _available(app, provider):
                    return "\u2011"  # non-breaking hyphen, same as original "not available"
                v = _version(app, provider)
                return f"  {v}" if v else ""  # checkbox already occupies the glyph slot

        if role == Qt.TextAlignmentRole:
            if col in (2,) or col in PROVIDER_KEY:
                return Qt.AlignVCenter | Qt.AlignLeft
            return Qt.AlignVCenter | Qt.AlignLeft

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() in PROVIDER_KEY:
            app = self.apps[index.row()]
            provider = PROVIDER_KEY[index.column()]
            new_state = Qt.CheckState(value)
            if new_state == Qt.Checked:
                app.selected_provider = provider
            else:
                if app.selected_provider == provider:
                    app.selected_provider = None
            # All three provider columns in this row may have changed
            # (checking one unchecks the others), so refresh the whole row.
            row = index.row()
            top_left = self.index(row, 3)
            bottom_right = self.index(row, 5)
            self.dataChanged.emit(top_left, bottom_right, [Qt.CheckStateRole])
            return True
        return False

    def refresh_row(self, row: int):
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))

    def refresh_all(self):
        self.beginResetModel()
        self.endResetModel()


TYPE_FILTER_MAP = {
    "All": "all",
    "Silent": "silent",
    "Non-Silent": "non_silent",
    "Driver": "driver",
}


class AppsFilterProxy(QSortFilterProxyModel):
    """Search text (app name) + install-type filter + category filter,
    mirroring the original Search box + 'Filter by Type' combo, plus a new
    'Filter by Category' combo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search = ""
        self._type_filter = "all"
        self._category_filter = "All"
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def set_search(self, text: str):
        self._search = text.strip().lower()
        self.invalidateFilter()

    def set_type_filter(self, type_name: str):
        self._type_filter = TYPE_FILTER_MAP.get(type_name, "all")
        self.invalidateFilter()

    def set_category_filter(self, category: str):
        self._category_filter = category
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        app = model.apps[source_row]
        if self._search and self._search not in app.display_name.lower():
            return False
        if self._type_filter != "all" and app.install_type != self._type_filter:
            return False
        if self._category_filter != "All" and (app.category or "Uncategorized") != self._category_filter:
            return False
        return True


class AppsTab(QWidget):
    def __init__(self, apps: list, parent=None):
        super().__init__(parent)

        self.model = AppsTableModel(apps, self)
        self.proxy = AppsFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # --- toolbar row: search + filter + check version ---
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter by app name\u2026")
        self.search_box.textChanged.connect(self.proxy.set_search)
        toolbar.addWidget(self.search_box, stretch=1)

        toolbar.addWidget(QLabel("Filter by Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["All", "Silent", "Non-Silent", "Driver"])
        self.type_combo.currentTextChanged.connect(self.proxy.set_type_filter)
        toolbar.addWidget(self.type_combo)

        toolbar.addWidget(QLabel("Filter by Category:"))
        self.category_combo = QComboBox()
        categories = sorted(set((a.category or "Uncategorized") for a in apps))
        self.category_combo.addItems(["All"] + categories)
        self.category_combo.currentTextChanged.connect(self.proxy.set_category_filter)
        toolbar.addWidget(self.category_combo)

        self.check_version_btn = QPushButton("Check Version")
        toolbar.addWidget(self.check_version_btn)

        layout.addLayout(toolbar)

        # --- table ---
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3, 4, 5):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 160)
        self.table.setColumnWidth(5, 160)

        layout.addWidget(self.table, stretch=1)
