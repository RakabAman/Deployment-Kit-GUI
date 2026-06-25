"""
ScriptRunner - Executes external scripts (PowerShell, Batch, etc.)
"""

import subprocess
import os

class ScriptRunner:
    @staticmethod
    def run_script(script_path, arguments=None, timeout=3600):
        """Run a script and return (success, output)."""
        if not os.path.isfile(script_path):
            return False, "Script file not found"

        # Determine interpreter
        ext = os.path.splitext(script_path)[1].lower()
        if ext == '.ps1':
            cmd = ['powershell', '-ExecutionPolicy', 'Bypass', '-File', script_path]
            if arguments:
                cmd.extend(arguments.split())
        elif ext == '.bat' or ext == '.cmd':
            cmd = [script_path]
            if arguments:
                cmd.extend(arguments.split())
        else:
            # Assume executable
            cmd = [script_path]
            if arguments:
                cmd.extend(arguments.split())

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            output = result.stdout + result.stderr
            if result.returncode == 0:
                return True, output
            else:
                return False, output
        except subprocess.TimeoutExpired:
            return False, "Script timed out"
        except Exception as e:
            return False, str(e)