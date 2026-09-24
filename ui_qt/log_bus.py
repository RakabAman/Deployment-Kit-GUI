"""
Every tab in the Tkinter version calls self.log_text_insert(...) into one
shared log panel that lives on the Main tab. Here that's a small QObject
signal bus, instantiated once in MainWindow and handed to every tab.

Qt automatically queues a signal emitted from a background thread onto the
receiving QObject's own thread (the main/GUI thread here), so this is safe
to emit directly from the plain threading.Thread workers the engines already
use - no extra QThread wrapper needed, mirroring the original architecture
where log_text_insert() marshals onto the Tk main loop via root.after(0, ...).
"""
from PySide6.QtCore import QObject, Signal


class LogBus(QObject):
    message = Signal(str)

    def log(self, text: str):
        self.message.emit(text)
