"""
Windows 11 Autostart Manager for Project Kontroll.
Manages automatic boot launch via Current User Run Registry key (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run).
Ensures zero-admin permission requirements and silent background boot execution via pythonw.exe.
"""

import os
import sys
import winreg
from typing import Tuple

APP_NAME = "ProjectKontroll"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_launch_command() -> str:
    """
    Constructs the command to execute Project Kontroll.
    Prefers pythonw.exe if available to suppress terminal console popups on boot.
    """
    python_dir = os.path.dirname(sys.executable)
    pythonw_path = os.path.join(python_dir, "pythonw.exe")
    exe = pythonw_path if os.path.exists(pythonw_path) else sys.executable

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    main_script = os.path.join(project_root, "main.py")

    return f'"{exe}" "{main_script}" --autostart'


def is_autostart_enabled() -> bool:
    """Checks whether Project Kontroll is configured to launch on Windows startup."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as e:
        print(f"[Autostart] Query error: {e}")
        return False


def enable_autostart() -> Tuple[bool, str]:
    """Registers Project Kontroll to run automatically on Windows boot for the current user."""
    cmd = get_launch_command()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        return True, f"Successfully registered startup command: {cmd}"
    except Exception as e:
        return False, f"Failed to enable autostart: {e}"


def disable_autostart() -> Tuple[bool, str]:
    """Removes Project Kontroll from Windows startup."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, APP_NAME)
                return True, "Autostart removed successfully."
            except FileNotFoundError:
                return True, "Autostart was not configured."
    except Exception as e:
        return False, f"Failed to disable autostart: {e}"
