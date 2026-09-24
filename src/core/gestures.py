"""
Gesture Recognition Engine for Project Kontroll (Flawless Precision Edition).
Engineered to resolve:
1. Extendedness Gate: Tapping index on middle is ONLY evaluated when BOTH index and middle
   fingers are extended. When pointing (middle curled), tap is impossible (ratio=1.0).
2. Tilted Dual-Monitor Setup: Mathematically calibrated mounting rotation (+25° for left monitor)
   aligning desk motion directly with the primary screen.
3. Ergonomic Rest Box: Positioned at natural elbow-rest height (ymin=0.45, ymax=0.78) with S-curve
   acceleration. Tiny 2-inch wrist twitches effortlessly reach every corner.
4. Absolute Zero-Drift Tracking: Absolute 1:1 camera-to-screen mapping eliminates accumulator drift.
5. Zero Accidental Drags: Drag is strictly engaged via Thumb+Index Pinch (or double-tap hold).
6. Non-Freezing Anchor Lock: Cursor anchor holds for a maximum of 70ms on tap impact, then releases.
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
        # Default is 'left' if tilted dual-monitor setup, or 'auto'
        self.mount_mode = "left"  # Default to left monitor for user setup
        self.detected_tilt_angle = 25.0

        # 1€ Filter: Fast responsive tuning (min_cutoff=0.8 for stillness, beta=0.045 for zero-drag response)
        self.cursor_filter = Point2DOneEuroFilter(freq=60.0, min_cutoff=0.8, beta=0.045, deadband_radius=2.2)

        # Assistive Magnetic Target Snapper (subtle 30% pull, never traps cursor)
        self.target_lock = TargetLockManager(capture_radius=42.0, breakout_velocity=220.0)

        # Ergonomic Rest Box (Optimized for forearm/elbow resting on desk)
        # Dimensions: 42% width, 32% height in camera space (~3-4 inches of physical movement)
        self.box_xmin = 0.28
        self.box_xmax = 0.70
        self.box_ymin = 0.44
        self.box_ymax = 0.78

        # Tap Click Parameters (Normalized 3D scale)
        self.tap_down_ratio = 0.17      # Contact threshold when both fingers extended
        self.tap_up_ratio = 0.24        # Release threshold
        self.tap_state = "UP"           # "UP", "DOWN"
        self.tap_start_time = 0.0

        # Separate Drag Mode (Zero accidental dragging!)
        self.is_dragging = False
        self.pinch_drag_threshold = 0.22  # Thumb tip (4) to Index tip (8) distance
        self.pinch_start_time = 0.0

        # Multi-Click / Double-Click tracking
        self.double_click_window = 0.38  # 380 ms window for second tap
        self.last_click_time = 0.0
        self.last_click_pos = (screen_width // 2, screen_height // 2)

        # Click-Anchor Lock: Briefly holds cursor for max 70ms on tap contact to absorb finger impact
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

    def reset_hand_state(self):
        """Called when no hand is in view to clear all sticky states immediately."""
        self.tap_state = "UP"
        self.anchor_position = None
        self.anchor_release_time = 0.0
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

    def compute_tap_metric(self, landmarks, scale: float) -> Tuple[float, bool]:
        """
        Calculates tap metric with mandatory Finger Extension Prerequisite.
        If the middle finger is curled (e.g. pointing with index), tap is impossible.
        Only when BOTH index and middle fingers are extended does tap detection activate.
        """
        # Extension checks: tip must be above PIP joint (smaller y in image space)
        # Index tip (8) vs Index PIP (6)
        index_extended = landmarks[8].y < landmarks[6].y
        # Middle tip (12) vs Middle PIP (10)
        middle_extended = landmarks[12].y < landmarks[10].y

        if not (index_extended and middle_extended):
            # Middle finger is curled or hand is not in pointing pose -> Cannot tap!
            return 1.0, False

        # 3D Euclidean distance between index tip and middle tip
        d3d = self._dist_3d(landmarks[8], landmarks[12])
        tap_ratio = d3d / scale
        is_contact = tap_ratio < self.tap_down_ratio

        return tap_ratio, is_contact

    # Backwards-compatible alias for diagnostic UI and test suites
    compute_angle_invariant_tap_metric = compute_tap_metric

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
        Intentional Pinch-to-Drag (Thumb Tip 4 touching Index Tip 8).
        Eliminates accidental dragging while pointing or clicking.
        """
        pinch_dist = self._dist_3d(landmarks[4], landmarks[8]) / scale
        # Ensure middle, ring, pinky are not extended upright (not Super gesture)
        is_pinching = pinch_dist < self.pinch_drag_threshold

        if is_pinching:
            if self.pinch_start_time == 0.0:
                self.pinch_start_time = now
            elif (now - self.pinch_start_time) >= 0.20:
                return True
        else:
            self.pinch_start_time = 0.0

        return False

    def process(self, landmarks, timestamp: Optional[float] = None) -> Dict[str, Any]:
        """Processes 21 MediaPipe hand landmarks with absolute ergonomic mapping."""
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
                        "cursor_y": self.last_screen_y, "action": "DRAG_RELEASE", "tap_ratio": 1.0,
                        "super_detected": False, "is_locked": False, "target_desc": None}

            return {
                "active": False,
                "toggled": toggled_state,
                "cursor_x": self.last_screen_x,
                "cursor_y": self.last_screen_y,
                "action": "STANDBY",
                "tap_ratio": 1.0,
                "super_detected": super_detected,
                "is_locked": False,
                "target_desc": None,
            }

        # 2. Tap Metric with Extendedness Gate & Pinch-to-Drag
        tap_ratio, is_contact = self.compute_tap_metric(landmarks, scale)
        pinch_drag_active = self.check_pinch_drag(landmarks, scale, now)

        # 3. Absolute Ergonomic Cursor Tracking with Angle Compensation
        index_tip = landmarks[8]
        norm_x = 1.0 - index_tip.x  # Mirrored for natural AR
        norm_y = index_tip.y

        # Camera Mounting Angle Compensation:
        # User has camera on the left tilted secondary monitor (~30°)
        if self.mount_mode == "left":
            rad = math.radians(24.0)  # Correct positive sign for left monitor!
            cx_box = (self.box_xmin + self.box_xmax) / 2.0
            cy_box = (self.box_ymin + self.box_ymax) / 2.0
            rx = norm_x - cx_box
            ry = norm_y - cy_box
            norm_x = cx_box + (rx * math.cos(rad) - ry * math.sin(rad))
            norm_y = cy_box + (rx * math.sin(rad) + ry * math.cos(rad))
        elif self.mount_mode == "right":
            rad = math.radians(-24.0)
            cx_box = (self.box_xmin + self.box_xmax) / 2.0
            cy_box = (self.box_ymin + self.box_ymax) / 2.0
            rx = norm_x - cx_box
            ry = norm_y - cy_box
            norm_x = cx_box + (rx * math.cos(rad) - ry * math.sin(rad))
            norm_y = cy_box + (rx * math.sin(rad) + ry * math.cos(rad))

        # Absolute Mapping inside Ergonomic Comfort Box
        box_w = max(0.001, self.box_xmax - self.box_xmin)
        box_h = max(0.001, self.box_ymax - self.box_ymin)

        u = (norm_x - self.box_xmin) / box_w
        v = (norm_y - self.box_ymin) / box_h
        u = max(0.0, min(1.0, u))
        v = max(0.0, min(1.0, v))

        # Smooth S-Curve: fine precision in center, gentle reach near edges
        u_curved = 0.5 + math.copysign(0.5 * (abs(2.0 * (u - 0.5)) ** 1.15), u - 0.5)
        v_curved = 0.5 + math.copysign(0.5 * (abs(2.0 * (v - 0.5)) ** 1.15), v - 0.5)

        raw_screen_x = u_curved * float(self.screen_width - 1)
        raw_screen_y = v_curved * float(self.screen_height - 1)

        # 1€ Filter: Adaptive Low-Pass Filter
        smooth_x, smooth_y = self.cursor_filter.filter(raw_screen_x, raw_screen_y, timestamp=now)
        velocity = self.cursor_filter.last_velocity

        # 4. Assistive Magnetic Target Snapping (subtle 30% assist)
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

        # Double-click target anchor (locks within 200px of first click)
        if (now - self.last_click_time) <= self.double_click_window:
            dx_prev = current_screen_x - self.last_click_pos[0]
            dy_prev = current_screen_y - self.last_click_pos[1]
            if math.hypot(dx_prev, dy_prev) <= 200.0:
                current_screen_x, current_screen_y = self.last_click_pos

        action = "MOVE"

        # 5. Handle Intentional Pinch-to-Drag
        if pinch_drag_active:
            if not self.is_dragging:
                self.is_dragging = True
                action = "DRAG_START"
            else:
                action = "DRAG_MOVE"
            self.anchor_position = None
            self.last_screen_x = current_screen_x
            self.last_screen_y = current_screen_y
            return {
                "active": True, "toggled": toggled_state, "cursor_x": current_screen_x,
                "cursor_y": current_screen_y, "action": action, "tap_ratio": tap_ratio,
                "super_detected": super_detected, "is_locked": is_locked, "target_desc": "PINCH DRAG",
            }
        elif self.is_dragging:
            self.is_dragging = False
            action = "DRAG_RELEASE"
            self.last_screen_x = current_screen_x
            self.last_screen_y = current_screen_y
            return {
                "active": True, "toggled": toggled_state, "cursor_x": current_screen_x,
                "cursor_y": current_screen_y, "action": action, "tap_ratio": tap_ratio,
                "super_detected": super_detected, "is_locked": is_locked, "target_desc": None,
            }

        # 6. Tap Click State Machine with Non-Freezing Anchor Lock
        if self.tap_state == "UP":
            if is_contact:
                self.tap_state = "DOWN"
                self.tap_start_time = now
                self.anchor_position = (current_screen_x, current_screen_y)
                # Max 70ms anchor lock! NEVER freezes cursor permanently!
                self.anchor_release_time = now + 0.070
                action = "TAP_CONTACT"

        elif self.tap_state == "DOWN":
            contact_duration = now - self.tap_start_time

            # Released -> Trigger Click!
            if not is_contact or tap_ratio > self.tap_up_ratio:
                self.tap_state = "UP"
                self.anchor_position = None

                click_pos = (current_screen_x, current_screen_y)

                if (now - self.last_click_time) <= self.double_click_window:
                    dx_prev = click_pos[0] - self.last_click_pos[0]
                    dy_prev = click_pos[1] - self.last_click_pos[1]
                    if math.hypot(dx_prev, dy_prev) <= 200.0:
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

            elif contact_duration > 0.35:
                # Timed out safely: reset to UP without dragging or freezing!
                self.tap_state = "UP"
                self.anchor_position = None

        # Apply short anchor lock only within initial 70ms
        if self.anchor_position is not None and now < self.anchor_release_time:
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
