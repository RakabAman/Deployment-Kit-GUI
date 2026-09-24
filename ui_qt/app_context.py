"""
AppContext - a bundle of getter callables MainTab uses to read state from the
Backup/Restore, Activators, and External Scripts tabs at deploy time (mirrors
how DeploymentGUI, being one big class in the Tkinter version, could just
reach into self.tree_activators / self.backup_tree_items / etc. directly).

MainWindow builds one of these after all tabs exist and hands it to MainTab.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class AppContext:
    get_selected_activators: Callable[[], list[dict]]
    get_checked_external_scripts: Callable[[], list[dict]]
    get_restore_selected_only: Callable[[], bool]
    get_checked_backup_sources: Callable[[], list[str]]
    get_backup_filename: Callable[[], str]
