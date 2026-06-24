@echo off
REM ============================================================
REM build_clean.bat
REM Builds Deployment Kit as a single EXE without including
REM the JSON configuration files. The app will create default
REM JSON files on first run.
REM Output: Deployment_Kit_GUI_Clean.exe
REM ============================================================

echo Building Deployment Kit (clean - no JSON files included)...

REM Remove previous build artifacts (optional)
Rem if exist "build" rmdir /s /q build
rem if exist "dist" rmdir /s /q dist
if exist "*.spec" del /q *.spec

REM PyInstaller command
py -m PyInstaller --onefile ^
            --windowed ^
            --name "Deployment_Kit_GUI_Clean" ^
            --add-data "modules;modules" ^
            --hidden-import tkinter ^
            --hidden-import tkinter.ttk ^
            --hidden-import tkinter.scrolledtext ^
            --hidden-import tkinter.filedialog ^
            --hidden-import tkinter.messagebox ^
            --hidden-import tkinter.simpledialog ^
            main.py

echo.
echo Build complete. The executable is in the "dist" folder.
pause