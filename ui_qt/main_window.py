from __future__ import annotations
import os
import sys

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QLabel, QStatusBar, QMessageBox
)
from PySide6.QtGui import QAction, QCloseEvent

from ui_qt.theme import get_qss
from ui_qt.apps_tab import AppsTab
from ui_qt.main_tab import MainTab
from ui_qt.backup_tab import BackupTab
from ui_qt.tweaks_tab import TweaksTab
from ui_qt.activators_tab import ActivatorsTab
from ui_qt.external_scripts_tab import ExternalScriptsTab
from ui_qt.log_bus import LogBus
from ui_qt.app_context import AppContext
from ui_qt.profile_dialog import ManageProfilesDialog
from ui_qt.settings_dialog import SettingsDialog

from modules.config_manager import ConfigManager
from modules.app_catalog import AppCatalog
from modules.backup_engine import BackupEngine
from modules.install_engine import InstallEngine
from modules.profile_manager import ProfileManager


class MainWindow(QMainWindow):
    def __init__(self, base_dir: str, is_admin: bool = False):
        super().__init__()
        self.setWindowTitle("Deployment Kit v1.0")
        self.resize(1150, 780)
        self.setStyleSheet(get_qss())
        self.is_admin = is_admin

        # ---- real backend, same objects gui_main.py (Tkinter) uses ----
        self.config = ConfigManager(base_dir=base_dir)
        self.catalog = AppCatalog(self.config)
        self.catalog.refresh()
        self.backup_engine = BackupEngine(self.config)
        self.install_engine = InstallEngine(self.catalog, self.backup_engine, self.config)
        self.profile_manager = ProfileManager(self.config.base_dir)
        self.log_bus = LogBus()

        self._build_menu()
        self._build_tabs()
        self._build_status_bar()

    # ---------------- menu ----------------
    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        manage_profiles_action = QAction("Manage Profiles\u2026", self)
        manage_profiles_action.triggered.connect(self._open_manage_profiles)
        file_menu.addAction(manage_profiles_action)
        if not self.is_admin:
            file_menu.addSeparator()
            relaunch = QAction("Relaunch as Administrator\u2026", self)
            relaunch.triggered.connect(self._relaunch_as_admin)
            file_menu.addAction(relaunch)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        settings_menu = menubar.addMenu("&Settings")
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings)
        settings_menu.addAction(settings_action)

    def _open_manage_profiles(self):
        ManageProfilesDialog(self).exec()

    def _relaunch_as_admin(self):
        """Relaunches the app elevated via the standard UAC 'runas' verb.
        Opt-in rather than a forced startup prompt - see gui_main.py's
        _relaunch_as_admin for why (winget can work worse when elevated)."""
        proceed = QMessageBox.question(
            self, "Relaunch as Administrator",
            "Chocolatey installs typically need this (they fail writing to system folders "
            "without it).\n\n"
            "Note: testing has shown winget can sometimes work worse when this app is "
            "already elevated (an installer's own permission prompt can get silently "
            "cancelled) - if you're only using winget, non-elevated may actually work "
            "better.\n\n"
            "Relaunch as Administrator now? This will close the current window."
        )
        if proceed != QMessageBox.Yes:
            return
        try:
            import ctypes
            if getattr(sys, 'frozen', False):
                executable, params = sys.executable, ''
            else:
                python_dir = os.path.dirname(sys.executable)
                pythonw_path = os.path.join(python_dir, 'pythonw.exe')
                executable = pythonw_path if os.path.isfile(pythonw_path) else sys.executable
                params = ' '.join(f'"{a}"' for a in sys.argv)
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
            if result > 32:
                os._exit(0)
            else:
                QMessageBox.warning(self, "Couldn't Relaunch Elevated",
                                     "The elevation request didn't go through - continuing as-is.")
        except Exception as e:
            QMessageBox.warning(self, "Couldn't Relaunch Elevated", f"Couldn't relaunch elevated: {e}")

    def _open_settings(self):
        SettingsDialog(self).exec()

    def closeEvent(self, event: QCloseEvent):
        """Mirrors gui_main.py's _on_close: warn if anything is running,
        then force an unconditional process exit so no background thread
        (version-check pool, in-progress deployment, backup/restore, a
        tweak/activator/script run) can keep it alive."""
        try:
            busy_tabs = [
                name for name, tab in (
                    ("Backup/Restore", self.backup_tab),
                    ("Tweaks", self.tweaks_tab),
                    ("Activators", self.activators_tab),
                    ("External Scripts", self.external_tab),
                )
                if tab.is_busy()
            ]
            deploying = self.install_engine.is_running()

            if deploying or busy_tabs:
                if deploying:
                    what = "A deployment is currently running."
                else:
                    what = f"A background operation is running on: {', '.join(busy_tabs)}."
                reply = QMessageBox.question(
                    self, "Operation In Progress",
                    f"{what} Exit anyway?\n\n"
                    "Anything already started (an installer, a script) will keep running in the "
                    "background even after this window closes."
                )
                if reply != QMessageBox.Yes:
                    event.ignore()
                    return
        except Exception:
            pass
        event.accept()
        os._exit(0)

    # ---------------- tabs ----------------
    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.apps_tab = AppsTab(self.catalog.apps)
        self.backup_tab = BackupTab(self.config, self.backup_engine, self.log_bus)
        self.tweaks_tab = TweaksTab(self.config, self.log_bus)
        self.activators_tab = ActivatorsTab(self.config, self.log_bus)
        self.external_tab = ExternalScriptsTab(self.config, self.log_bus)

        context = AppContext(
            get_selected_activators=self.activators_tab.get_selected_activators,
            get_checked_external_scripts=self.external_tab.get_checked_scripts,
            get_restore_selected_only=self.backup_tab.get_restore_selected_only,
            get_checked_backup_sources=self.backup_tab.get_checked_sources,
            get_backup_filename=self.backup_tab.get_backup_filename,
        )
        self.main_tab = MainTab(self.config, self.catalog, self.install_engine,
                                 self.log_bus, self.is_admin, context)

        self.tabs.addTab(self.main_tab, "Main")
        self.tabs.addTab(self.apps_tab, "Apps")
        self.tabs.addTab(self.backup_tab, "Backup / Restore")
        self.tabs.addTab(self.tweaks_tab, "Tweaks")
        self.tabs.addTab(self.activators_tab, "Activators")
        self.tabs.addTab(self.external_tab, "External Scripts")

    # ---------------- status bar ----------------
    def _build_status_bar(self):
        bar = QStatusBar()
        self.setStatusBar(bar)
        status = "Administrator" if self.is_admin else "Lower Rights"
        self.elevation_label = QLabel(f"Running with: {status}")
        bar.addWidget(self.elevation_label)
