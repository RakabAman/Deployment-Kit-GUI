# Deployment Kit

**Windows system provisioning made easy.**

Deployment Kit is a Python-based GUI tool that automates Windows system setup. It provides a clean, tabbed interface for:

- Installing applications (offline installers, Winget, Chocolatey)
- Managing backups and restores (ZIP/7z with support for special folders)
- Applying system tweaks with enable/disable scripts
- Running activators (e.g., MAS, KMS_VL_ALL)
- Executing temporary per‑session scripts

The tool runs entirely on Windows, requires administrator privileges for most operations, and is packaged as a portable executable.

---

## Features

### 🚀 Application Installation
- **Offline installers** – use your own `.exe`, `.msi`, or `.msix` files with custom switches.
- **Online package managers** – install apps via **Winget** or **Chocolatey**.
- **Post‑install scripts** – run PowerShell, Batch, Python, or REG scripts automatically after installation.
- **Version caching** – shows installed/available versions with a 5‑minute cache.

### 💾 Backup & Restore
- Backup user folders (Documents, Desktop, Downloads, or custom sources) into ZIP or 7z archives.
- Restore backups selectively – choose which folders to restore.
- Special system folders (e.g., `%SystemDrive%\Scripts`, `%SystemDrive%\PowerTools`) are automatically included and backed up to separate sub‑archives.
- Full integration with the deployment pipeline.

### ⚙️ System Tweaks
- Add, edit, and delete tweaks via the Settings dialog.
- Each tweak can have both an **Enable** and a **Disable** script (PowerShell, Batch, Python, REG).
- In the Tweaks tab, check either Enable or Disable (mutually exclusive) for each tweak.
- Run selected tweaks manually or include them in automated deployments.
- Built‑in tweaks for Custom Scripts and PowerTools are protected from accidental deletion.

### 🔑 Activators
- Run activation tools like **MAS** (Microsoft Activation Scripts) and **KMS_VL_ALL** with custom switches.
- Download activators directly from GitHub releases or URLs.
- Double‑click to edit switches per activator.
- Only one activator runs at a time to avoid conflicts.

### 📜 External Scripts (Temporary)
- Add scripts on‑the‑fly by browsing for a file or typing inline.
- Supported types: PowerShell, Batch, Python, REG.
- Reorder scripts with Move Up/Down.
- Run selected scripts immediately or include them in the deployment pipeline.
- Scripts are session‑only and are not saved to disk.

### 🧩 Orchestration
- Build a custom execution order by adding operations like:
  - Install Silent Apps
  - Install Winget/Chocolatey Apps
  - Install Drivers
  - Restore Backup
  - Apply Tweaks
  - Run Activators
  - Run External Scripts
- **Add All** / **Remove All** buttons for quick operation management.
- Live status panel showing current and next operation, with per‑step success/failure indicators.

### ⚙️ Full Configuration via GUI
- **Settings dialog** with tabs:
  - **App Management**: add/edit/delete apps, set offline paths, switches, versions, and download URLs.
  - **Tweaks Management**: add/edit/delete tweaks with inline script editing and browsing.
  - **Activators Management**: add/edit/delete activators with GitHub/URL download support.
  - **Command Templates**: customise command strings for Winget, Chocolatey, offline installers, and scripts.
  - **Operations**: enable/disable available deployment operations.
  - **General**: default provider, log level, archive format, backup destination.
- **Download Now** buttons in App/Activator management to fetch files directly from URLs or GitHub.

### 📦 Portability & Deployment
- Packaged as a single portable `.exe` using PyInstaller.
- JSON configuration files can be embedded at build time, or created on first run.
- When embedded, the app automatically copies bundled JSON files to the executable directory on first launch.

### 📝 Logging
- Detailed log output to both console and `deployment.log` file.
- Live log viewer in the Main tab.
- Status panel with colour‑coded icons (⏳ pending, ▶️ running, ✅ success, ❌ failed, ⏭️ skipped).

---

## Installation

### Option 1 – Pre‑compiled Executable
Download the latest `Deployment_Kit_GUI.exe` from the [Releases](https://github.com/yourusername/deployment-kit/releases) page.  
Run it as Administrator.

### Option 2 – From Source
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/deployment-kit.git
   cd deployment-kit

### Install dependencies:

```bash
pip install -r requirements.txt
```
(Requirements: tkinter – usually included with Python, py7zr for 7z support, pyinstaller for building)

### Run the application:

```bash
python main.py
```
##Building the Executable
Two batch files are provided in the root:

build_clean.bat – builds an EXE without embedding JSON files (defaults created on first run).

build_with_json.bat – builds an EXE that includes all *.json files.

Run the desired batch file from the project root.

##Usage
Launch as Administrator – right‑click the EXE and select "Run as administrator".

Add Apps (optional) – go to the Apps tab and select your preferred providers (Offline/Winget/Choco).

Set up Tweaks (optional) – go to the Tweaks tab and check Enable or Disable for each tweak.

Add Activators (optional) – download them via the Activators tab or Settings.

Add External Scripts (optional) – add temporary scripts in the External Scripts tab.

Build Execution Order – in the Main tab, add operations from the left list to the right list. Reorder with Move Up/Down.

Deploy – click the Deploy button. The status panel will show progress, and the detailed log will update in real time.

Cancel – click Cancel to stop the deployment after the current operation finishes.

##Configuration Files
All settings are stored in JSON files in the same directory as the executable (or source folder):

settings.json – general settings, command templates, and available operations.

apps.json – application catalog.

backup.json – backup sources and destination.

tweaks.json – system tweaks (with enable/disable scripts and selection states).

activators.json – activator tools (with download URLs and switches).

You can edit these files manually or via the Settings dialog (Settings → [tab]).

Contributing
Contributions are welcome! Please open an issue or pull request for any improvements, bug fixes, or new features.

##License


##Acknowledgements
PyInstaller – for packaging.

py7zr – for 7z archive support.

MAS – activation scripts.

KMS_VL_ALL – KMS activator.
