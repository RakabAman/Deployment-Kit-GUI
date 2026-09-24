"""
BusyMixin - shared "is a background operation running on this tab" tracking.

Used by every tab that spawns a background thread (Backup/Restore, Tweaks,
Activators, External Scripts) so that:
  1. The button that started the operation disables itself, so a second
     click can't start a second overlapping run.
  2. MainWindow's closeEvent can check across all tabs whether anything is
     still running before warning the user on close - not just
     install_engine.is_running(), which only covers a Deploy run.

Plain mixin, not a QObject - just adds state and two methods to whatever
QWidget subclass uses it (e.g. class BackupTab(QWidget, BusyMixin)).
"""
from ui_qt.thread_utils import run_on_main_thread


class BusyMixin:
    def _init_busy(self, buttons: list):
        """buttons: the widgets to disable while busy (typically the button(s)
        that start a background operation on this tab)."""
        self._busy = False
        self._busy_buttons = buttons

    def is_busy(self) -> bool:
        return getattr(self, '_busy', False)

    def _set_busy(self, busy: bool):
        self._busy = busy
        for b in self._busy_buttons:
            b.setEnabled(not busy)

    def _set_busy_threadsafe(self, busy: bool):
        """Same as _set_busy, but safe to call from a background thread -
        use this from inside the thread's target function."""
        run_on_main_thread(lambda: self._set_busy(busy))
