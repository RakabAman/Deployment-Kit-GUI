"""
Settings dialog - Qt port of settings_dialog.py's SettingsDialog. Assembles
the six sub-tabs into one QTabWidget-based dialog, in the same order the
Tkinter version's notebook uses.
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QPushButton, QHBoxLayout

from ui_qt.settings_general_tabs import GeneralSettingsTab, OperationsSettingsTab, CommandTemplatesTab
from ui_qt.settings_apps_tab import AppManagementTab
from ui_qt.settings_tweaks_mgmt_tab import TweaksManagementTab
from ui_qt.settings_activators_mgmt_tab import ActivatorsManagementTab


class SettingsDialog(QDialog):
    def __init__(self, win):
        """win: the MainWindow, so changes here can refresh the live tabs
        (main_tab's operations list, tweaks_tab, activators_tab)."""
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Settings")
        self.resize(850, 650)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs, stretch=1)

        tabs.addTab(GeneralSettingsTab(win.config), "General")
        tabs.addTab(AppManagementTab(win.config, win.catalog), "App Management")
        tabs.addTab(TweaksManagementTab(win.config, on_saved=self._on_tweaks_changed), "Tweaks Management")
        tabs.addTab(ActivatorsManagementTab(win.config, on_saved=self._on_activators_changed), "Activators Management")
        tabs.addTab(OperationsSettingsTab(win.config, on_saved=self._on_operations_changed), "Operations")
        tabs.addTab(CommandTemplatesTab(win.config), "Command Templates")

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_operations_changed(self):
        self.win.main_tab.refresh_operations_from_config()

    def _on_tweaks_changed(self):
        self.win.tweaks_tab._refresh()

    def _on_activators_changed(self):
        self.win.activators_tab._refresh()
