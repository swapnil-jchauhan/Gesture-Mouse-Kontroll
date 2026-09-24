"""
Magnetic Target Snapper & Precision UI Element Locker for Project Kontroll.
Detects clickable UI elements (window close/minimize/maximize buttons, desktop folders,
links, tabs, checkboxes, pushbuttons) and applies an assistive magnetic attraction field
with kinetic zero-jitter locking.
"""

import math
import time
import ctypes
from ctypes import wintypes, byref
from typing import Tuple, Optional, Dict, Any


class VARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
        ("wReserved2", wintypes.WORD),
        ("wReserved3", wintypes.WORD),
        ("lVal", wintypes.LONG),
        ("padding", ctypes.c_byte * 12),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


# Win32 MSAA Clickable Roles
ROLE_SYSTEM_TITLEBAR = 0x1
ROLE_SYSTEM_MENUBAR = 0x2
ROLE_SYSTEM_MENUITEM = 0xC
ROLE_SYSTEM_LINK = 0x1E
ROLE_SYSTEM_LISTITEM = 0x22      # Desktop icons, Explorer files/folders
ROLE_SYSTEM_OUTLINEITEM = 0x24   # Tree folders
ROLE_SYSTEM_PAGETAB = 0x25       # Browser & window tabs
ROLE_SYSTEM_GRAPHIC = 0x28
ROLE_SYSTEM_TEXT = 0x2A          # Text boxes / search bars
ROLE_SYSTEM_PUSHBUTTON = 0x2B    # Buttons (Close, Min, Max, OK, Cancel)
ROLE_SYSTEM_CHECKBUTTON = 0x2C   # Checkboxes
ROLE_SYSTEM_RADIOBUTTON = 0x2D   # Radio buttons
ROLE_SYSTEM_COMBOBOX = 0x2E      # Dropdowns
ROLE_SYSTEM_SLIDER = 0x33
ROLE_SYSTEM_SPLITBUTTON = 0x3E

CLICKABLE_ROLES = {
    ROLE_SYSTEM_PUSHBUTTON,
    ROLE_SYSTEM_LISTITEM,
    ROLE_SYSTEM_OUTLINEITEM,
    ROLE_SYSTEM_PAGETAB,
    ROLE_SYSTEM_LINK,
    ROLE_SYSTEM_CHECKBUTTON,
    ROLE_SYSTEM_RADIOBUTTON,
    ROLE_SYSTEM_MENUITEM,
    ROLE_SYSTEM_SPLITBUTTON,
    ROLE_SYSTEM_COMBOBOX,
    ROLE_SYSTEM_TEXT,
}

ROLE_NAMES = {
    ROLE_SYSTEM_PUSHBUTTON: "BUTTON",
    ROLE_SYSTEM_LISTITEM: "FOLDER / ICON",
    ROLE_SYSTEM_OUTLINEITEM: "TREE ITEM",
    ROLE_SYSTEM_PAGETAB: "TAB",
    ROLE_SYSTEM_LINK: "LINK",
    ROLE_SYSTEM_CHECKBUTTON: "CHECKBOX",
    ROLE_SYSTEM_RADIOBUTTON: "RADIO",
    ROLE_SYSTEM_MENUITEM: "MENU ITEM",
    ROLE_SYSTEM_SPLITBUTTON: "SPLIT BUTTON",
    ROLE_SYSTEM_COMBOBOX: "DROPDOWN",
    ROLE_SYSTEM_TEXT: "TEXT INPUT",
    ROLE_SYSTEM_TITLEBAR: "TITLEBAR",
}


