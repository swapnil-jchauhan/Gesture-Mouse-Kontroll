"""
Gesture Detection Engine for Project Kontroll.
Implements:
1. Closed-Fist Index-on-Thumb Tap for Left Click & Double Click.
2. Index-on-Thumb with Three Fingers Up (Super Sign) for Drag & Drop.
3. Index-on-Middle Tap for Right Click.
4. OS-Level Sticky Aim Assist integration with Zero Cursor Freezing / Jamming.
5. S-Curve Dynamic Pointer Acceleration inside Ergonomic Rest Box.
"""

import math
import time
from typing import Tuple, Optional, Callable, Dict, Any
from src.core.filter import Point2DOneEuroFilter
from src.core.target_lock import TargetLockManager


class GestureEngine:
    """
    Gesture State Machine & Cursor Mapping Engine for Project Kontroll.
    """

    def __init__(
        self,
        screen_width: int = 1920,
        screen_height: int = 1080,
        on_state_change: Optional[Callable[[bool], None]] = None,
        on_click_callback: Optional[Callable[[], None]] = None,
    ):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.on_state_change = on_state_change
        self.on_click_callback = on_click_callback

        # System State
        self.is_active = True

        # Camera Mounting Mode: 'auto', 'left' (tilted left monitor), 'center', 'right'
        self.mount_mode = "left"
        self.detected_tilt_angle = 25.0

        # 1€ Filter: Fast responsive tuning with stillness deadband
        self.cursor_filter = Point2DOneEuroFilter(freq=60.0, min_cutoff=0.8, beta=0.045, deadband_radius=2.2)

        # OS-Level Sticky Aim Assister
        self.target_lock = TargetLockManager(capture_radius=40.0, breakout_velocity=260.0)

        # Ergonomic Rest Box (forearm/elbow resting on desk)
        self.box_xmin = 0.28
        self.box_xmax = 0.70
        self.box_ymin = 0.44
        self.box_ymax = 0.78

        # Left Click Parameters: Closed-Fist Index-Thumb Tap
        self.tap_down_ratio = 0.18
        self.tap_up_ratio = 0.24
        self.tap_state = "UP"  # "UP", "DOWN"
        self.tap_start_time = 0.0

        # Right Click Parameters: Index-on-Middle Tap
        self.right_tap_down_ratio = 0.17
        self.right_tap_up_ratio = 0.23
        self.right_click_state = "UP"
        self.right_tap_start_time = 0.0

        # Drag Mode: Index-Thumb with 3 Fingers UP
        self.is_dragging = False
        self.pinch_drag_threshold = 0.22
        self.pinch_start_time = 0.0

        # Multi-Click / Double-Click tracking
        self.double_click_window = 0.38
        self.last_click_time = 0.0
        self.last_click_pos = (screen_width // 2, screen_height // 2)

        # Telemetry
        self.last_screen_x = screen_width // 2
        self.last_screen_y = screen_height // 2
        self.last_is_locked = False
        self.last_target_desc = None

    def update_screen_size(self, width: int, height: int):
        self.screen_width = width
        self.screen_height = height

    def reset_hand_state(self):
        """Called when no hand is in view to clear all active states immediately."""
        self.tap_state = "UP"
        self.right_click_state = "UP"
        self.is_dragging = False
        self.pinch_start_time = 0.0
        self.last_is_locked = False
        self.last_target_desc = None

    @staticmethod
    def _dist_3d(p1, p2) -> float:
        """Euclidean distance in normalized 3D landmark space."""
        dx = p1.x - p2.x
        dy = p1.y - p2.y
        dz = getattr(p1, "z", 0.0) - getattr(p2, "z", 0.0)
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _get_hand_scale(self, landmarks) -> float:
        """Calculates hand scale reference: Wrist (0) to Middle MCP knuckle (9) in 3D."""
        return max(0.01, self._dist_3d(landmarks[0], landmarks[9]))

    def is_fist_closed(self, landmarks, scale: float) -> bool:
        """
        Detects if the middle, ring, and pinky fingers are curled closed into a fist.
        In a fist, tips are folded down towards the palm (tip.y >= pip.y or dist_to_wrist is small).
        """
        # Middle (12 vs 10), Ring (16 vs 14), Pinky (20 vs 18)
        m_curled = (landmarks[12].y >= landmarks[10].y - 0.025)
        r_curled = (landmarks[16].y >= landmarks[14].y - 0.025)
        p_curled = (landmarks[20].y >= landmarks[18].y - 0.025)

        # Distance to wrist in 3D
        d_m_wrist = self._dist_3d(landmarks[12], landmarks[0]) / scale
        d_r_wrist = self._dist_3d(landmarks[16], landmarks[0]) / scale
        d_p_wrist = self._dist_3d(landmarks[20], landmarks[0]) / scale

        wrist_close = (d_m_wrist < 1.25 and d_r_wrist < 1.25 and d_p_wrist < 1.25)
        return (m_curled and r_curled and p_curled) or wrist_close

    def are_last_three_up(self, landmarks) -> bool:
        """
        Detects if the last three fingers (Middle, Ring, Pinky) are extended upright.
        """
        m_up = landmarks[12].y < landmarks[10].y
        r_up = landmarks[16].y < landmarks[14].y
        p_up = landmarks[20].y < landmarks[18].y
        return m_up and r_up and p_up

    def compute_tap_metric(self, landmarks, scale: float) -> Tuple[float, bool]:
        """
        Calculates Left-Click Tap Metric:
        Index fingertip (8) on Thumb fingertip (4) with a CLOSED FIST.
        """
        fist_closed = self.is_fist_closed(landmarks, scale)
        if not fist_closed:
            return 1.0, False

        d_index_thumb = self._dist_3d(landmarks[8], landmarks[4])
        tap_ratio = d_index_thumb / scale
        is_contact = tap_ratio < self.tap_down_ratio

        return tap_ratio, is_contact

    compute_angle_invariant_tap_metric = compute_tap_metric

    def is_super_gesture(self, landmarks) -> bool:
        """
        Detects the 'Super / OK' pose:
        Index touches Thumb while last three fingers (Middle, Ring, Pinky) are straight UP.
        """
        scale = self._get_hand_scale(landmarks)
        d_thumb_index = self._dist_3d(landmarks[4], landmarks[8]) / scale
        return (d_thumb_index < self.pinch_drag_threshold) and self.are_last_three_up(landmarks)

    def process(self, landmarks, timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Processes a frame of hand landmarks and outputs cursor position, action, and telemetry.
        """
        now = timestamp if timestamp is not None else time.perf_counter()
        scale = self._get_hand_scale(landmarks)

        # 1. Distances and Pose Classifications
        d_thumb_index = self._dist_3d(landmarks[4], landmarks[8]) / scale
        d_index_middle = self._dist_3d(landmarks[8], landmarks[12]) / scale
        fist_closed = self.is_fist_closed(landmarks, scale)
        three_fingers_up = self.are_last_three_up(landmarks)

        # Left Click: Index on Thumb with Closed Fist
        is_left_contact = (d_thumb_index < self.tap_down_ratio) and fist_closed

        # Drag: Index on Thumb with Last Three Fingers UP (Super Pose)
        drag_pose_active = (d_thumb_index < self.pinch_drag_threshold) and three_fingers_up

        # Right Click: Index on Middle tap with both extended
        index_extended = landmarks[8].y < landmarks[6].y
        middle_extended = landmarks[12].y < landmarks[10].y
        is_right_contact = (d_index_middle < self.right_tap_down_ratio) and index_extended and middle_extended

        # 2. Cursor Tracking Point: Index Fingertip
        norm_x = landmarks[8].x
        norm_y = landmarks[8].y

        # Camera Tilt Correction
        rot_angle = 0.0
        if self.mount_mode == "left":
            rot_angle = math.radians(24.0)
        elif self.mount_mode == "right":
            rot_angle = math.radians(-24.0)

        if abs(rot_angle) > 1e-4:
            cos_a = math.cos(rot_angle)
            sin_a = math.sin(rot_angle)
            cx_ref, cy_ref = 0.5, 0.6
            dx = norm_x - cx_ref
            dy = norm_y - cy_ref
            norm_x = cx_ref + (dx * cos_a - dy * sin_a)
            norm_y = cy_ref + (dx * sin_a + dy * cos_a)

        # 3. Absolute Mapping inside Ergonomic Rest Box
        box_w = max(0.001, self.box_xmax - self.box_xmin)
        box_h = max(0.001, self.box_ymax - self.box_ymin)

        u = (norm_x - self.box_xmin) / box_w
        v = (norm_y - self.box_ymin) / box_h
        u = max(0.0, min(1.0, u))
        v = max(0.0, min(1.0, v))

        # Smooth S-Curve: Precision in center, gentle reach near edges
        u_curved = 0.5 + math.copysign(0.5 * (abs(2.0 * (u - 0.5)) ** 1.15), u - 0.5)
        v_curved = 0.5 + math.copysign(0.5 * (abs(2.0 * (v - 0.5)) ** 1.15), v - 0.5)

        raw_screen_x = u_curved * float(self.screen_width - 1)
        raw_screen_y = v_curved * float(self.screen_height - 1)

        # 1€ Adaptive Low-Pass Filter
        smooth_x, smooth_y = self.cursor_filter.filter(raw_screen_x, raw_screen_y, timestamp=now)
        velocity = self.cursor_filter.last_velocity

        # 4. OS-Level Sticky Aim Assist (clings directly onto buttons, icons, links)
        is_locked = False
        target_desc = None
        if not self.is_dragging:
            snapped_x, snapped_y, is_locked, target_desc = self.target_lock.apply_magnetic_lock(
                smooth_x, smooth_y, velocity=velocity, timestamp=now
            )
        else:
            snapped_x, snapped_y = int(smooth_x), int(smooth_y)

        current_screen_x = snapped_x
        current_screen_y = snapped_y

        action = "MOVE"

        # 5. Drag & Drop State Machine (Super Pose: Index-Thumb + 3 Fingers Up)
        if drag_pose_active:
            if not self.is_dragging:
                if self.pinch_start_time == 0.0:
                    self.pinch_start_time = now
                elif (now - self.pinch_start_time) >= 0.14:
                    self.is_dragging = True
                    action = "DRAG_START"
            else:
                action = "DRAG_MOVE"
            self.last_screen_x = current_screen_x
            self.last_screen_y = current_screen_y
            return {
                "active": True, "cursor_x": current_screen_x, "cursor_y": current_screen_y,
                "action": action, "tap_ratio": d_thumb_index, "is_locked": is_locked,
                "target_desc": "PINCH DRAG",
            }
        elif self.is_dragging:
            self.is_dragging = False
            self.pinch_start_time = 0.0
            action = "DRAG_RELEASE"
            self.last_screen_x = current_screen_x
            self.last_screen_y = current_screen_y
            return {
                "active": True, "cursor_x": current_screen_x, "cursor_y": current_screen_y,
                "action": action, "tap_ratio": d_thumb_index, "is_locked": is_locked,
                "target_desc": None,
            }

        # 6. Right-Click State Machine (Index on Middle Tap)
        if self.right_click_state == "UP":
            if is_right_contact:
                self.right_click_state = "DOWN"
                self.right_tap_start_time = now
                action = "RIGHT_CONTACT"
        elif self.right_click_state == "DOWN":
            if not is_right_contact or d_index_middle > self.right_tap_up_ratio:
                self.right_click_state = "UP"
                action = "RIGHT_CLICK"
            elif (now - self.right_tap_start_time) > 0.40:
                self.right_click_state = "UP"

        # 7. Left-Click State Machine (Closed-Fist Index-Thumb Tap, ZERO CURSOR JAMMING)
        if self.tap_state == "UP":
            if is_left_contact:
                self.tap_state = "DOWN"
                self.tap_start_time = now
                action = "TAP_CONTACT"
        elif self.tap_state == "DOWN":
            contact_duration = now - self.tap_start_time
            if not is_left_contact or d_thumb_index > self.tap_up_ratio:
                self.tap_state = "UP"
                click_pos = (current_screen_x, current_screen_y)

                if (now - self.last_click_time) <= self.double_click_window:
                    dx_prev = click_pos[0] - self.last_click_pos[0]
                    dy_prev = click_pos[1] - self.last_click_pos[1]
                    if math.hypot(dx_prev, dy_prev) <= 220.0:
                        action = "DOUBLE_CLICK"
                        self.last_click_time = 0.0
                    else:
                        action = "CLICK"
                        self.last_click_time = now
                        self.last_click_pos = click_pos
                else:
                    action = "CLICK"
                    self.last_click_time = now
                    self.last_click_pos = click_pos

                if self.on_click_callback:
                    self.on_click_callback()

            elif contact_duration > 0.40:
                self.tap_state = "UP"

        self.last_screen_x = current_screen_x
        self.last_screen_y = current_screen_y
        self.last_is_locked = is_locked
        self.last_target_desc = target_desc

        return {
            "active": True,
            "cursor_x": current_screen_x,
            "cursor_y": current_screen_y,
            "action": action,
            "tap_ratio": d_thumb_index if fist_closed else 1.0,
            "super_detected": three_fingers_up and (d_thumb_index < self.pinch_drag_threshold),
            "is_locked": is_locked,
            "target_desc": target_desc,
        }
