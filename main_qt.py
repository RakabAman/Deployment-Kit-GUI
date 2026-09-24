"""
Entry point for the PySide6 rebuild of Deployment Kit.

Run from the repo root (same convention as main.py):
    python main_qt.py
"""
import os
import sys


def _enable_windows_dpi_awareness():
    """Must run before QApplication is created. Without this, Windows can
    report virtualized/scaled coordinates to the process, producing blurry
    text and controls on high-DPI displays (the app looking "off" or
    slightly fuzzy on a 4K/150%+ scaled monitor). PROCESS_PER_MONITOR_DPI_AWARE
    (2) is the modern per-monitor-aware mode; falls back to the older
    system-DPI-aware call if that's not available (older Windows builds)."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()  # older Windows fallback
    except Exception:
        pass  # never block startup over this


_enable_windows_dpi_awareness()

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui_qt.main_window import MainWindow


def main():
    # Crisp rendering at fractional scale factors (125%, 150%, etc.) instead
    # of Qt rounding to the nearest whole number and looking slightly blurry.
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = QApplication(sys.argv)
    app.setApplicationName("Deployment Kit")
    win = MainWindow(base_dir=base_dir)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
