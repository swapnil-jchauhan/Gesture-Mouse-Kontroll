"""
Windows Session & Desktop Lock Detection for Project Kontroll.
Detects when the user has entered their password and unlocked the interactive desktop,
preventing the Jarvis boot sequence from executing while the machine is on the Lock Screen.
"""

import sys
import ctypes
from typing import Tuple

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260)
        ]


def is_logonui_active() -> bool:
    """
    Checks whether Windows LogonUI.exe is currently active.
    LogonUI.exe renders the password and PIN input screen.
    When the user submits the correct password, LogonUI terminates.
    """
    if not IS_WINDOWS:
        return False

    try:
        h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if h_snap == -1 or h_snap == 0xFFFFFFFF:
            return False

        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        found = False
        try:
            if kernel32.Process32FirstW(h_snap, ctypes.byref(pe)):
                while True:
                    if pe.szExeFile.lower() == "logonui.exe":
                        found = True
                        break
                    if not kernel32.Process32NextW(h_snap, ctypes.byref(pe)):
                        break
        finally:
            kernel32.CloseHandle(h_snap)
        return found
    except Exception:
        return False


def is_workstation_unlocked() -> bool:
    """
    Determines if the Windows workstation is unlocked and user is at their active desktop.
    Returns False when the lock screen, logon screen, or credential prompt is active.
    """
    if not IS_WINDOWS:
        return True

    try:
        # Check 1: OpenInputDesktop
        # DESKTOP_SWITCHDESKTOP = 0x0100
        h_desk = user32.OpenInputDesktop(0, False, 0x0100)
        if not h_desk:
            # Error 5 (ERROR_ACCESS_DENIED) indicates the input desktop is Winlogon
            return False

        name_buf = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        UOI_NAME = 2
        success = user32.GetUserObjectInformationW(
            h_desk, UOI_NAME, name_buf, 256, ctypes.byref(needed)
        )
        user32.CloseDesktop(h_desk)

        if not success or name_buf.value.lower() != "default":
            return False

        # Check 2: LogonUI.exe presence check
        if is_logonui_active():
            return False

        return True
    except Exception:
        return True
