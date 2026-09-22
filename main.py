#!/usr/bin/env python3
"""
Deployment Kit - Main Entry Point
Modern GUI-driven deployment tool for Windows.
"""

import sys
import os

# Add the current directory to Python's path so 'modules' can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


import ctypes
import tkinter as tk
from tkinter import messagebox
import threading
import queue
from modules.logger import setup_logging

# Import the main GUI class
from modules.gui_main import DeploymentGUI

def is_admin():
    """Check if the script is running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def relaunch_as_admin():
    """Re-launches this same process elevated via the standard Windows
    'runas' verb (triggers the normal UAC consent prompt). Returns True
    if the relaunch was *requested* successfully (the new elevated
    instance is starting up separately) - the caller should exit this
    (non-elevated) instance right after. Returns False if the relaunch
    itself couldn't be started, in which case the caller should continue
    running non-elevated rather than leave the user with no app at all."""
    try:
        if getattr(sys, 'frozen', False):
            executable, params = sys.executable, ''
        else:
            # sys.executable is normally python.exe when launched via
            # "py main.py" - python.exe always owns a console window, so
            # relaunching with it means a black console appears alongside
            # the GUI, and stays open even after the GUI window is closed
            # since it belongs to that separate process. pythonw.exe is
            # the windowless sibling every standard Python install ships
            # next to python.exe - use it when present so the elevated
            # relaunch has no console of its own at all.
            python_dir = os.path.dirname(sys.executable)
            pythonw_path = os.path.join(python_dir, 'pythonw.exe')
            executable = pythonw_path if os.path.isfile(pythonw_path) else sys.executable
            params = ' '.join(f'"{a}"' for a in sys.argv)
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
        # ShellExecuteW returns a value > 32 on success, per the Windows API.
        return result > 32
    except Exception:
        return False


def main():
    # Determine base directory (works for both script and EXE)
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # Setup logging FIRST
    setup_logging(base_dir)

    # Now check admin rights
    admin = is_admin()

    # NOTE: this used to force a blocking "relaunch as Administrator?"
    # dialog on every non-elevated launch. Real-machine testing changed
    # the picture: Chocolatey genuinely needs elevation (it fails writing
    # to ProgramData without it), but winget actually worked *worse*
    # elevated in testing - an installer's own UAC prompt got silently
    # auto-cancelled (exit 1602) specifically when this app was already
    # running elevated via a nested "runas" relaunch, and worked cleanly
    # non-elevated (a normal single-hop UAC prompt). Since there's no
    # single right answer for "should this app be elevated" that holds
    # for both tools, forcing the choice at every startup was actively
    # wrong for winget-only use and, per feedback, just one more
    # unwanted popup. Elevation is available on demand instead (File
    # menu > Relaunch as Administrator) for when a choco-heavy
    # deployment specifically needs it; the in-app warning before a
    # choco/winget operation still tells you at the point it's relevant.

    title = "Deployment Kit v1.0"
    if admin:
        title += " [Administrator]"
    else:
        title += " [Lower Rights]"

    # Initialize the root window
    root = tk.Tk()
    root.title(title)

    # Set icon if available (optional)
    # root.iconbitmap('icon.ico')

    # Create the main application
    app = DeploymentGUI(root, admin)

    # Run the GUI
    root.mainloop()

if __name__ == "__main__":
    main()