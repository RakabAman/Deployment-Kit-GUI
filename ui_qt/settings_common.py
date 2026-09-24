"""
Shared helpers used by the Settings sub-tabs - ported out of
settings_dialog.py's _test_package_id / _sanitize_folder_name as plain
functions, since that module imports tkinter at the top and we don't want
the Qt app depending on Tkinter being installed.
"""
import re
import subprocess


def test_package_id(provider: str, package_id: str):
    """Test if a package ID exists in Winget or Chocolatey.
    Returns (success, message, version)."""
    if not package_id:
        return False, "Package ID is empty", None

    try:
        if provider == 'winget':
            cmd = f"winget show {package_id}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                     encoding='utf-8', errors='ignore', timeout=30)
            if result.returncode == 0:
                version = None
                for line in result.stdout.split('\n'):
                    if 'Version' in line and ':' in line:
                        version = line.split(':', 1)[1].strip()
                        break
                if version:
                    return True, f"Winget Found: {version}", version
                return True, "Package found (no version info)", None
            error = result.stderr.strip() or result.stdout.strip()
            if "not found" in error.lower() or "no such" in error.lower():
                return False, "Package not found", None
            return False, f"Error: {error[:80]}", None

        elif provider == 'choco':
            cmd = f"choco find {package_id} --exact --limit-output"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                     encoding='utf-8', errors='ignore', timeout=30)
            if result.returncode == 0:
                version = None
                for line in result.stdout.split('\n'):
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            version = parts[1].strip()
                            break
                if version:
                    return True, f"Choco Found: {version}", version
                return True, "Package found (no version info)", None
            error = result.stderr.strip() or result.stdout.strip()
            if "not found" in error.lower() or "no such" in error.lower():
                return False, "Package not found", None
            return False, f"Error: {error[:80]}", None

        return False, f"Unknown provider: {provider}", None
    except subprocess.TimeoutExpired:
        return False, "Timeout (package query took too long)", None
    except FileNotFoundError:
        return False, f"{provider.capitalize()} not installed", None
    except Exception as e:
        return False, f"Exception: {str(e)[:80]}", None


def sanitize_folder_name(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', '_', name).strip()
