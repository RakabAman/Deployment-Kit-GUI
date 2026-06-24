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