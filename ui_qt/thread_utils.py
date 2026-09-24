"""
run_on_main_thread(fn) - the correct replacement for the QTimer.singleShot(0,
fn) pattern that was used (incorrectly) throughout this codebase to marshal
work from a background thread back onto the GUI thread.

QTimer.singleShot only fires if the thread that calls it is running a Qt
event loop. A plain threading.Thread never runs one, so a timer scheduled
from inside one silently never fires - this is what caused the Deploy
button to stay disabled forever after a deployment finished (the
InstallEngine calls its on_finished callback from its own worker thread).

Qt's signal/slot connections, by contrast, are automatically queued onto the
receiver's thread when emitted from a different thread. A QObject created on
the GUI thread (as this module-level singleton is, since it's imported
during app startup before any worker thread exists) is exactly that
receiver, so emitting its signal from any thread safely and reliably
delivers the call to the GUI thread's event loop.
"""
from PySide6.QtCore import QObject, Signal


class _MainThreadInvoker(QObject):
    _invoke = Signal(object)

    def __init__(self):
        super().__init__()
        self._invoke.connect(self._run)

    def _run(self, fn):
        fn()


# Created at import time - this module is imported during app startup, on
# the GUI thread, before any deployment/download/test worker thread exists.
_invoker = _MainThreadInvoker()


def run_on_main_thread(fn):
    """Schedule fn() to run on the GUI thread. Safe to call from any thread,
    including the GUI thread itself (the call is still queued, so it runs
    on the next event-loop iteration rather than immediately - fine for the
    'deployment/download/test finished, now update the UI' use case this
    exists for)."""
    _invoker._invoke.emit(fn)
