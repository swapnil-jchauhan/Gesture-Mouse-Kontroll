"""
Windows Hardware-Level Mouse Event Simulation via ctypes and Win32 SendInput.
Bypasses user-space wrapper latency, supports high-DPI and absolute coordinate mapping.
"""

import ctypes
from ctypes import wintypes
import time
from typing import Tuple

# Windows Constants
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
INPUT_MOUSE = 0
WHEEL_DELTA = 120

# C Struct definitions
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]

class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUTunion),
    ]

class MouseSimulator:
    """High-performance Windows mouse simulator using Win32 SendInput."""

    def __init__(self):
        self.user32 = ctypes.windll.user32
        # Enable DPI Awareness so screen resolutions match physical pixels
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2) # Per-monitor DPI aware
        except Exception:
            try:
                self.user32.SetProcessDPIAware()
            except Exception:
                pass

        self.screen_width = self.user32.GetSystemMetrics(0)
        self.screen_height = self.user32.GetSystemMetrics(1)
        self._is_left_down = False
        self._is_right_down = False
        self._last_x = self.screen_width // 2
        self._last_y = self.screen_height // 2

    def refresh_screen_metrics(self):
        """Update screen dimensions in case display resolution changed."""
        self.screen_width = self.user32.GetSystemMetrics(0)
        self.screen_height = self.user32.GetSystemMetrics(1)

    def move_to(self, x: int, y: int):
        """
        Move the mouse cursor to absolute screen coordinates (x, y).
        Maps to Windows normalized 0..65535 coordinate space.
        """
        self.screen_width = max(1, self.screen_width)
        self.screen_height = max(1, self.screen_height)

        clamped_x = max(0, min(self.screen_width - 1, int(x)))
        clamped_y = max(0, min(self.screen_height - 1, int(y)))
        self._last_x = clamped_x
        self._last_y = clamped_y

        # Normalize to 0..65535
        norm_x = int(clamped_x * 65535 / (self.screen_width - 1))
        norm_y = int(clamped_y * 65535 / (self.screen_height - 1))

        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dx = norm_x
        inp.mi.dy = norm_y
        inp.mi.mouseData = 0
        inp.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
        inp.mi.time = 0
        inp.mi.dwExtraInfo = None

        self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def left_down(self):
        """Press and hold left mouse button."""
        if not self._is_left_down:
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
            self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            self._is_left_down = True

    def left_up(self):
        """Release left mouse button."""
        if self._is_left_down:
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.mi.dwFlags = MOUSEEVENTF_LEFTUP
            self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            self._is_left_down = False

    def click(self):
        """Perform an instantaneous hardware-level left mouse click via SendInput."""
        inputs = (INPUT * 2)()
        inputs[0].type = INPUT_MOUSE
        inputs[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN
        inputs[1].type = INPUT_MOUSE
        inputs[1].mi.dwFlags = MOUSEEVENTF_LEFTUP
        self.user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
        self._is_left_down = False

    def double_click(self):
        """Perform a rapid double click without blocking the main event loop."""
        import threading
        def _dc():
            self.click()
            time.sleep(0.045)
            self.click()
        threading.Thread(target=_dc, daemon=True).start()

    def drag_start(self):
        """
        Initiates native Windows drag with a double-click-and-hold sequence:
        DOWN -> UP -> DOWN (held). This ensures background windows are focused,
        files and desktop icons enter drag mode, and text selection begins reliably.
        """
        self.click()
        time.sleep(0.04)
        self.left_down()

    def right_click(self):
        """Perform an instantaneous hardware-level right mouse click."""
        inputs = (INPUT * 2)()
        inputs[0].type = INPUT_MOUSE
        inputs[0].mi.dwFlags = MOUSEEVENTF_RIGHTDOWN
        inputs[1].type = INPUT_MOUSE
        inputs[1].mi.dwFlags = MOUSEEVENTF_RIGHTUP
        self.user32.SendInput(2, inputs, ctypes.sizeof(INPUT))

    def scroll(self, steps: int):
        """Scroll vertical wheel. Positive for up, negative for down."""
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dwFlags = MOUSEEVENTF_WHEEL
        inp.mi.mouseData = steps * WHEEL_DELTA
        self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    @property
    def is_dragging(self) -> bool:
        return self._is_left_down
