"""
OS-Level Viscous Deceleration Aim Assist & Target Lock for Project Kontroll.
Pillar 5: Replaces hard magnetic teleportation with dynamic viscous deceleration bubbles
(35 px radius). Velocity slows down smoothly by up to 65% when approaching buttons so the
cursor settles effortlessly on target without overshoot. Firm click anchor during active
tap/click motion. Instant breakout on intentional hand flick.
"""

import math
import time
import ctypes
from ctypes import wintypes, byref
from typing import Tuple, Optional, Dict, Any

try:
    import uiautomation as auto
except ImportError:
    auto = None


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
ROLE_SYSTEM_LISTITEM = 0x22      # Desktop icons, Explorer files
ROLE_SYSTEM_OUTLINEITEM = 0x24   # Tree folders
ROLE_SYSTEM_PAGETAB = 0x25       # Browser and window tabs
ROLE_SYSTEM_GRAPHIC = 0x28
ROLE_SYSTEM_TEXT = 0x2A          # Text boxes and search bars
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

# No dashes or slashes in role names
ROLE_NAMES = {
    ROLE_SYSTEM_PUSHBUTTON: "BUTTON",
    ROLE_SYSTEM_LISTITEM: "ICON OR FOLDER",
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

UIA_CLICKABLE_TYPES = {
    "ButtonControl",
    "HyperlinkControl",
    "MenuItemControl",
    "TabItemControl",
    "ListItemControl",
    "CheckBoxControl",
    "RadioButtonControl",
    "SplitButtonControl",
    "ComboBoxControl",
    "TreeItemControl",
    "HeaderItemControl",
    "ThumbControl",
}


class TargetLockManager:
    """
    OS-Level Viscous Deceleration Aim Assist Manager.
    Automatically detects clickable UI elements across Windows.
    Applies viscous deceleration bubbles (35 px) that slow cursor velocity by up to 65%
    approaching buttons to prevent overshoot, while providing a firm click anchor during taps.
    """

    def __init__(
        self,
        capture_radius: float = 42.0,
        breakout_velocity: float = 750.0,
        bubble_radius: float = 35.0,
        max_damping: float = 0.65,
    ):
        self.capture_radius = capture_radius
        self.breakout_velocity = breakout_velocity
        self.bubble_radius = bubble_radius
        self.max_damping = max_damping  # Slow down by up to 65%

        self.user32 = ctypes.windll.user32
        self.ole32 = ctypes.windll.ole32
        self.oleacc = ctypes.windll.oleacc

        try:
            self.ole32.CoInitialize(None)
        except Exception:
            pass

        # Attach thread to interactive user desktop
        try:
            h_desk = self.user32.OpenInputDesktop(0, False, 0x10000000)
            if h_desk:
                self.user32.SetThreadDesktop(h_desk)
        except Exception:
            pass

        # Configure AccessibleObjectFromPoint
        try:
            self.oleacc.AccessibleObjectFromPoint.argtypes = [
                ctypes.c_uint64,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(VARIANT),
            ]
            self.oleacc.AccessibleObjectFromPoint.restype = ctypes.c_long
        except Exception:
            pass

        # Target tracking state
        self.last_target_rect: Optional[Tuple[int, int, int, int]] = None
        self.last_target_center: Optional[Tuple[float, float]] = None
        self.last_target_role: Optional[int] = None
        self.last_target_name: Optional[str] = None
        self.is_locked: bool = False
        self.lock_start_time: float = 0.0

        # Query caching to ensure 120 Hz loop stays ultra-fast
        self._last_query_time = 0.0
        self._query_interval = 0.035
        self._cached_target: Optional[Dict[str, Any]] = None
        self._override_target: Optional[Dict[str, Any]] = None
        self.last_output_pos: Optional[Tuple[float, float]] = None

    def query_ui_element(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """
        Inspects screen coordinate (x, y) for clickable targets via Win32 hit-testing,
        Windows UI Automation, and MSAA.
        """
        # Override for testing
        if self._override_target is not None:
            return self._override_target

        # 1. Fast Window Caption Hit Test (Close, Maximize, Minimize)
        caption_target = self._check_window_caption_controls(x, y)
        if caption_target is not None:
            return caption_target

        # 2. Modern Windows UI Automation (Chrome, Edge, Explorer, Windows 11 apps)
        if auto:
            try:
                c = auto.ControlFromPoint(x, y)
                if c:
                    target_ctrl = None
                    c_type = c.ControlTypeName
                    if c_type in UIA_CLICKABLE_TYPES or getattr(c, "AriaRole", None) in {"button", "link", "tab", "menuitem", "checkbox", "radio"}:
                        target_ctrl = c
                    else:
                        p = c.GetParentControl()
                        if p and (p.ControlTypeName in UIA_CLICKABLE_TYPES or getattr(p, "AriaRole", None) in {"button", "link", "tab", "menuitem", "checkbox", "radio"}):
                            target_ctrl = p

                    if target_ctrl:
                        rect = target_ctrl.BoundingRectangle
                        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                        width, height = right - left, bottom - top
                        if 4 <= width <= 800 and 4 <= height <= 450:
                            cx = (left + right) / 2.0
                            cy = (top + bottom) / 2.0
                            name = target_ctrl.Name or target_ctrl.ControlTypeName.replace("Control", "")
                            return {
                                "role": ROLE_SYSTEM_PUSHBUTTON,
                                "role_name": name.strip()[:24] if name else "BUTTON",
                                "rect": (left, top, width, height),
                                "center": (cx, cy),
                            }
            except Exception:
                pass

        # 3. Legacy MSAA Accessible Object Query
        pt_val = (int(y) << 32) | (int(x) & 0xFFFFFFFF)
        pacc = ctypes.c_void_p()
        var = VARIANT()
        var.vt = 3  # VT_I4

        try:
            hr = self.oleacc.AccessibleObjectFromPoint(pt_val, byref(pacc), byref(var))
            if hr == 0 and pacc.value:
                vtable = ctypes.cast(pacc, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

                # get_accRole
                get_accRole_func = ctypes.CFUNCTYPE(
                    ctypes.c_long, ctypes.c_void_p, VARIANT, ctypes.POINTER(VARIANT)
                )(vtable[13])
                role_var = VARIANT()
                hr_role = get_accRole_func(pacc, var, byref(role_var))
                role_id = role_var.lVal if (hr_role == 0 and role_var.vt == 3) else None

                # accLocation
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

                if hr_loc == 0 and role_id in CLICKABLE_ROLES:
                    left, top, width, height = px.value, py.value, pw.value, ph.value
                    if 4 <= width <= 600 and 4 <= height <= 500:
                        cx = left + width / 2.0
                        cy = top + height / 2.0
                        return {
                            "role": role_id,
                            "role_name": ROLE_NAMES.get(role_id, "BUTTON"),
                            "rect": (left, top, width, height),
                            "center": (cx, cy),
                        }
        except Exception:
            pass
        finally:
            if pacc.value:
                try:
                    vtable = ctypes.cast(pacc, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                    release_func = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
                    release_func(pacc)
                except Exception:
                    pass

        return None

    def _check_window_caption_controls(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """Fast Win32 hit-testing for top window buttons (Close, Minimize, Maximize)."""
        pt = POINT(x, y)
        hwnd = self.user32.WindowFromPoint(pt)
        if not hwnd:
            return None

        WM_NCHITTEST = 0x0084
        lparam = (y << 16) | (x & 0xFFFF)
        try:
            hit = self.user32.SendMessageW(hwnd, WM_NCHITTEST, 0, lparam)
        except Exception:
            return None

        HTCLOSE = 20
        HTMINBUTTON = 8
        HTMAXBUTTON = 9
        HTHELP = 21

        if hit in (HTCLOSE, HTMINBUTTON, HTMAXBUTTON, HTHELP):
            rect = wintypes.RECT()
            self.user32.GetWindowRect(hwnd, byref(rect))

            btn_w = 46
            btn_h = 32

            if hit == HTCLOSE:
                bx = rect.right - btn_w // 2
                by = rect.top + btn_h // 2
                return {
                    "role": ROLE_SYSTEM_PUSHBUTTON,
                    "role_name": "CLOSE [X]",
                    "rect": (rect.right - btn_w, rect.top, btn_w, btn_h),
                    "center": (float(bx), float(by)),
                }
            elif hit == HTMAXBUTTON:
                bx = rect.right - btn_w - btn_w // 2
                by = rect.top + btn_h // 2
                return {
                    "role": ROLE_SYSTEM_PUSHBUTTON,
                    "role_name": "MAXIMIZE [□]",
                    "rect": (rect.right - btn_w * 2, rect.top, btn_w, btn_h),
                    "center": (float(bx), float(by)),
                }
            elif hit == HTMINBUTTON:
                bx = rect.right - btn_w * 2 - btn_w // 2
                by = rect.top + btn_h // 2
                return {
                    "role": ROLE_SYSTEM_PUSHBUTTON,
                    "role_name": "MINIMIZE [_]",
                    "rect": (rect.right - btn_w * 3, rect.top, btn_w, btn_h),
                    "center": (float(bx), float(by)),
                }

        # Universal fallback for modern XAML / Windows Terminal / custom-drawn windows
        rect = wintypes.RECT()
        if self.user32.GetWindowRect(hwnd, byref(rect)):
            win_w = rect.right - rect.left
            win_h = rect.bottom - rect.top
            # If window is an application window and cursor is within top caption strip (top 38px)
            if win_w >= 220 and win_h >= 120 and rect.top <= y <= rect.top + 38:
                if rect.right - 52 <= x <= rect.right:
                    # Close [X] button in top right
                    return {
                        "role": ROLE_SYSTEM_PUSHBUTTON,
                        "role_name": "CLOSE [X]",
                        "rect": (rect.right - 52, rect.top, 52, 36),
                        "center": (float(rect.right - 26), float(rect.top + 18)),
                    }
                elif rect.right - 100 <= x < rect.right - 52:
                    # Maximize button
                    return {
                        "role": ROLE_SYSTEM_PUSHBUTTON,
                        "role_name": "MAXIMIZE [□]",
                        "rect": (rect.right - 100, rect.top, 48, 36),
                        "center": (float(rect.right - 76), float(rect.top + 18)),
                    }
                elif rect.right - 148 <= x < rect.right - 100:
                    # Minimize button
                    return {
                        "role": ROLE_SYSTEM_PUSHBUTTON,
                        "role_name": "MINIMIZE [_]",
                        "rect": (rect.right - 148, rect.top, 48, 36),
                        "center": (float(rect.right - 124), float(rect.top + 18)),
                    }

        return None

    def compute_viscous_scale(self, distance_to_target: float, velocity: float) -> float:
        """
        Computes dynamic velocity scale factor (1.0 = normal speed, down to 0.35 = 65% deceleration).
        If velocity >= breakout_velocity, returns 1.0 (instant breakout).
        """
        if velocity >= self.breakout_velocity:
            return 1.0

        if distance_to_target >= self.bubble_radius:
            return 1.0

        # Distance within outer bubble (35 px):
        # Scale slows down smoothly as distance decreases:
        # factor = 1.0 - alpha * ((bubble_radius - dist) / bubble_radius)
        proximity = max(0.0, (self.bubble_radius - distance_to_target) / self.bubble_radius)
        scale = 1.0 - (self.max_damping * proximity)
        return max(1.0 - self.max_damping, min(1.0, scale))

    def apply_magnetic_lock(
        self,
        raw_x: float,
        raw_y: float,
        velocity: float = 0.0,
        timestamp: float = 0.0,
        is_clicking: bool = False,
    ) -> Tuple[int, int, bool, Optional[str]]:
        """
        Applies OS-Level Viscous Deceleration Aim Assist.
        Inside button rectangle or during click motions (is_clicking=True):
        Firmly clings to target center to prevent finger twitch slip.
        Approaching button boundary:
        Smooth viscous deceleration dampens velocity by up to 65% to eliminate overshoot.
        Intentional fast flick breaks out cleanly.
        """
        override = getattr(self, "_override_target", None)

        # 1. If currently locked, evaluate sticky gravity well retention
        if self.is_locked and self.last_target_rect is not None and self.last_target_center is not None:
            left, top, width, height = self.last_target_rect
            tcx, tcy = self.last_target_center
            pad = max(self.capture_radius, 65.0)
            inside_pad = (left - pad <= raw_x <= left + width + pad) and (top - pad <= raw_y <= top + height + pad)
            dist = math.hypot(raw_x - tcx, raw_y - tcy)
            max_stick_dist = max(width, height) / 2.0 + 75.0

            # Active Click Anchor: During taps/clicks, hold lock rigidly unless pulled far away (> 240 px)
            if is_clicking:
                if dist <= 240.0 or inside_pad:
                    self.last_output_pos = (tcx, tcy)
                    return int(round(tcx)), int(round(tcy)), True, self.last_target_name
                else:
                    self.is_locked = False
                    self._cached_target = None
                    self.last_output_pos = (raw_x, raw_y)
            else:
                # Retention zone: Stay locked unless user substantially, intentionally pulls away
                should_breakout = False
                if not inside_pad and dist > max_stick_dist:
                    should_breakout = True
                elif velocity >= self.breakout_velocity and dist >= 35.0:
                    should_breakout = True

                if not should_breakout:
                    self.last_output_pos = (tcx, tcy)
                    return int(round(tcx)), int(round(tcy)), True, self.last_target_name
                else:
                    self.is_locked = False
                    self._cached_target = None
                    self.last_output_pos = (raw_x, raw_y)

        if override is not None:
            target = override
        else:
            # 2. Query target for current cursor position
            target = self._cached_target
            if (timestamp - self._last_query_time) >= self._query_interval or target is None:
                new_target = self.query_ui_element(int(raw_x), int(raw_y))
                if new_target is not None:
                    self._cached_target = new_target
                    target = new_target
                elif (timestamp - self._last_query_time) >= 0.12:
                    self._cached_target = None
                    target = None
                self._last_query_time = timestamp

        if target is None:
            self.is_locked = False
            self.last_output_pos = (raw_x, raw_y)
            return int(round(raw_x)), int(round(raw_y)), False, None

        tcx, tcy = target["center"]
        left, top, width, height = target["rect"]
        role_name = target["role_name"]

        # Calculate distance to element center
        dx = tcx - raw_x
        dy = tcy - raw_y
        dist = math.hypot(dx, dy)

        # Check if inside physical element rectangle
        inside_rect = (left <= raw_x <= left + width) and (top <= raw_y <= top + height)
        # Calculate distance to element edge
        dx_edge = max(0.0, max(left - raw_x, raw_x - (left + width)))
        dy_edge = max(0.0, max(top - raw_y, raw_y - (top + height)))
        dist_edge = math.hypot(dx_edge, dy_edge)

        if velocity >= self.breakout_velocity:
            self.is_locked = False
            self.last_output_pos = (raw_x, raw_y)
            return int(round(raw_x)), int(round(raw_y)), False, None

        # 1. Firm Click Anchor: Active tap/click contact firmly locks onto button center
        if is_clicking and (inside_rect or dist <= 120.0 or dist_edge <= self.bubble_radius):
            self.is_locked = True
            self.last_target_center = (tcx, tcy)
            self.last_target_rect = (left, top, width, height)
            self.last_target_role = target.get("role", ROLE_SYSTEM_PUSHBUTTON)
            self.last_target_name = role_name
            self.last_output_pos = (tcx, tcy)
            return int(round(tcx)), int(round(tcy)), True, role_name

        # 2. Inside physical element bounds: Cling to target center
        if inside_rect:
            self.is_locked = True
            self.last_target_center = (tcx, tcy)
            self.last_target_rect = (left, top, width, height)
            self.last_target_role = target.get("role", ROLE_SYSTEM_PUSHBUTTON)
            self.last_target_name = role_name
            self.last_output_pos = (tcx, tcy)
            return int(round(tcx)), int(round(tcy)), True, role_name

        # 3. Approaching in outer viscous deceleration bubble (35 px):
        # Velocity slows down smoothly by up to 65% so the cursor settles on target without overshoot
        if dist_edge <= self.bubble_radius:
            scale = self.compute_viscous_scale(dist_edge, velocity)
            if self.last_output_pos is not None:
                step_x = raw_x - self.last_output_pos[0]
                step_y = raw_y - self.last_output_pos[1]
                out_x = self.last_output_pos[0] + step_x * scale
                out_y = self.last_output_pos[1] + step_y * scale
            else:
                out_x = raw_x
                out_y = raw_y

            self.is_locked = True
            self.last_target_center = (tcx, tcy)
            self.last_target_rect = (left, top, width, height)
            self.last_target_role = target.get("role", ROLE_SYSTEM_PUSHBUTTON)
            self.last_target_name = role_name
            self.last_output_pos = (out_x, out_y)
            return int(round(out_x)), int(round(out_y)), True, role_name

        self.is_locked = False
        self.last_output_pos = (raw_x, raw_y)
        return int(round(raw_x)), int(round(raw_y)), False, None
