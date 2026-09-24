"""
Look and feel for Deployment Kit (PySide6).

One token dict (DEFAULT) drives one QSS template - kept as tokens rather
than a hand-written stylesheet so individual colors/spacing are easy to
tweak later without hunting through CSS. Dark by default.

Usage:
    from ui_qt.theme import get_qss
    app.setStyleSheet(get_qss())
"""

from __future__ import annotations
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Tokens:
    # Base surfaces
    bg: str
    bg_elevated: str        # cards/panels/dialogs
    bg_input: str            # text fields, table cells, lists, log panels
    border: str
    border_strong: str

    # Text
    text: str
    text_muted: str
    text_disabled: str

    # Brand / interactive
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str          # text color ON TOP of accent (contrast)

    # Semantic
    success: str
    warning: str
    danger: str

    # Table / list
    row_alt: str
    row_selected: str
    row_selected_text: str
    header_bg: str

    # Checkboxes / indicators
    indicator_bg: str
    indicator_border: str
    indicator_checked_bg: str
    indicator_checked_border: str
    indicator_check_mark: str

    # Sizing (shared across themes but still tokens, so a differently-sized
    # theme could override just these later without touching color logic)
    radius: str = "6px"
    font_size: str = "13px"
    font_family: str = "Segoe UI, -apple-system, sans-serif"


DEFAULT = Tokens(
    bg="#1e1f22",
    bg_elevated="#26282b",
    bg_input="#2b2d31",
    border="#3a3c40",
    border_strong="#53565c",
    text="#e6e6e6",
    text_muted="#a3a6ab",
    text_disabled="#6b6e73",
    accent="#4f8cff",
    accent_hover="#699bff",
    accent_pressed="#3b6fd6",
    accent_text="#0e1116",
    success="#3fb950",
    warning="#d29922",
    danger="#f85149",
    row_alt="#2a2c30",
    row_selected="#3a5a8c",
    row_selected_text="#ffffff",
    header_bg="#2b2d31",
    indicator_bg="#2b2d31",
    indicator_border="#7a7d84",
    indicator_checked_bg="#4f8cff",
    indicator_checked_border="#4f8cff",
    indicator_check_mark="#0e1116",
)

