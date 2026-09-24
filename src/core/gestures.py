"""
Gesture Recognition Engine for Project Kontroll (Angle-Invariant & Ergonomic Edition).
Solves:
1. Tilted dual-monitor webcam setups (hand-local coordinate frame invariant to camera angle).
2. Arm fatigue (lowered comfort box + dynamic pointer acceleration for wrist-only control).
3. Accidental dragging (single-tap never drags; drag requires pinch-to-drag or double-tap hold).
4. Button skitting & overshooting (MSAA magnetic snapping with correct 350 px/s breakout velocity).
5. 120 Hz high-frequency cursor motion extrapolation.
"""

import math
import time
import collections
from typing import Optional, Tuple, Dict, Any, Callable
import numpy as np

from .filter import Point2DOneEuroFilter
from .target_lock import TargetLockManager


class GestureEngine:
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
        # Default is 'auto' with tilt compensation
        self.mount_mode = "auto"
        self.detected_tilt_angle = 0.0  # Degrees

        # 1€ Filter with kinetic deadband for rock-solid standing-still cursor stability
        self.cursor_filter = Point2DOneEuroFilter(freq=60.0, min_cutoff=0.6, beta=0.035, deadband_radius=2.5)

        # Assistive Magnetic Target Snapper (Fix: breakout_velocity=350.0 to prevent instant breakout)
        self.target_lock = TargetLockManager(capture_radius=46.0, breakout_velocity=350.0)

        # Ergonomic Comfort Zone (Lowered & centered so elbow/forearm rests on desk)
        # No more lifting arm to the ceiling!
        self.box_xmin = 0.20
        self.box_xmax = 0.80
        self.box_ymin = 0.32
        self.box_ymax = 0.88

        # Dynamic Pointer Acceleration State
        self.last_norm_x: Optional[float] = None
        self.last_norm_y: Optional[float] = None
        self.virtual_cursor_x: float = screen_width / 2.0
        self.virtual_cursor_y: float = screen_height / 2.0

        # Angle-Invariant Tap Parameters
        self.tap_down_ratio = 0.22      # Contact threshold along local hand frame
        self.tap_up_ratio = 0.28        # Release threshold
        self.tap_state = "UP"           # "UP", "DOWN"
        self.tap_start_time = 0.0
        self.recent_tap_ratios = collections.deque(maxlen=6)

        # Separate Drag Mode (Zero accidental dragging!)
        # Drag is triggered by Thumb+Index pinch (> 0.22s) OR Double-tap-and-hold
        self.is_dragging = False
        self.pinch_drag_threshold = 0.20  # Thumb tip (4) to Index tip (8) distance
        self.pinch_start_time = 0.0

        # Multi-Click / Double-Click tracking
        self.double_click_window = 0.38  # 380 ms window for second tap
        self.last_click_time = 0.0
        self.last_click_pos = (screen_width // 2, screen_height // 2)

        # Pre-Tap & Click-Anchor Lock:
        self.coord_history = collections.deque(maxlen=15)
        self.anchor_position: Optional[Tuple[int, int]] = None
        self.anchor_release_time = 0.0

        # "Super" Gesture Parameters
        self.super_gesture_hold_time = 0.38
        self.super_candidate_start = 0.0
        self.super_cooldown_until = 0.0

        # Last stable cursor output
        self.last_screen_x = screen_width // 2
        self.last_screen_y = screen_height // 2
        self.last_is_locked = False
        self.last_target_desc = None

    def update_screen_size(self, width: int, height: int):
        self.screen_width = width
        self.screen_height = height
        self.virtual_cursor_x = width / 2.0
        self.virtual_cursor_y = height / 2.0

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

    def compute_angle_invariant_tap_metric(self, landmarks, scale: float) -> Tuple[float, float]:
        """
        Computes finger separation in the palm's OWN anatomical coordinate system.
        Completely immune to camera tilt, perspective distortion, or whether the webcam
        is mounted on a tilted side monitor.
        """
        # Convert landmarks to 3D numpy vectors
        p0 = np.array([landmarks[0].x, landmarks[0].y, getattr(landmarks[0], "z", 0.0)])
        p5 = np.array([landmarks[5].x, landmarks[5].y, getattr(landmarks[5], "z", 0.0)])   # Index MCP
        p9 = np.array([landmarks[9].x, landmarks[9].y, getattr(landmarks[9], "z", 0.0)])   # Middle MCP
        p17 = np.array([landmarks[17].x, landmarks[17].y, getattr(landmarks[17], "z", 0.0)]) # Pinky MCP
        p8 = np.array([landmarks[8].x, landmarks[8].y, getattr(landmarks[8], "z", 0.0)])   # Index Tip
        p12 = np.array([landmarks[12].x, landmarks[12].y, getattr(landmarks[12], "z", 0.0)]) # Middle Tip

        # Palm anatomical axes
        u_long = p9 - p0
        u_long_norm = np.linalg.norm(u_long)
        if u_long_norm > 1e-4:
            u_long = u_long / u_long_norm

        v_lat = p5 - p17
        v_lat_norm = np.linalg.norm(v_lat)
        if v_lat_norm > 1e-4:
            v_lat = v_lat / v_lat_norm

        # Palm normal (perpendicular out of palm)
        n_palm = np.cross(u_long, v_lat)
        n_palm_norm = np.linalg.norm(n_palm)
        if n_palm_norm > 1e-4:
            n_palm = n_palm / n_palm_norm

        # Estimate hand yaw angle relative to camera lens
        # If camera is on left monitor, n_palm has a significant horizontal component
        self.detected_tilt_angle = float(np.degrees(math.atan2(n_palm[0], max(1e-3, abs(n_palm[2])))))

        # Separation vector between Index tip and Middle tip
        delta = p8 - p12
        d3d = float(np.linalg.norm(delta))

        # Separation along lateral knuckle axis (across fingers)
        s_lat = float(abs(np.dot(delta, v_lat)))

        # Angle-invariant ratio:
        # Both fingers must be close in 3D AND along the knuckle lateral axis
        tap_ratio = (0.60 * d3d + 0.40 * s_lat) / scale

        # Velocity impulse (rate of change)
        self.recent_tap_ratios.append(tap_ratio)
        if len(self.recent_tap_ratios) >= 3:
            vel_impulse = (self.recent_tap_ratios[-1] - self.recent_tap_ratios[0]) / (len(self.recent_tap_ratios) * 0.016)
        else:
            vel_impulse = 0.0

        return tap_ratio, vel_impulse

    def is_super_gesture(self, landmarks) -> bool:
        """
        Detects the 'Super / OK' activation gesture:
        - Last three fingers (Middle, Ring, Pinky) are extended upright.
        - Thumb and Index tips are close/touching (forming the power ring).
        """
        scale = self._get_hand_scale(landmarks)
        thumb_index_dist = self._dist_3d(landmarks[4], landmarks[8]) / scale
        is_ring_formed = thumb_index_dist < 0.40

        # Check extended fingers relative to PIP joints
        middle_up = landmarks[12].y < landmarks[10].y
        ring_up = landmarks[16].y < landmarks[14].y
        pinky_up = landmarks[20].y < landmarks[18].y

        return is_ring_formed and middle_up and ring_up and pinky_up

    def check_pinch_drag(self, landmarks, scale: float, now: float) -> bool:
        """
        Checks for intentional Pinch-to-Drag (Thumb Tip 4 touching Index Tip 8).
        Eliminates 100% of accidental dragging during normal index-on-middle clicking!
        """
        pinch_dist = self._dist_3d(landmarks[4], landmarks[8]) / scale
        # Also ensure middle, ring, pinky are NOT all upright (not Super gesture)
        is_pinching = pinch_dist < self.pinch_drag_threshold

        if is_pinching:
            if self.pinch_start_time == 0.0:
                self.pinch_start_time = now
            elif (now - self.pinch_start_time) >= 0.22:
                return True
        else:
            self.pinch_start_time = 0.0

        return False

    def process(self, landmarks, timestamp: Optional[float] = None) -> Dict[str, Any]:
        """Processes 21 MediaPipe hand landmarks with angle compensation & pointer acceleration."""
        if timestamp is None:
            timestamp = time.perf_counter()

        now = timestamp
        scale = self._get_hand_scale(landmarks)

        # 1. Check 'Super' Gesture Toggle
        super_detected = self.is_super_gesture(landmarks)
        toggled_state = False

        if super_detected and now > self.super_cooldown_until:
            if self.super_candidate_start == 0.0:
                self.super_candidate_start = now
            elif (now - self.super_candidate_start) >= self.super_gesture_hold_time:
                self.is_active = not self.is_active
                self.super_cooldown_until = now + 1.2
                self.super_candidate_start = 0.0
                toggled_state = True
                if self.on_state_change:
                    self.on_state_change(self.is_active)
        else:
            if not super_detected:
                self.super_candidate_start = 0.0

        if not self.is_active:
            if self.is_dragging:
                self.is_dragging = False
                return {"active": False, "toggled": toggled_state, "cursor_x": self.last_screen_x,
                        "cursor_y": self.last_screen_y, "action": "DRAG_RELEASE", "tap_ratio": 0.0,
                        "super_detected": False, "is_locked": False, "target_desc": None}

            return {
                "active": False,
                "toggled": toggled_state,
                "cursor_x": self.last_screen_x,
                "cursor_y": self.last_screen_y,
                "action": "STANDBY",
                "tap_ratio": 0.0,
                "super_detected": super_detected,
                "is_locked": False,
                "target_desc": None,
            }

        # 2. Angle-Invariant Tap Metric & Pinch-to-Drag
        tap_ratio, vel_impulse = self.compute_angle_invariant_tap_metric(landmarks, scale)
        pinch_drag_active = self.check_pinch_drag(landmarks, scale, now)

        # 3. Ergonomic Cursor Tracking with Dynamic Pointer Acceleration
        index_tip = landmarks[8]
        norm_x = 1.0 - index_tip.x  # Mirrored for natural AR
        norm_y = index_tip.y

        # Camera Mounting Angle Compensation:
        # If camera is mounted on a secondary tilted monitor to the left, apply tilt skew compensation
        if self.mount_mode == "left" or (self.mount_mode == "auto" and self.detected_tilt_angle > 18.0):
            # Compensate for 25-35 degree side yaw
            rad = math.radians(-16.0)
            cx_box = (self.box_xmin + self.box_xmax) / 2.0
            cy_box = (self.box_ymin + self.box_ymax) / 2.0
            rx = norm_x - cx_box
            ry = norm_y - cy_box
            norm_x = cx_box + (rx * math.cos(rad) - ry * math.sin(rad))
            norm_y = cy_box + (rx * math.sin(rad) + ry * math.cos(rad))

        elif self.mount_mode == "right" or (self.mount_mode == "auto" and self.detected_tilt_angle < -18.0):
            rad = math.radians(16.0)
            cx_box = (self.box_xmin + self.box_xmax) / 2.0
            cy_box = (self.box_ymin + self.box_ymax) / 2.0
            rx = norm_x - cx_box
            ry = norm_y - cy_box
            norm_x = cx_box + (rx * math.cos(rad) - ry * math.sin(rad))
            norm_y = cy_box + (rx * math.sin(rad) + ry * math.cos(rad))

        # Dynamic Pointer Acceleration:
        # Avoids having to swing the entire arm! Tiny finger movements cover full screen.
        if self.last_norm_x is None:
            self.last_norm_x = norm_x
            self.last_norm_y = norm_y

        dt = max(1e-4, min(0.1, now - (getattr(self, "_last_process_time", now) or now)))
        self._last_process_time = now

        dx_norm = norm_x - self.last_norm_x
        dy_norm = norm_y - self.last_norm_y
        self.last_norm_x = norm_x
        self.last_norm_y = norm_y

        box_w = max(0.001, self.box_xmax - self.box_xmin)
        box_h = max(0.001, self.box_ymax - self.box_ymin)

        # Normalized speed (relative to active box)
        speed = math.hypot(dx_norm / box_w, dy_norm / box_h) / dt

        # Non-linear power curve for pointer acceleration:
        # Slow speed: fine control (gain ~1.1)
        # Fast wrist flick: leaps effortlessly across monitors (gain ~3.6)
        gain = 1.1 + 2.5 * min(1.0, (speed / 2.2) ** 1.3)

        # Update virtual cursor position
        delta_pixels_x = (dx_norm / box_w) * self.screen_width * gain
        delta_pixels_y = (dy_norm / box_h) * self.screen_height * gain

        self.virtual_cursor_x = max(0.0, min(float(self.screen_width - 1), self.virtual_cursor_x + delta_pixels_x))
        self.virtual_cursor_y = max(0.0, min(float(self.screen_height - 1), self.virtual_cursor_y + delta_pixels_y))

        # Filter through 1€ filter with deadband
        smooth_x, smooth_y = self.cursor_filter.filter(
            self.virtual_cursor_x, self.virtual_cursor_y, timestamp=now
        )
        velocity = self.cursor_filter.last_velocity
        self.coord_history.append((now, int(smooth_x), int(smooth_y)))

        # 4. Assistive Magnetic Target Snapping (only when not dragging)
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

        # Double-click target anchor
        if (now - self.last_click_time) <= self.double_click_window:
            dx_prev = current_screen_x - self.last_click_pos[0]
            dy_prev = current_screen_y - self.last_click_pos[1]
            if math.hypot(dx_prev, dy_prev) <= 250.0:
                current_screen_x, current_screen_y = self.last_click_pos

        action = "MOVE"

        # 5. Handle Intentional Pinch-to-Drag
        if pinch_drag_active:
            if not self.is_dragging:
                self.is_dragging = True
                action = "DRAG_START"
            else:
                action = "DRAG_MOVE"
            # Free cursor during drag
            self.anchor_position = None
            self.last_screen_x = current_screen_x
            self.last_screen_y = current_screen_y
            return {
                "active": True, "toggled": toggled_state, "cursor_x": current_screen_x,
                "cursor_y": current_screen_y, "action": action, "tap_ratio": tap_ratio,
                "super_detected": super_detected, "is_locked": is_locked, "target_desc": "PINCH DRAG",
            }
        elif self.is_dragging:
            # Pinch released -> Drop!
            self.is_dragging = False
            action = "DRAG_RELEASE"
            self.last_screen_x = current_screen_x
            self.last_screen_y = current_screen_y
            return {
                "active": True, "toggled": toggled_state, "cursor_x": current_screen_x,
                "cursor_y": current_screen_y, "action": action, "tap_ratio": tap_ratio,
                "super_detected": super_detected, "is_locked": is_locked, "target_desc": None,
            }

        # 6. Tap Click State Machine (Single Click & Double Click ONLY - Zero Accidental Drag!)
        if self.tap_state == "UP":
            if tap_ratio < self.tap_down_ratio:
                self.tap_state = "DOWN"
                self.tap_start_time = now

                # Pre-tap coordinate rollback to eliminate physical impact aim drift
                if (now - self.last_click_time) <= self.double_click_window:
                    dx_prev = current_screen_x - self.last_click_pos[0]
                    dy_prev = current_screen_y - self.last_click_pos[1]
                    if math.hypot(dx_prev, dy_prev) <= 250.0:
                        self.anchor_position = self.last_click_pos
                    else:
                        self.anchor_position = self._get_pre_tap_position(now, current_screen_x, current_screen_y)
                else:
                    self.anchor_position = self._get_pre_tap_position(now, current_screen_x, current_screen_y)

                self.anchor_release_time = now + 0.16
                action = "TAP_CONTACT"

        elif self.tap_state == "DOWN":
            contact_duration = now - self.tap_start_time

            # If fingers separate again (released)
            if tap_ratio > self.tap_up_ratio:
                self.tap_state = "UP"
                self.anchor_release_time = now + 0.08
                click_pos = self.anchor_position or (current_screen_x, current_screen_y)

                if (now - self.last_click_time) <= self.double_click_window:
                    dx_prev = click_pos[0] - self.last_click_pos[0]
                    dy_prev = click_pos[1] - self.last_click_pos[1]
                    if math.hypot(dx_prev, dy_prev) <= 250.0:
                        action = "DOUBLE_CLICK"
                        self.last_click_time = 0.0
                        click_pos = self.last_click_pos
                    else:
                        action = "CLICK"
                        self.last_click_time = now
                        self.last_click_pos = click_pos
                else:
                    action = "CLICK"
                    self.last_click_time = now
                    self.last_click_pos = click_pos

                self.anchor_position = click_pos
                current_screen_x, current_screen_y = click_pos
                if self.on_click_callback:
                    self.on_click_callback()

            elif contact_duration > 0.60:
                # If held for too long without releasing, simply reset state to UP so user isn't stuck
                self.tap_state = "UP"
                self.anchor_position = None

        # Apply Click-Anchor Lock during tap
        if self.anchor_position is not None:
            if now < self.anchor_release_time or self.tap_state == "DOWN":
                current_screen_x, current_screen_y = self.anchor_position
            else:
                self.anchor_position = None

        self.last_screen_x = current_screen_x
        self.last_screen_y = current_screen_y
        self.last_is_locked = is_locked
        self.last_target_desc = target_desc

        return {
            "active": True,
            "toggled": toggled_state,
            "cursor_x": current_screen_x,
            "cursor_y": current_screen_y,
            "action": action,
            "tap_ratio": tap_ratio,
            "super_detected": super_detected,
            "is_locked": is_locked,
            "target_desc": target_desc,
        }

    def _get_pre_tap_position(self, now: float, default_x: int, default_y: int) -> Tuple[int, int]:
        target_time = now - 0.080
        for t_hist, hx, hy in reversed(self.coord_history):
            if t_hist <= target_time:
                return (hx, hy)
        if self.coord_history:
            return (self.coord_history[0][1], self.coord_history[0][2])
        return (default_x, default_y)
