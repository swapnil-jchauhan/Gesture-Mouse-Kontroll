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
        self.target_lock = TargetLockManager(capture_radius=42.0, breakout_velocity=750.0)

        # Ergonomic Rest Box (forearm/elbow resting on desk, compact wrist flick)
        self.box_xmin = 0.36
        self.box_xmax = 0.64
        self.box_ymin = 0.46
        self.box_ymax = 0.74

        # Left Click Parameters: Closed-Fist Index-Thumb Tap
        self.tap_down_ratio = 0.27
        self.tap_up_ratio = 0.35
        self.tap_state = "UP"  # "UP", "DOWN"
        self.tap_start_time = 0.0

        # Right Click Parameters: Index-on-Middle Tap
        self.right_tap_down_ratio = 0.26
        self.right_tap_up_ratio = 0.34
        self.right_click_state = "UP"
        self.right_tap_start_time = 0.0

        # Drag Mode: Index-Thumb with 3 Fingers UP
        self.is_dragging = False
        self.pinch_drag_threshold = 0.28
        self.pinch_start_time = 0.0

        # Shaka Activation Gesture (Pinky & Thumb OUT, 3 Middle Fingers Curled)
        self.shaka_start_time = 0.0
        self.shaka_triggered = False
        self.shaka_hold_duration = 0.35

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
        self.shaka_start_time = 0.0
        self.shaka_triggered = False
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
        In a fist, tips are folded down towards the palm/knuckles in 3D.
        """
        # 3D distance from fingertips to their MCP knuckles (9, 13, 17)
        d_m_mcp = self._dist_3d(landmarks[12], landmarks[9]) / scale
        d_r_mcp = self._dist_3d(landmarks[16], landmarks[13]) / scale
        d_p_mcp = self._dist_3d(landmarks[20], landmarks[17]) / scale

        # 3D distance to wrist (0)
        d_m_wrist = self._dist_3d(landmarks[12], landmarks[0]) / scale
        d_r_wrist = self._dist_3d(landmarks[16], landmarks[0]) / scale
        d_p_wrist = self._dist_3d(landmarks[20], landmarks[0]) / scale

        m_curled = (d_m_mcp < 0.70) or (d_m_wrist < 1.25) or (landmarks[12].y >= landmarks[10].y - 0.03)
        r_curled = (d_r_mcp < 0.70) or (d_r_wrist < 1.25) or (landmarks[16].y >= landmarks[14].y - 0.03)
        p_curled = (d_p_mcp < 0.70) or (d_p_wrist < 1.25) or (landmarks[20].y >= landmarks[18].y - 0.03)

        return m_curled and r_curled and p_curled

    def are_last_three_up(self, landmarks) -> bool:
        """
        Detects if the last three fingers (Middle, Ring, Pinky) are extended upright.
        """
        scale = self._get_hand_scale(landmarks)
        d_m_mcp = self._dist_3d(landmarks[12], landmarks[9]) / scale
        d_r_mcp = self._dist_3d(landmarks[16], landmarks[13]) / scale
        d_p_mcp = self._dist_3d(landmarks[20], landmarks[17]) / scale

        d_m_wrist = self._dist_3d(landmarks[12], landmarks[0]) / scale
        d_r_wrist = self._dist_3d(landmarks[16], landmarks[0]) / scale
        d_p_wrist = self._dist_3d(landmarks[20], landmarks[0]) / scale

        m_up = (d_m_mcp > 0.55) or (d_m_wrist > 1.05) or (landmarks[12].y < landmarks[10].y)
        r_up = (d_r_mcp > 0.55) or (d_r_wrist > 1.05) or (landmarks[16].y < landmarks[14].y)
        p_up = (d_p_mcp > 0.50) or (d_p_wrist > 0.95) or (landmarks[20].y < landmarks[18].y)
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

    def is_shaka_gesture(self, landmarks) -> bool:
        """
        Detects the Shaka Activation Gesture (🤙):
        Thumb (4) and Pinky (20) are fully extended OUT,
        while Index (8), Middle (12), and Ring (16) are curled IN against the palm.
        """
        scale = self._get_hand_scale(landmarks)

        # Thumb (4) and Pinky (20) distance from wrist (0)
        d_thumb_wrist = self._dist_3d(landmarks[4], landmarks[0]) / scale
        d_pinky_wrist = self._dist_3d(landmarks[20], landmarks[0]) / scale
        d_thumb_pinky = self._dist_3d(landmarks[4], landmarks[20]) / scale

        # Index (8), Middle (12), Ring (16) distance from wrist
        d_index_wrist = self._dist_3d(landmarks[8], landmarks[0]) / scale
        d_middle_wrist = self._dist_3d(landmarks[12], landmarks[0]) / scale
        d_ring_wrist = self._dist_3d(landmarks[16], landmarks[0]) / scale

        # Knuckle clearances
        d_thumb_index_mcp = self._dist_3d(landmarks[4], landmarks[5]) / scale
        d_pinky_mcp = self._dist_3d(landmarks[20], landmarks[17]) / scale

        thumb_extended = (d_thumb_wrist > 0.95) and (d_thumb_index_mcp > 0.50)
        pinky_extended = (d_pinky_wrist > 1.05) and (d_pinky_mcp > 0.50)

        index_curled = (landmarks[8].y >= landmarks[6].y - 0.035) or (d_index_wrist < 1.25)
        middle_curled = (landmarks[12].y >= landmarks[10].y - 0.035) or (d_middle_wrist < 1.25)
        ring_curled = (landmarks[16].y >= landmarks[14].y - 0.035) or (d_ring_wrist < 1.25)

        return (
            thumb_extended
            and pinky_extended
            and index_curled
            and middle_curled
            and ring_curled
            and (d_thumb_pinky > 1.30)
        )

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

        # 0. Shaka Activation / Toggle Gesture Detection (Pinky & Thumb OUT)
        shaka_pose_active = self.is_shaka_gesture(landmarks)
        if shaka_pose_active:
            if self.shaka_start_time == 0.0:
                self.shaka_start_time = now
            elif (now - self.shaka_start_time) >= self.shaka_hold_duration and not self.shaka_triggered:
                self.is_active = not self.is_active
                self.shaka_triggered = True
                if self.on_state_change:
                    self.on_state_change(self.is_active)
        else:
            self.shaka_start_time = 0.0
            self.shaka_triggered = False

        if not self.is_active:
            return {
                "active": False,
                "shaka_active": shaka_pose_active,
                "cursor_x": self.last_screen_x,
                "cursor_y": self.last_screen_y,
                "action": "STANDBY",
                "is_locked": False,
                "target_desc": None,
            }

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
        d_idx_mcp = self._dist_3d(landmarks[8], landmarks[5]) / scale
        d_mid_mcp = self._dist_3d(landmarks[12], landmarks[9]) / scale
        index_extended = (d_idx_mcp > 0.52) or (self._dist_3d(landmarks[8], landmarks[0]) / scale > 1.05) or (landmarks[8].y < landmarks[6].y + 0.02)
        middle_extended = (d_mid_mcp > 0.52) or (self._dist_3d(landmarks[12], landmarks[0]) / scale > 1.05) or (landmarks[12].y < landmarks[10].y + 0.02)
        is_right_contact = (d_index_middle < self.right_tap_down_ratio) and index_extended and middle_extended

        # Click Intent / Active Tap Detection:
        click_intent = (
            is_left_contact
            or (self.tap_state == "DOWN")
            or is_right_contact
            or (self.right_click_state == "DOWN")
            or (d_thumb_index < self.tap_up_ratio * 1.35 and fist_closed)
            or (d_index_middle < self.right_tap_up_ratio * 1.35 and index_extended and middle_extended)
            or ((now - self.last_click_time) < 0.25)
        )

        # 2. Cursor Tracking Point: Index Fingertip (Horizontally Mirrored)
        norm_x = 1.0 - landmarks[8].x
        norm_y = landmarks[8].y

        # Camera Tilt Correction
        rot_angle = 0.0
        if self.mount_mode == "auto":
            dx_hand = (1.0 - landmarks[9].x) - (1.0 - landmarks[0].x)
            dy_hand = landmarks[9].y - landmarks[0].y
            if dy_hand < -0.05:
                tilt_deg = math.degrees(math.atan2(dx_hand, -dy_hand))
                self.detected_tilt_angle = tilt_deg
                if abs(tilt_deg) > 12.0:
                    rot_angle = -math.radians(tilt_deg)
        elif self.mount_mode == "left":
            rot_angle = math.radians(-24.0)
        elif self.mount_mode == "right":
            rot_angle = math.radians(24.0)

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
                smooth_x, smooth_y, velocity=velocity, timestamp=now, is_clicking=click_intent
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
            "shaka_active": shaka_pose_active,
            "cursor_x": current_screen_x,
            "cursor_y": current_screen_y,
            "action": action,
            "tap_ratio": d_thumb_index if fist_closed else 1.0,
            "super_detected": three_fingers_up and (d_thumb_index < self.pinch_drag_threshold),
            "is_locked": is_locked,
            "target_desc": target_desc,
        }
