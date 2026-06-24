@echo off
REM ============================================================
REM build_with_json.bat
REM Builds Deployment Kit as a single EXE and embeds all
REM existing JSON configuration files (settings, apps, backup,
REM tweaks, activators) into the executable.
REM Output: Deployment_Kit_GUI_Json.exe
REM ============================================================

echo Building Deployment Kit (with JSON configuration files)...

REM Remove previous build artifacts
rem if exist "build" rmdir /s /q build
rem if exist "dist" rmdir /s /q dist
if exist "*.spec" del /q *.spec

REM PyInstaller command (JSON files explicitly listed)
py -m PyInstaller --onefile ^
            --windowed ^
            --name "Deployment_Kit_GUI_Json" ^
            --add-data "modules;modules" ^
            --add-data "settings.json;." ^
            --add-data "apps.json;." ^
            --add-data "backup.json;." ^
            --add-data "tweaks.json;." ^
            --add-data "activators.json;." ^
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