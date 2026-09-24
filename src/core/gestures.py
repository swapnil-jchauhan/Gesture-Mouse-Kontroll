"""
Gesture Recognition Engine for Project Kontroll.
Mathematically models:
1. Active Screen Mapping (with ergonomic bounding box to eliminate arm fatigue)
2. Dual-Stage Kinetic Stabilization (Deadband + 1€ Filter for 0px jitter near tiny icons)
3. Smart Magnetic Target Snapping (locks onto folders, close [X], minimize [_], maximize [□], buttons)
4. Scale-Invariant Pre-Tap Anchored Click & Drag State Machine (Instant Single Click, Fast Double Click, Deliberate Drag)
5. "Super" Activation Gesture (Thumb-Index ring with last three fingers upright)
"""

import math
import time
import collections
from typing import Optional, Tuple, Dict, Any, Callable
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
        self.is_active = True  # Starts active, toggleable via Super Gesture

        # 1€ Filter with kinetic deadband for rock-solid standing-still cursor stability
        self.cursor_filter = Point2DOneEuroFilter(freq=60.0, min_cutoff=0.5, beta=0.025, deadband_radius=2.8)

        # Assistive Magnetic Target Snapper (snaps into buttons, icons, window controls)
        self.target_lock = TargetLockManager(capture_radius=36.0, breakout_velocity=32.0)

        # Virtual Mousepad Active Box (Percentage of camera frame: [xmin, ymin, xmax, ymax])
        # Using 65% center area ensures easy corner reach with minimal hand movement
        self.box_xmin = 0.18
        self.box_xmax = 0.82
        self.box_ymin = 0.20
        self.box_ymax = 0.85

        # Tap Click Parameters (Normalized 2D Camera Plane)
        self.tap_down_ratio = 0.25      # Contact threshold between Index & Middle tips
        self.tap_up_ratio = 0.32        # Release threshold with hysteresis (clean separation)
        self.tap_state = "UP"           # "UP", "DOWN", "DRAG"
        self.tap_start_time = 0.0
        self.drag_hold_duration = 0.42  # Seconds of contact before engaging drag lock (420 ms)

        # Multi-Click / Double-Click tracking
        self.double_click_window = 0.40  # 400 ms window for second tap
        self.last_click_time = 0.0
        self.last_click_pos = (screen_width // 2, screen_height // 2)

        # Pre-Tap & Click-Anchor Lock:
        # Buffer of (timestamp, x, y) from recent frames to freeze to the pre-tap coordinate
        self.coord_history = collections.deque(maxlen=15)
        self.anchor_position: Optional[Tuple[int, int]] = None
        self.anchor_release_time = 0.0

        # "Super" Gesture Parameters
        self.super_gesture_hold_time = 0.40  # Seconds pose must be held to toggle
        self.super_candidate_start = 0.0
        self.super_cooldown_until = 0.0      # Debounce cooldown after firing

        # Last stable cursor output
        self.last_screen_x = screen_width // 2
        self.last_screen_y = screen_height // 2
        self.last_is_locked = False
        self.last_target_desc = None

    def update_screen_size(self, width: int, height: int):
        self.screen_width = width
        self.screen_height = height

    @staticmethod
    def _dist_3d(p1, p2) -> float:
        """Euclidean distance in normalized 3D landmark space."""
        dx = p1.x - p2.x
        dy = p1.y - p2.y
        dz = getattr(p1, "z", 0.0) - getattr(p2, "z", 0.0)
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def _dist_2d(p1, p2) -> float:
        """Euclidean distance in normalized 2D image plane (avoids noisy Z estimation)."""
        dx = p1.x - p2.x
        dy = p1.y - p2.y
        return math.hypot(dx, dy)

    def _get_hand_scale(self, landmarks) -> float:
        """Calculates hand scale reference: Wrist (0) to Middle MCP knuckle (9)."""
        scale = self._dist_2d(landmarks[0], landmarks[9])
        return max(0.01, scale)

    def is_super_gesture(self, landmarks) -> bool:
        """
        Detects the 'Super / OK' activation gesture:
        - Last three fingers (Middle, Ring, Pinky) are extended upright.
        - Thumb and Index tips are close/touching (forming the power ring).
        """
        scale = self._get_hand_scale(landmarks)

        # 1. Thumb tip (4) and Index tip (8) proximity
        thumb_index_dist = self._dist_2d(landmarks[4], landmarks[8]) / scale
        is_ring_formed = thumb_index_dist < 0.42

        # 2. Middle finger extended (Tip 12 above PIP 10)
        middle_up = landmarks[12].y < landmarks[10].y

        # 3. Ring finger extended (Tip 16 above PIP 14)
        ring_up = landmarks[16].y < landmarks[14].y

        # 4. Pinky finger extended (Tip 20 above PIP 18)
        pinky_up = landmarks[20].y < landmarks[18].y

        three_fingers_up = middle_up and ring_up and pinky_up
        return is_ring_formed and three_fingers_up

    def process(self, landmarks, timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Processes 21 MediaPipe hand landmarks and emits mouse actions.
        :param landmarks: Normalized landmark array from MediaPipe.
        :param timestamp: Monotonic timestamp.
        :return: Dict containing cursor coordinates, click actions, and system states.
        """
        if timestamp is None:
            timestamp = time.perf_counter()

        now = timestamp
        scale = self._get_hand_scale(landmarks)

        # Check 'Super' Gesture (Active / Standby Toggle)
        super_detected = self.is_super_gesture(landmarks)
        toggled_state = False

        if super_detected and now > self.super_cooldown_until:
            if self.super_candidate_start == 0.0:
                self.super_candidate_start = now
            elif (now - self.super_candidate_start) >= self.super_gesture_hold_time:
                self.is_active = not self.is_active
                self.super_cooldown_until = now + 1.2  # 1.2s cooldown
                self.super_candidate_start = 0.0
                toggled_state = True
                if self.on_state_change:
                    self.on_state_change(self.is_active)
        else:
            if not super_detected:
                self.super_candidate_start = 0.0

        # If system is in Standby mode, skip cursor movement and clicking
        if not self.is_active:
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

        # 1. Cursor Tracking via Index Fingertip (Landmark 8)
        index_tip = landmarks[8]

        # Camera is mirrored for natural AR interaction: mirror X coordinate
        norm_x = 1.0 - index_tip.x
        norm_y = index_tip.y

        # Map active zone bounding box to full screen
        mapped_x = (norm_x - self.box_xmin) / max(0.001, (self.box_xmax - self.box_xmin))
        mapped_y = (norm_y - self.box_ymin) / max(0.001, (self.box_ymax - self.box_ymin))

        clamped_x = max(0.0, min(1.0, mapped_x))
        clamped_y = max(0.0, min(1.0, mapped_y))

        raw_screen_x = clamped_x * self.screen_width
        raw_screen_y = clamped_y * self.screen_height

        # 1€ Filter smoothing with kinetic stillness deadband (clamps tremor)
        smooth_x, smooth_y = self.cursor_filter.filter(raw_screen_x, raw_screen_y, timestamp=now)
        velocity = self.cursor_filter.last_velocity

        # Record coordinate in history buffer (for pre-tap rollback)
        self.coord_history.append((now, int(smooth_x), int(smooth_y)))

        # 2. Tap Click Detection: Index Tip (8) to Middle Tip (12) in 2D
        middle_tip = landmarks[12]
        index_middle_dist = self._dist_2d(index_tip, middle_tip)
        tap_ratio = index_middle_dist / scale

        # 3. Apply Assistive Magnetic Target Snapping (when not dragging)
        is_locked = False
        target_desc = None
        if self.tap_state != "DRAG":
            snapped_x, snapped_y, is_locked, target_desc = self.target_lock.apply_magnetic_lock(
                smooth_x, smooth_y, velocity=velocity, timestamp=now
            )
        else:
            snapped_x, snapped_y = int(smooth_x), int(smooth_y)

        current_screen_x = snapped_x
        current_screen_y = snapped_y

        # If within double-click window of previous click and hand remains nearby (< 150px),
        # anchor cursor to the exact target to guarantee 100% reliable double-click registration.
        if (now - self.last_click_time) <= self.double_click_window:
            dx_prev = current_screen_x - self.last_click_pos[0]
            dy_prev = current_screen_y - self.last_click_pos[1]
            if math.hypot(dx_prev, dy_prev) <= 150.0:
                current_screen_x, current_screen_y = self.last_click_pos

        action = "MOVE"

        # 4. Tap State Machine with Pre-Tap Freezing & Double-Click Support
        if self.tap_state == "UP":
            if tap_ratio < self.tap_down_ratio:
                # Transition to TAP_DOWN: Lock position immediately!
                self.tap_state = "DOWN"
                self.tap_start_time = now

                # If this is a candidate for double click, lock to the exact first click location
                if (now - self.last_click_time) <= self.double_click_window:
                    dx_prev = current_screen_x - self.last_click_pos[0]
                    dy_prev = current_screen_y - self.last_click_pos[1]
                    if math.hypot(dx_prev, dy_prev) <= 150.0:
                        self.anchor_position = self.last_click_pos
                    else:
                        self.anchor_position = self._get_pre_tap_position(now, current_screen_x, current_screen_y)
                else:
                    # Roll back to the position right before finger started moving to tap
                    self.anchor_position = self._get_pre_tap_position(now, current_screen_x, current_screen_y)

                self.anchor_release_time = now + 0.15  # Hold anchor for at least 150ms
                action = "TAP_CONTACT"

        elif self.tap_state == "DOWN":
            contact_duration = now - self.tap_start_time

            # Check if held long enough to become DRAG (held >= 420 ms)
            if contact_duration >= self.drag_hold_duration:
                self.tap_state = "DRAG"
                action = "DRAG_START"
                self.anchor_position = None  # Free cursor to move with drag!
            elif tap_ratio > self.tap_up_ratio:
                # Released before drag duration -> Crisp Click!
                self.tap_state = "UP"
                self.anchor_release_time = now + 0.08  # Hold anchor briefly during release

                click_pos = self.anchor_position or (current_screen_x, current_screen_y)

                # Check if this qualifies as a DOUBLE CLICK
                if (now - self.last_click_time) <= self.double_click_window:
                    dx_prev = click_pos[0] - self.last_click_pos[0]
                    dy_prev = click_pos[1] - self.last_click_pos[1]
                    if math.hypot(dx_prev, dy_prev) <= 150.0:
                        action = "DOUBLE_CLICK"
                        self.last_click_time = 0.0  # Reset
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

        elif self.tap_state == "DRAG":
            if tap_ratio > self.tap_up_ratio:
                # Drag released
                self.tap_state = "UP"
                action = "DRAG_RELEASE"
                self.last_click_time = 0.0
            else:
                action = "DRAG_MOVE"

        # Apply Click-Anchor Lock: Keep position rock-solid during tap impact
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
        """Looks back ~70ms in coordinate history to get the position before tap deflection started."""
        target_time = now - 0.075
        for t_hist, hx, hy in reversed(self.coord_history):
            if t_hist <= target_time:
                return (hx, hy)
        if self.coord_history:
            return (self.coord_history[0][1], self.coord_history[0][2])
        return (default_x, default_y)
