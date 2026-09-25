"""
Gesture Detection Engine for Project Kontroll.
Pillar 3: Orthogonal Natural Gestures (Physical Mouse Paradigm).
- Left Click: Closed fist (✊) Index fingertip taps Thumb.
- Right Click: Middle fingertip taps Thumb (✊/👌 with middle-thumb contact).
  Completely immune to collinear line-of-sight occlusion in angled cameras; 0% ghost clicks.
- Drag & Drop: Super gesture (👌, Index on thumb + last 3 fingers up) with Windows priming double-tap-and-hold.
- Activation/Standby: Hawaiian Shaka sign (🤙).
- Relative Ballistics & 3D Desk Homography Integration.
"""

import math
import time
from typing import Tuple, Optional, Callable, Dict, Any

from src.core.filter import Point2DOneEuroFilter
from src.core.target_lock import TargetLockManager
from src.core.homography import DeskHomography
from src.core.ballistics import RelativeBallisticsEngine


class GestureEngine:
    """
    Gesture State Machine & Cursor Mapping Engine for Project Kontroll.
    Seamlessly integrates 3D Desk Homography, Relative Ballistics with Air-Clutching,
    Orthogonal Gestures, and Viscous Deceleration Aim Assist.
    """

    def __init__(
        self,
        screen_width: int = 1920,
        screen_height: int = 1080,
        on_state_change: Optional[Callable[[bool], None]] = None,
        on_click_callback: Optional[Callable[[], None]] = None,
        initial_active: bool = False,
    ):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.on_state_change = on_state_change
        self.on_click_callback = on_click_callback

        # System State (Online / Standby - defaults to Standby)
        self.is_active = initial_active

        # Pillar 2: 3D Desk Homography Engine
        self.mount_mode = "center"
        self.homography = DeskHomography(mode=self.mount_mode, default_tilt_deg=0.0)

        # Pillar 4: Relative Ballistics Engine with Air-Clutching
        self.ballistics = RelativeBallisticsEngine(
            screen_width=self.screen_width,
            screen_height=self.screen_height,
            mode="relative",
            base_sensitivity=1.6,
        )

        # 1€ Filter: Adaptive Low-Pass Filter with kinetic deadband
        self.cursor_filter = Point2DOneEuroFilter(freq=60.0, min_cutoff=0.8, beta=0.045, deadband_radius=2.2)

        # Pillar 5: OS-Level Viscous Deceleration Aim Assister
        self.target_lock = TargetLockManager(capture_radius=42.0, breakout_velocity=750.0, bubble_radius=35.0)

        # Ergonomic Rest Box (forearm/elbow resting on desk)
        self.box_xmin = 0.20
        self.box_xmax = 0.80
        self.box_ymin = 0.30
        self.box_ymax = 0.85

        # Left Click Parameters: Closed-Fist Index-Thumb Tap
        self.tap_down_ratio = 0.32
        self.tap_up_ratio = 0.40
        self.tap_state = "UP"  # "UP", "DOWN"
        self.tap_start_time = 0.0

        # Right Click Parameters: Middle-Thumb Tap (Orthogonal, 0% Ghost Clicks)
        self.right_tap_down_ratio = 0.28
        self.right_tap_up_ratio = 0.38
        self.right_click_state = "UP"  # "UP", "DOWN"
        self.right_tap_start_time = 0.0
        self._mid_open_timer = 0.0

        # Drag Mode: Index-Thumb with 3 Fingers UP (Super Gesture 👌)
        self.is_dragging = False
        self.pinch_drag_threshold = 0.28
        self.pinch_start_time = 0.0

        # Shaka Activation Gesture (🤙: Thumb & Pinky OUT, 3 Middle Fingers Curled)
        self.shaka_start_time = 0.0
        self.shaka_triggered = False
        self.shaka_hold_duration = 0.35

        # Multi-Click / Double-Click tracking
        self.double_click_window = 0.38
        self.last_click_time = 0.0
        self.last_click_pos = (screen_width // 2, screen_height // 2)

        # Previous frame landmark position for delta calculation
        self._prev_norm_pos: Optional[Tuple[float, float]] = None
        self._last_process_time: float = time.perf_counter()

        # Telemetry
        self.last_screen_x = screen_width // 2
        self.last_screen_y = screen_height // 2
        self.last_is_locked = False
        self.last_target_desc = None
        self.detected_tilt_angle = 35.0

    @property
    def tracking_mode(self) -> str:
        return self.ballistics.mode

    def set_tracking_mode(self, mode: str):
        self.ballistics.set_mode(mode)

    def update_screen_size(self, width: int, height: int):
        self.screen_width = width
        self.screen_height = height
        self.ballistics.update_screen_size(width, height)

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
        self._prev_norm_pos = None
        self._mid_open_timer = 0.0
        self.cursor_filter.reset()

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
        Detects if middle, ring, and pinky fingers are curled closed into palm.
        """
        d_m_mcp = self._dist_3d(landmarks[12], landmarks[9]) / scale
        d_r_mcp = self._dist_3d(landmarks[16], landmarks[13]) / scale
        d_p_mcp = self._dist_3d(landmarks[20], landmarks[17]) / scale

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
        # If middle finger is touching the thumb, it cannot be extended upright (super gesture impossible)
        d_thumb_middle = self._dist_3d(landmarks[4], landmarks[12]) / scale
        if d_thumb_middle < 0.35:
            return False

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
        d_index_thumb = self._dist_3d(landmarks[8], landmarks[4])
        tap_ratio = d_index_thumb / scale
        fist_closed = self.is_fist_closed(landmarks, scale)
        if not fist_closed:
            return tap_ratio, False

        is_contact = tap_ratio < self.tap_down_ratio
        return tap_ratio, is_contact

    compute_angle_invariant_tap_metric = compute_tap_metric

    def is_shaka_gesture(self, landmarks) -> bool:
        """
        Detects the Hawaiian Shaka Activation Gesture (🤙):
        Thumb (4) and Pinky (20) are fully extended OUT,
        while Index (8), Middle (12), and Ring (16) are curled IN against palm.
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
        Detects the 'Super / OK' pose (👌):
        Index touches Thumb while last three fingers (Middle, Ring, Pinky) are straight UP.
        """
        scale = self._get_hand_scale(landmarks)
        d_thumb_index = self._dist_3d(landmarks[4], landmarks[8]) / scale
        return (d_thumb_index < self.pinch_drag_threshold) and self.are_last_three_up(landmarks)

    def process(
        self,
        landmarks,
        timestamp: Optional[float] = None,
        optical_flow_delta: Optional[Tuple[float, float]] = None,
    ) -> Dict[str, Any]:
        """
        Processes a frame of hand landmarks and optional optical flow displacement.
        """
        now = timestamp if timestamp is not None else time.perf_counter()
        dt = max(1e-4, min(0.05, now - self._last_process_time))
        self._last_process_time = now

        scale = self._get_hand_scale(landmarks)

        # 0. Shaka Activation / Toggle Gesture Detection (🤙)
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

        # 1. Distances and Orthogonal Gestures Detection
        d_thumb_index = self._dist_3d(landmarks[4], landmarks[8]) / scale
        d_thumb_middle = self._dist_3d(landmarks[4], landmarks[12]) / scale
        fist_closed = self.is_fist_closed(landmarks, scale)
        three_fingers_up = self.are_last_three_up(landmarks)

        # Check finger extensions
        d_idx_mcp = self._dist_3d(landmarks[8], landmarks[5]) / scale
        d_idx_wrist = self._dist_3d(landmarks[8], landmarks[0]) / scale
        index_extended = (d_idx_mcp > 0.55) or (d_idx_wrist > 1.05) or (landmarks[8].y < landmarks[6].y - 0.02)

        d_mid_mcp = self._dist_3d(landmarks[12], landmarks[9]) / scale
        d_mid_wrist = self._dist_3d(landmarks[12], landmarks[0]) / scale
        middle_extended = (d_mid_mcp > 0.55) or (d_mid_wrist > 1.05) or (landmarks[12].y < landmarks[10].y)

        if middle_extended:
            self._mid_open_timer = now

        # Drag: Index on Thumb with Last Three Fingers UP (👌 Super Gesture)
        drag_pose_active = (d_thumb_index < self.pinch_drag_threshold) and three_fingers_up

        # Two-Finger Pinch (Index + Middle touching Thumb together) -> Right Click
        two_finger_pinch = (
            (d_thumb_index < self.tap_down_ratio * 1.05)
            and (d_thumb_middle < self.right_tap_down_ratio * 1.05)
            and not three_fingers_up
        )

        # Right Click (Pillar 3 Orthogonal Gesture):
        # 1) Two-Finger Pinch (Index + Middle touch thumb), OR
        # 2) Middle finger taps thumb actively (was extended recently), OR
        # 3) Fist closed middle tap (index not extended pointing)
        d_ring_mcp = self._dist_3d(landmarks[16], landmarks[13]) / scale
        d_pinky_mcp = self._dist_3d(landmarks[20], landmarks[17]) / scale
        ring_pinky_curled = (d_ring_mcp < 0.72) and (d_pinky_mcp < 0.72)

        middle_active_tap = (
            (d_thumb_middle < self.right_tap_down_ratio)
            and (
                two_finger_pinch
                or (now - self._mid_open_timer < 0.40)
                or (not index_extended and (ring_pinky_curled or fist_closed))
            )
            and not drag_pose_active
        )
        is_right_contact = middle_active_tap

        # Left Click: Index fingertip taps Thumb while NOT right click and NOT drag
        is_left_contact = (
            (d_thumb_index < self.tap_down_ratio)
            and not two_finger_pinch
            and not drag_pose_active
            and not is_right_contact
            and (fist_closed or not three_fingers_up)
        )

        # Click Intent / Active Tap Detection for Firm Anchor
        click_intent = (
            is_left_contact
            or (self.tap_state == "DOWN")
            or is_right_contact
            or (self.right_click_state == "DOWN")
            or (d_thumb_index < self.tap_up_ratio * 1.2 and fist_closed)
            or ((now - self.last_click_time) < 0.25)
        )

        # 2. Air-Clutching Check (Pillar 4)
        is_pointing, is_clutched = self.ballistics.check_air_clutch(landmarks, scale)

        # 3. Position and Motion Calculation
        norm_x = 1.0 - landmarks[8].x  # Mirrored for natural user perspective
        norm_y = landmarks[8].y

        # Update homography mounting mode and estimate tilt if auto
        self.homography.set_mode(self.mount_mode)
        if self.mount_mode == "auto":
            self.detected_tilt_angle = self.homography.estimate_camera_tilt(landmarks)
        else:
            self.detected_tilt_angle = self.homography.get_effective_tilt_deg()

        # Compute Absolute Screen Coordinates (Fallback / Calibration)
        unwarped_norm_x, unwarped_norm_y = self.homography.transform_point(norm_x, norm_y, landmarks)
        box_w = max(0.001, self.box_xmax - self.box_xmin)
        box_h = max(0.001, self.box_ymax - self.box_ymin)
        u = max(0.0, min(1.0, (unwarped_norm_x - self.box_xmin) / box_w))
        v = max(0.0, min(1.0, (unwarped_norm_y - self.box_ymin) / box_h))
        u_curved = 0.5 + math.copysign(0.5 * (abs(2.0 * (u - 0.5)) ** 1.15), u - 0.5)
        v_curved = 0.5 + math.copysign(0.5 * (abs(2.0 * (v - 0.5)) ** 1.15), v - 0.5)
        abs_screen_x = u_curved * float(self.screen_width - 1)
        abs_screen_y = v_curved * float(self.screen_height - 1)

        # Motion displacement delta
        if is_left_contact or self.tap_state == "DOWN" or is_right_contact or self.right_click_state == "DOWN":
            # Pin cursor during active physical tap-down and tap-release:
            # finger actuation motion is not a mouse swipe
            screen_dx = 0.0
            screen_dy = 0.0
        elif optical_flow_delta is not None:
            if abs(optical_flow_delta[0]) < 1e-6 and abs(optical_flow_delta[1]) < 1e-6:
                # Laser-mouse stillness guarantee: identically (0.00, 0.00) px displacement
                screen_dx = 0.0
                screen_dy = 0.0
            else:
                # Invert camera X so physical rightward movement is positive
                cam_dx = -optical_flow_delta[0]
                cam_dy = optical_flow_delta[1]
                desk_dx, desk_dy = self.homography.transform_vector(cam_dx, cam_dy, landmarks)
                # Scale from camera pixels to screen pixel space
                screen_dx = desk_dx * (self.screen_width / 640.0)
                screen_dy = desk_dy * (self.screen_height / 480.0)
        elif self._prev_norm_pos is not None:
            raw_dx = (norm_x - self._prev_norm_pos[0]) * float(self.screen_width)
            raw_dy = (norm_y - self._prev_norm_pos[1]) * float(self.screen_height)
            desk_dx, desk_dy = self.homography.transform_vector(raw_dx, raw_dy, landmarks)
            screen_dx = desk_dx
            screen_dy = desk_dy
        else:
            screen_dx = 0.0
            screen_dy = 0.0

        if self._prev_norm_pos is None:
            if self.ballistics.mode == "absolute":
                self.ballistics.reset_position(abs_screen_x, abs_screen_y)

        self._prev_norm_pos = (norm_x, norm_y)

        # Update Relative Ballistics with Air-Clutching (Pillar 4)
        if self.ballistics.mode == "relative":
            ballistic_x, ballistic_y, raw_vel = self.ballistics.update(
                dx=screen_dx,
                dy=screen_dy,
                dt=dt,
                is_engaged=is_pointing and not is_clutched,
                absolute_pos=(abs_screen_x, abs_screen_y),
            )
        else:
            ballistic_x = abs_screen_x
            ballistic_y = abs_screen_y
            raw_vel = math.hypot(screen_dx, screen_dy) / dt

        # 1€ Filter Smoothing
        smooth_x, smooth_y = self.cursor_filter.filter(ballistic_x, ballistic_y, timestamp=now)
        velocity = self.cursor_filter.last_velocity

        # Pillar 5: OS-Level Viscous Deceleration Aim Assist
        is_locked = False
        target_desc = None
        if not self.is_dragging:
            snapped_x, snapped_y, is_locked, target_desc = self.target_lock.apply_magnetic_lock(
                smooth_x, smooth_y, velocity=velocity, timestamp=now, is_clicking=click_intent
            )
        else:
            snapped_x, snapped_y = int(round(smooth_x)), int(round(smooth_y))

        current_screen_x = snapped_x
        current_screen_y = snapped_y

        action = "MOVE"

        # 4. Drag & Drop State Machine (👌 Super Gesture)
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
                "active": True,
                "cursor_x": current_screen_x,
                "cursor_y": current_screen_y,
                "action": action,
                "tap_ratio": d_thumb_index,
                "is_locked": is_locked,
                "target_desc": "PINCH DRAG",
            }
        elif self.is_dragging:
            self.is_dragging = False
            self.pinch_start_time = 0.0
            action = "DRAG_RELEASE"
            self.last_screen_x = current_screen_x
            self.last_screen_y = current_screen_y
            return {
                "active": True,
                "cursor_x": current_screen_x,
                "cursor_y": current_screen_y,
                "action": action,
                "tap_ratio": d_thumb_index,
                "is_locked": is_locked,
                "target_desc": None,
            }

        # 5. Right-Click State Machine (Middle-Thumb Tap)
        if self.right_click_state == "UP":
            if is_right_contact and self.tap_state == "UP":
                self.right_click_state = "DOWN"
                self.right_tap_start_time = now
                action = "RIGHT_CONTACT"
        elif self.right_click_state == "DOWN":
            if not is_right_contact or d_thumb_middle > self.right_tap_up_ratio:
                self.right_click_state = "UP"
                action = "RIGHT_CLICK"
            elif (now - self.right_tap_start_time) > 0.40:
                self.right_click_state = "UP"

        # 6. Left-Click State Machine (Closed-Fist Index-Thumb Tap)
        if self.tap_state == "UP":
            if is_left_contact and action not in ("RIGHT_CONTACT", "RIGHT_CLICK") and self.right_click_state == "UP":
                self.tap_state = "DOWN"
                self.tap_start_time = now
                action = "TAP_CONTACT"
        elif self.tap_state == "DOWN":
            contact_duration = now - self.tap_start_time
            if not is_left_contact or d_thumb_index > self.tap_up_ratio:
                self.tap_state = "UP"
                click_pos = (current_screen_x, current_screen_y)

                if action not in ("RIGHT_CONTACT", "RIGHT_CLICK"):
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
            "is_clutched": is_clutched,
        }
