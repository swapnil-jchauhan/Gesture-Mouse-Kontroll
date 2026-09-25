"""
Relative Ballistics with Frictionless Air-Clutching for Project Kontroll.
Pillar 4: Relative coordinate integration with Windows-tuned dynamic S-curve ballistics
and biomechanical air-clutching. Pointing pose engages cursor movement; resting or relaxed
flat hand disengages (clutches) cursor for effortless repositioning without arm fatigue.
"""

import math
import time
from typing import Optional, Tuple, Any


class RelativeBallisticsEngine:
    """
    Relative Coordinate Integration and Dynamic S-Curve Ballistics Engine.
    Emulates a physical high-DPI laser mouse in air with biomechanical air-clutching.
    """

    def __init__(
        self,
        screen_width: int = 1920,
        screen_height: int = 1080,
        mode: str = "relative",  # 'relative' or 'absolute'
        base_sensitivity: float = 1.0,
    ):
        self.screen_width = max(1, screen_width)
        self.screen_height = max(1, screen_height)
        self.mode = mode
        self.base_sensitivity = base_sensitivity

        # Current virtual cursor coordinates
        self.cursor_x = float(self.screen_width // 2)
        self.cursor_y = float(self.screen_height // 2)

        # Dynamic velocity tracking
        self.last_velocity: float = 0.0
        self.last_update_time: float = time.perf_counter()

        # Air-Clutch state
        self.is_engaged: bool = True
        self.is_clutched: bool = False

    def update_screen_size(self, width: int, height: int):
        self.screen_width = max(1, width)
        self.screen_height = max(1, height)

    def set_mode(self, mode: str):
        """Toggle between 'relative' and 'absolute' tracking."""
        if mode in ("relative", "absolute"):
            self.mode = mode

    def reset_position(self, x: Optional[float] = None, y: Optional[float] = None):
        """Resets virtual cursor position."""
        self.cursor_x = float(x if x is not None else self.screen_width // 2)
        self.cursor_y = float(y if y is not None else self.screen_height // 2)
        self.last_velocity = 0.0

    @staticmethod
    def _dist_3d(p1, p2) -> float:
        dx = p1.x - p2.x
        dy = p1.y - p2.y
        dz = getattr(p1, "z", 0.0) - getattr(p2, "z", 0.0)
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def check_air_clutch(self, landmarks, scale: float) -> Tuple[bool, bool]:
        """
        Determines if the hand pose engages cursor tracking or clutches (disengages).
        :return: (is_pointing, is_clutched)
        - Pointing Pose: Index extended, middle/ring/pinky curled or resting -> ENGAGED.
        - Clutched Pose: Relaxed flat hand (all 5 fingers open), or index curled -> CLUTCHED.
        """
        if landmarks is None or len(landmarks) < 21:
            return False, True

        # Index extension check: tip (8) to MCP (5)
        d_idx_mcp = self._dist_3d(landmarks[8], landmarks[5]) / scale
        d_idx_wrist = self._dist_3d(landmarks[8], landmarks[0]) / scale
        index_extended = (d_idx_mcp > 0.52) or (d_idx_wrist > 1.05) or (landmarks[8].y < landmarks[6].y + 0.02)

        # Middle, Ring, Pinky extensions
        d_mid_mcp = self._dist_3d(landmarks[12], landmarks[9]) / scale
        d_ring_mcp = self._dist_3d(landmarks[16], landmarks[13]) / scale
        d_pinky_mcp = self._dist_3d(landmarks[20], landmarks[17]) / scale

        mid_open = (d_mid_mcp > 0.56) and (landmarks[12].y < landmarks[10].y)
        ring_open = (d_ring_mcp > 0.56) and (landmarks[16].y < landmarks[14].y)
        pinky_open = (d_pinky_mcp > 0.52) and (landmarks[20].y < landmarks[18].y)

        # Relaxed flat open hand: all fingers extended flat -> CLUTCHED (rest / reposition)
        all_fingers_open = index_extended and mid_open and ring_open and pinky_open

        # Index curled: not pointing -> CLUTCHED
        if not index_extended:
            self.is_engaged = False
            self.is_clutched = True
            return False, True

        if all_fingers_open:
            self.is_engaged = False
            self.is_clutched = True
            return False, True

        # Standard pointing pose: Index is extended, last three fingers curled/neutral
        self.is_engaged = True
        self.is_clutched = False
        return True, False

    def compute_ballistic_gain(self, velocity: float) -> float:
        """
        Dynamic S-Curve Pointer Acceleration Profile:
        - Low speeds (< 120 px/s): 0.85x sub-linear gear for pixel-perfect targeting on 10px icons.
        - Medium speeds (120 - 600 px/s): 1.0x - 2.5x linear cruising gear.
        - High speeds (> 600 px/s): Exponential boost up to 5.5x for dual-monitor flick with 1-inch wrist motion.
        """
        if velocity < 120.0:
            return 0.85 * self.base_sensitivity
        elif velocity < 600.0:
            # Cubic smoothstep S-curve
            t = (velocity - 120.0) / 480.0
            smooth_t = t * t * (3.0 - 2.0 * t)
            return (0.85 + (2.5 - 0.85) * smooth_t) * self.base_sensitivity
        else:
            # Exponential wrist flick boost
            excess = min(1500.0, velocity - 600.0) / 1500.0
            boost = 2.5 + 3.0 * (excess ** 1.25)
            return boost * self.base_sensitivity

    def update(
        self,
        dx: float,
        dy: float,
        dt: float,
        is_engaged: bool = True,
        absolute_pos: Optional[Tuple[float, float]] = None,
    ) -> Tuple[float, float, float]:
        """
        Updates cursor position based on relative displacement and dynamic ballistics.
        :param dx: Un-tilted horizontal displacement.
        :param dy: Un-tilted vertical displacement.
        :param dt: Delta time in seconds.
        :param is_engaged: Whether air-clutch is engaged.
        :param absolute_pos: Optional fallback absolute screen coordinates if in absolute mode.
        :return: (cursor_x, cursor_y, velocity)
        """
        safe_dt = max(1e-4, dt)

        # If in absolute mode and absolute coordinates provided:
        if self.mode == "absolute" and absolute_pos is not None:
            ax, ay = absolute_pos
            disp = math.hypot(ax - self.cursor_x, ay - self.cursor_y)
            self.last_velocity = disp / safe_dt
            self.cursor_x = max(0.0, min(float(self.screen_width - 1), ax))
            self.cursor_y = max(0.0, min(float(self.screen_height - 1), ay))
            return self.cursor_x, self.cursor_y, self.last_velocity

        # Air-Clutching Check: If disengaged/clutched, ignore displacement completely!
        if not is_engaged:
            self.last_velocity = 0.0
            return self.cursor_x, self.cursor_y, 0.0

        # Calculate instantaneous raw input speed
        raw_dist = math.hypot(dx, dy)
        raw_velocity = raw_dist / safe_dt

        # Compute dynamic S-curve ballistics gain
        gain = self.compute_ballistic_gain(raw_velocity)

        # Integrate relative motion: x_t = x_{t-1} + dx * Curve(v)
        step_x = dx * gain
        step_y = dy * gain

        new_x = self.cursor_x + step_x
        new_y = self.cursor_y + step_y

        # Clamp to physical desktop boundaries
        self.cursor_x = max(0.0, min(float(self.screen_width - 1), new_x))
        self.cursor_y = max(0.0, min(float(self.screen_height - 1), new_y))

        actual_disp = math.hypot(step_x, step_y)
        self.last_velocity = actual_disp / safe_dt

        return self.cursor_x, self.cursor_y, self.last_velocity