class TargetLockManager:
    """
    Real-time Assistive UI Snapper using Windows MSAA and Non-Client Window geometry.
    Snaps cursor into tiny clickable controls when the user slows down to aim.
    """

    def __init__(self, capture_radius: float = 38.0, breakout_velocity: float = 350.0):
        self.capture_radius = capture_radius
        self.breakout_velocity = breakout_velocity

        self.user32 = ctypes.windll.user32
        self.ole32 = ctypes.windll.ole32
        self.oleacc = ctypes.windll.oleacc

        try:
            self.ole32.CoInitialize(None)
        except Exception:
            pass

        try:
            h_desk = self.user32.OpenDesktopW("default", 0, False, 0x10000000)
            if h_desk:
                self.user32.SetThreadDesktop(h_desk)
        except Exception:
            pass

        # Configure AccessibleObjectFromPoint:
        # In x64 Windows C ABI: POINT ptScreen is packed in RCX (uint64: x | (y << 32))
        self.oleacc.AccessibleObjectFromPoint.argtypes = [
            ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(VARIANT),
        ]
        self.oleacc.AccessibleObjectFromPoint.restype = ctypes.c_long

        # Last locked state
        self.last_target_rect: Optional[Tuple[int, int, int, int]] = None
        self.last_target_center: Optional[Tuple[float, float]] = None
        self.last_target_role: Optional[int] = None
        self.last_target_name: Optional[str] = None
        self.is_locked: bool = False
        self.lock_start_time: float = 0.0

        # Query rate limiting (MSAA is fast ~1ms, but query every 30-50ms or when moving slowly)
        self._last_query_time = 0.0
        self._query_interval = 0.033  # ~30 Hz query rate
        self._cached_target: Optional[Dict[str, Any]] = None

    def query_ui_element(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """
        Inspects the UI element at screen coordinate (x, y).
        Returns target dictionary if a clickable element is found.
        """
        # 1. First check window caption control buttons (Close, Min, Max)
        caption_target = self._check_window_caption_controls(x, y)
        if caption_target is not None:
            return caption_target

        # 2. Query Windows MSAA Accessible Object
        pt_val = (int(y) << 32) | (int(x) & 0xFFFFFFFF)
        pacc = ctypes.c_void_p()
        var = VARIANT()
        var.vt = 3  # VT_I4

        hr = self.oleacc.AccessibleObjectFromPoint(pt_val, byref(pacc), byref(var))
        if hr != 0 or not pacc.value:
            return None

        try:
            vtable = ctypes.cast(pacc, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

            # get_accRole (vtable index 13)
            get_accRole_func = ctypes.CFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, VARIANT, ctypes.POINTER(VARIANT)
            )(vtable[13])
            role_var = VARIANT()
            hr_role = get_accRole_func(pacc, var, byref(role_var))
            role_id = role_var.lVal if (hr_role == 0 and role_var.vt == 3) else None

            # accLocation (vtable index 22)
            accLocation_func = ctypes.CFUNCTYPE(
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_long),
                ctypes.POINTER(ctypes.c_long),
                ctypes.POINTER(ctypes.c_long),
                ctypes.POINTER(ctypes.c_long),
                VARIANT,
            )(vtable[22])
            px, py, pw, ph = ctypes.c_long(), ctypes.c_long(), ctypes.c_long(), ctypes.c_long()
            hr_loc = accLocation_func(pacc, byref(px), byref(py), byref(pw), byref(ph), var)

            if hr_loc != 0 or role_id not in CLICKABLE_ROLES:
                return None

            left, top, width, height = px.value, py.value, pw.value, ph.value

            # Filter out giant full-window containers misclassified as items
            if width <= 0 or height <= 0 or width > 600 or height > 600:
                return None

            cx = left + width / 2.0
            cy = top + height / 2.0

            return {
                "role": role_id,
                "role_name": ROLE_NAMES.get(role_id, f"ROLE_{role_id}"),
                "rect": (left, top, width, height),
                "center": (cx, cy),
            }

        except Exception:
            return None
        finally:
            if pacc.value:
                try:
                    vtable = ctypes.cast(pacc, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                    release_func = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
                    release_func(pacc)
                except Exception:
                    pass

    def _check_window_caption_controls(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """
        Directly detects Close [X], Maximize [□], and Minimize [_] buttons on windows.
        Works across Win32, UWP, and custom title bars.
        """
        # User32 WindowFromPoint
        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        self.user32.WindowFromPoint.argtypes = [POINT]
        self.user32.WindowFromPoint.restype = wintypes.HWND

        hwnd = self.user32.WindowFromPoint(POINT(int(x), int(y)))
        if not hwnd:
            return None

        # Get ancestor / top-level window
        GA_ROOT = 2
        root_hwnd = self.user32.GetAncestor(hwnd, GA_ROOT)
        target_hwnd = root_hwnd if root_hwnd else hwnd

        rect = wintypes.RECT()
        if not self.user32.GetWindowRect(target_hwnd, byref(rect)):
            return None

        win_left = rect.left
        win_right = rect.right
        win_top = rect.top
        win_height = rect.bottom - rect.top
        win_width = win_right - win_left

        if win_width < 100 or win_height < 60:
            return None

        # Title bar controls are within the top 36 pixels of the window
        caption_height = 34
        if not (win_top - 4 <= y <= win_top + caption_height):
            return None

        # 1. Close Button (Rightmost: ~46px wide)
        close_left = win_right - 46
        close_right = win_right
        if close_left - 10 <= x <= close_right + 5:
            return {
                "role": ROLE_SYSTEM_PUSHBUTTON,
                "role_name": "CLOSE [X]",
                "rect": (close_left, win_top, 46, caption_height),
                "center": (close_left + 23.0, win_top + caption_height / 2.0),
            }

        # 2. Maximize / Restore Button (~46px wide)
        max_left = win_right - 92
        max_right = win_right - 46
        if max_left - 5 <= x <= max_right + 5:
            return {
                "role": ROLE_SYSTEM_PUSHBUTTON,
                "role_name": "MAXIMIZE [□]",
                "rect": (max_left, win_top, 46, caption_height),
                "center": (max_left + 23.0, win_top + caption_height / 2.0),
            }

        # 3. Minimize Button (~46px wide)
        min_left = win_right - 138
        min_right = win_right - 92
        if min_left - 5 <= x <= min_right + 5:
            return {
                "role": ROLE_SYSTEM_PUSHBUTTON,
                "role_name": "MINIMIZE [_]",
                "rect": (min_left, win_top, 46, caption_height),
                "center": (min_left + 23.0, win_top + caption_height / 2.0),
            }

        return None

    def apply_magnetic_lock(
        self,
        raw_x: float,
        raw_y: float,
        velocity: float,
        timestamp: Optional[float] = None,
    ) -> Tuple[int, int, bool, Optional[str]]:
        """
        Applies magnetic attraction towards clickable targets.
        :param raw_x: Smoothed cursor X coordinate.
        :param raw_y: Smoothed cursor Y coordinate.
        :param velocity: Current hand movement velocity in pixels/sec or pixels/tick.
        :param timestamp: Monotonic timestamp.
        :return: (snapped_x, snapped_y, is_locked, target_description)
        """
        if timestamp is None:
            timestamp = time.perf_counter()

        # If user is flicking or moving fast, break out of any lock immediately
        if velocity > self.breakout_velocity:
            self.is_locked = False
            self.last_target_center = None
            self.last_target_rect = None
            return int(raw_x), int(raw_y), False, None

        # Check for target override (useful for testing or dedicated locks)
        override = getattr(self, "_override_target", None)
        if override is not None:
            target = override
        else:
            # Periodically refresh target info or check current cached target
            target = self._cached_target
            if (timestamp - self._last_query_time) >= self._query_interval or target is None:
                new_target = self.query_ui_element(int(raw_x), int(raw_y))
                if new_target is not None:
                    self._cached_target = new_target
                    target = new_target
                elif target is None or (timestamp - self._last_query_time) >= 0.20:
                    self._cached_target = None
                    target = None
                self._last_query_time = timestamp

        if target is None:
            # Also check if we were previously locked and still within breakout margin of previous target
            if self.is_locked and self.last_target_center is not None and self.last_target_rect is not None:
                tcx, tcy = self.last_target_center
                dist = math.hypot(raw_x - tcx, raw_y - tcy)
                if dist < self.capture_radius * 1.3:
                    # Maintain gentle assist while hovering near same target
                    pull = 0.25 if velocity < 120.0 else 0.10
                    snapped_x = raw_x + (tcx - raw_x) * pull
                    snapped_y = raw_y + (tcy - raw_y) * pull
                    return int(snapped_x), int(snapped_y), True, self.last_target_name
            self.is_locked = False
            return int(raw_x), int(raw_y), False, None

        tcx, tcy = target["center"]
        left, top, width, height = target["rect"]
        role_name = target["role_name"]

        # Calculate distance to element center
        dx = tcx - raw_x
        dy = tcy - raw_y
        dist = math.hypot(dx, dy)

        # Check if inside bounding box (with generous capture padding)
        pad = 18.0
        inside_box = (left - pad <= raw_x <= left + width + pad) and (top - pad <= raw_y <= top + height + pad)

        if inside_box or dist <= self.capture_radius:
            # Engage Magnetic Lock!
            self.is_locked = True
            self.last_target_center = (tcx, tcy)
            self.last_target_rect = (left, top, width, height)
            self.last_target_role = target["role"]
            self.last_target_name = role_name

            # Subtle Assistive Magnetic Pull:
            # Gently guides hand to center without trapping the cursor
            if velocity < 80.0:
                pull = 0.35
            elif velocity < 180.0:
                pull = 0.20
            else:
                pull = 0.08

            snapped_x = raw_x + (tcx - raw_x) * pull
            snapped_y = raw_y + (tcy - raw_y) * pull
            return int(snapped_x), int(snapped_y), True, role_name

        self.is_locked = False
        return int(raw_x), int(raw_y), False, None
