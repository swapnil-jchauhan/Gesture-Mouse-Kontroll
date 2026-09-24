"""
One Euro Filter (1€ Filter) for Adaptive Jitter Smoothing.
Based on the CHI 2012 paper by Géry Casiez, Nicolas Roussel, and Daniel Vogel:
"1 € Filter: A Simple Speed-based Low-pass Filter for Noisy Input in Human-Computer Interaction"

Key characteristics:
- High jitter reduction at low speeds (standing still on icons/buttons).
- Near-zero latency / lag at high speeds (swiping, tracking rapid hand movements).
"""

import math
import time
from typing import Optional, Tuple


class LowPassFilter:
    """Standard first-order low-pass filter."""

    def __init__(self, alpha: float = 0.5):
        self._alpha = alpha
        self._y: Optional[float] = None
        self._s: Optional[float] = None

    def filter(self, value: float, alpha: Optional[float] = None) -> float:
        if alpha is not None:
            self._alpha = alpha

        if self._s is None:
            self._s = value
        else:
            self._s = self._alpha * value + (1.0 - self._alpha) * self._s
        return self._s

    def last_value(self) -> Optional[float]:
        return self._s

    def reset(self):
        self._y = None
        self._s = None


class OneEuroFilter:
    """
    Adaptive One Euro Filter for a single 1D scalar signal.
    """

    def __init__(
        self,
        freq: float = 60.0,
        min_cutoff: float = 0.8,
        beta: float = 0.015,
        d_cutoff: float = 1.0,
    ):
        """
        :param freq: Estimate of sampling frequency (Hz), dynamically adjusted if timestamps are provided.
        :param min_cutoff: Minimum cutoff frequency (Hz). Lower values give smoother standing-still tracking.
        :param beta: Speed coefficient. Higher values reduce lag during fast movements.
        :param d_cutoff: Cutoff frequency for derivative filtering (Hz).
        """
        self._freq = max(1.0, freq)
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff

        self._x_filter = LowPassFilter()
        self._dx_filter = LowPassFilter()
        self._last_time: Optional[float] = None

    def _alpha(self, cutoff: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te = 1.0 / self._freq
        return 1.0 / (1.0 + tau / te)

    def filter(self, x: float, timestamp: Optional[float] = None) -> float:
        if timestamp is None:
            timestamp = time.perf_counter()

        if self._last_time is not None and timestamp > self._last_time:
            dt = timestamp - self._last_time
            if dt > 1e-5:
                self._freq = 1.0 / dt
        self._last_time = timestamp

        prev_x = self._x_filter.last_value()
        if prev_x is None:
            dx = 0.0
        else:
            dx = (x - prev_x) * self._freq

        edx = self._dx_filter.filter(dx, self._alpha(self._d_cutoff))
        cutoff = self._min_cutoff + self._beta * abs(edx)
        return self._x_filter.filter(x, self._alpha(cutoff))

    def reset(self):
        self._x_filter.reset()
        self._dx_filter.reset()
        self._last_time = None


class Point2DOneEuroFilter:
    """
    Composite 1€ filter for 2D points (x, y) with kinetic deadband stabilization.
    Completely eliminates sub-pixel cursor vibration when hovering still over small icons.
    """

    def __init__(
        self,
        freq: float = 60.0,
        min_cutoff: float = 0.5,
        beta: float = 0.025,
        d_cutoff: float = 1.0,
        deadband_radius: float = 2.8,
    ):
        self.x_filter = OneEuroFilter(freq, min_cutoff, beta, d_cutoff)
        self.y_filter = OneEuroFilter(freq, min_cutoff, beta, d_cutoff)
        self.deadband_radius = deadband_radius

        self._last_out_x: Optional[float] = None
        self._last_out_y: Optional[float] = None
        self._last_time: Optional[float] = None
        self.last_velocity: float = 0.0

    def filter(self, x: float, y: float, timestamp: Optional[float] = None) -> Tuple[float, float]:
        if timestamp is None:
            timestamp = time.perf_counter()

        fx = self.x_filter.filter(x, timestamp)
        fy = self.y_filter.filter(y, timestamp)

        if self._last_out_x is None or self._last_out_y is None:
            self._last_out_x = fx
            self._last_out_y = fy
            self._last_time = timestamp
            self.last_velocity = 0.0
            return fx, fy

        dt = max(1e-4, timestamp - (self._last_time or timestamp))
        self._last_time = timestamp

        disp = math.hypot(fx - self._last_out_x, fy - self._last_out_y)
        self.last_velocity = disp / dt  # pixels per second

        # Pseudo-Haptic Stillness Deadband:
        # If displacement is within deadband_radius (< 2.8 px) and velocity is not an intentional flick (< 150 px/s),
        # keep the cursor perfectly pinned to eliminate micro-tremor.
        if disp < self.deadband_radius and self.last_velocity < 150.0:
            return self._last_out_x, self._last_out_y

        # Smooth transition when leaving deadband
        if disp < self.deadband_radius * 2.0:
            blend = (disp - self.deadband_radius) / self.deadband_radius
            out_x = self._last_out_x + (fx - self._last_out_x) * blend
            out_y = self._last_out_y + (fy - self._last_out_y) * blend
        else:
            out_x = fx
            out_y = fy

        self._last_out_x = out_x
        self._last_out_y = out_y
        return out_x, out_y

    def reset(self):
        self.x_filter.reset()
        self.y_filter.reset()
        self._last_out_x = None
        self._last_out_y = None
        self._last_time = None
        self.last_velocity = 0.0