# The template. {token} is filled in from a Tokens instance's field values.
_QSS_TEMPLATE = """
* {{
    font-family: {font_family};
    font-size: {font_size};
    color: {text};
}}

QMainWindow, QDialog, QWidget {{
    background: {bg};
    color: {text};
}}

QWidget#Card, QFrame#Card {{
    background: {bg_elevated};
    border: 1px solid {border};
    border-radius: {radius};
}}

QLabel {{
    background: transparent;
    color: {text};
}}

QLabel[role="muted"] {{
    color: {text_muted};
}}

QLabel[role="heading"] {{
    font-weight: 600;
    font-size: calc({font_size});
}}

QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: {radius};
    background: {bg_elevated};
    top: -1px;
}}

QTabBar::tab {{
    background: transparent;
    color: {text_muted};
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}}

QTabBar::tab:selected {{
    color: {text};
    border-bottom: 2px solid {accent};
}}

QTabBar::tab:hover:!selected {{
    color: {text};
}}

QPushButton {{
    background: {bg_elevated};
    color: {text};
    border: 1px solid {border_strong};
    border-radius: {radius};
    padding: 6px 14px;
}}

QPushButton:hover {{
    border-color: {accent};
}}

QPushButton:pressed {{
    background: {row_alt};
}}

QPushButton:disabled {{
    color: {text_disabled};
    border-color: {border};
}}

QPushButton#Primary {{
    background: {accent};
    border: 1px solid {accent};
    color: {accent_text};
    font-weight: 600;
}}

QPushButton#Primary:hover {{
    background: {accent_hover};
}}

QPushButton#Primary:pressed {{
    background: {accent_pressed};
}}

QPushButton#Danger {{
    color: {danger};
    border-color: {danger};
}}

QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {{
    background: {bg_input};
    color: {text};
    border: 1px solid {border};
    border-radius: {radius};
    padding: 5px 8px;
    selection-background-color: {accent};
    selection-color: {accent_text};
}}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {accent};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background: {bg_input};
    color: {text};
    selection-background-color: {row_selected};
    selection-color: {row_selected_text};
    border: 1px solid {border};
    outline: none;
}}

QHeaderView::section {{
    background: {header_bg};
    color: {text_muted};
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border};
    font-weight: 600;
}}

QListWidget, QTableView, QTreeView, QTableWidget, QTreeWidget {{
    background: {bg_elevated};
    color: {text};
    alternate-background-color: {row_alt};
    gridline-color: {border};
    border: 1px solid {border};
    border-radius: {radius};
    selection-background-color: {row_selected};
    selection-color: {row_selected_text};
    outline: none;
}}

QListWidget::item {{
    padding: 4px 6px;
}}

QListWidget::item:selected {{
    background: {row_selected};
    color: {row_selected_text};
}}

QListWidget::item:hover {{
    background: {row_alt};
}}

QTableView::item, QTreeView::item, QTableWidget::item, QTreeWidget::item {{
    padding: 4px 6px;
    border: none;
}}

QTableView::item:selected, QTreeView::item:selected,
QTableWidget::item:selected, QTreeWidget::item:selected {{
    background: {row_selected};
    color: {row_selected_text};
}}

/* Checkbox indicators - both standalone QCheckBox and checkable cells in
   trees/tables/lists. Styled explicitly because the default OS indicator
   can render invisibly (dark-on-dark) once the rest of the app is themed. */
QCheckBox {{
    color: {text};
    spacing: 6px;
}}

QCheckBox::indicator,
QTreeView::indicator, QTableView::indicator,
QTreeWidget::indicator, QTableWidget::indicator,
QListWidget::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {indicator_border};
    border-radius: 3px;
    background: {indicator_bg};
}}

QCheckBox::indicator:hover,
QTreeView::indicator:hover, QTableView::indicator:hover,
QTreeWidget::indicator:hover, QTableWidget::indicator:hover {{
    border-color: {accent};
}}

QCheckBox::indicator:checked,
QTreeView::indicator:checked, QTableView::indicator:checked,
QTreeWidget::indicator:checked, QTableWidget::indicator:checked,
QListWidget::indicator:checked {{
    background: {indicator_checked_bg};
    border-color: {indicator_checked_border};
    image: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {border_strong};
    min-height: 24px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical:hover {{
    background: {text_muted};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {border_strong};
    min-width: 24px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {text_muted};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QStatusBar {{
    background: {header_bg};
    border-top: 1px solid {border};
    color: {text_muted};
}}

QMenuBar {{
    background: {bg_elevated};
    color: {text};
    border-bottom: 1px solid {border};
}}

QMenuBar::item:selected {{
    background: {row_alt};
}}

QMenu {{
    background: {bg_elevated};
    color: {text};
    border: 1px solid {border};
}}

QMenu::item:selected {{
    background: {accent};
    color: {accent_text};
}}

QGroupBox {{
    color: {text};
    border: 1px solid {border};
    border-radius: {radius};
    margin-top: 8px;
    padding-top: 8px;
}}

QToolTip {{
    background: {bg_elevated};
    color: {text};
    border: 1px solid {border_strong};
    padding: 3px 6px;
}}

/* Semantic badges - set dynamicProperty "state" to success|warning|danger */
QLabel[state="success"] {{ color: {success}; font-weight: 600; }}
QLabel[state="warning"] {{ color: {warning}; font-weight: 600; }}
QLabel[state="danger"]  {{ color: {danger};  font-weight: 600; }}
"""


def get_qss() -> str:
    values = {f.name: getattr(DEFAULT, f.name) for f in fields(DEFAULT)}
    return _QSS_TEMPLATE.format(**values)
