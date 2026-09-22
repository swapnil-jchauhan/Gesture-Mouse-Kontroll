"""
Unit & Integration Test Suite for Project Kontroll.
Verifies 1€ filtering, gesture math, tap detection, click-anchor lock, and mouse simulation.
"""

import unittest
import time
from types import SimpleNamespace

from src.core.filter import OneEuroFilter, Point2DOneEuroFilter
from src.core.gestures import GestureEngine
from src.core.input_simulator import MouseSimulator
from src.service.autostart import is_autostart_enabled, get_launch_command


class TestOneEuroFilter(unittest.TestCase):
    def test_low_velocity_jitter_suppression(self):
        """Simulates noisy sensor values around a fixed point to test smoothing."""
        filt = OneEuroFilter(freq=60.0, min_cutoff=0.5, beta=0.01)
        base = 500.0
        outputs = []
        # Add jitter: +/- 3 pixels around 500
        t = 0.0
        for i in range(30):
            jitter = (1 if i % 2 == 0 else -1) * 3.0
            val = base + jitter
            out = filt.filter(val, timestamp=t)
            outputs.append(out)
            t += 1.0 / 60.0

        # The filtered output variance must be significantly less than raw input jitter
        raw_variance = 3.0
        filtered_deviations = [abs(x - base) for x in outputs[10:]]
        max_filtered_dev = max(filtered_deviations)
        self.assertLess(max_filtered_dev, raw_variance * 0.4,
                        f"Expected filtered deviation < 1.2, got {max_filtered_dev}")

    def test_high_velocity_zero_lag(self):
        """Simulates a rapid swipe to verify the filter adapts without dragging behind."""
        filt = OneEuroFilter(freq=60.0, min_cutoff=0.8, beta=0.05)
        # Fast movement from 0 to 1000 over 10 frames
        t = 0.0
        for i in range(10):
            val = i * 100.0
            out = filt.filter(val, timestamp=t)
            t += 1.0 / 60.0

        # At high speed, the output must closely track the target (within 15%)
        self.assertGreater(out, 750.0)


class TestGestureEngine(unittest.TestCase):
    def _create_mock_landmarks(self, index_tip_y=0.4, middle_tip_y=0.4, tap_close=False, super_pose=False):
        """Helper to create 21 mocked 3D landmark points."""
        lm = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        # Wrist = 0
        lm[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        # Middle MCP = 9 (scale = dist(0, 9) = 0.8 - 0.5 = 0.3)
        lm[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)

        # Index tip (8), PIP (6)
        lm[6] = SimpleNamespace(x=0.38, y=0.55, z=0.0)
        lm[8] = SimpleNamespace(x=0.38, y=index_tip_y, z=0.0)

        # Middle tip (12), PIP (10)
        lm[10] = SimpleNamespace(x=0.52, y=0.52, z=0.0)
        lm[12] = SimpleNamespace(x=0.52, y=middle_tip_y, z=0.0)

        if tap_close:
            # Move index tip to touch middle tip
            lm[8] = SimpleNamespace(x=0.518, y=middle_tip_y, z=0.0)

        if super_pose:
            # Thumb (4) and Index (8) close together
            lm[4] = SimpleNamespace(x=0.49, y=0.55, z=0.0)
            lm[8] = SimpleNamespace(x=0.50, y=0.55, z=0.0)
            # Middle (12), Ring (16), Pinky (20) extended up (y tip < y pip)
            lm[10] = SimpleNamespace(x=0.52, y=0.50, z=0.0)
            lm[12] = SimpleNamespace(x=0.52, y=0.30, z=0.0) # Up

            lm[14] = SimpleNamespace(x=0.55, y=0.52, z=0.0)
            lm[16] = SimpleNamespace(x=0.55, y=0.32, z=0.0) # Up

            lm[18] = SimpleNamespace(x=0.58, y=0.55, z=0.0)
            lm[20] = SimpleNamespace(x=0.58, y=0.35, z=0.0) # Up

        return lm

    def test_tap_click_detection(self):
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        # 1. Normal hand with index and middle separated
        lm_open = self._create_mock_landmarks(index_tip_y=0.4, middle_tip_y=0.4, tap_close=False)
        res1 = engine.process(lm_open, timestamp=1.0)
        self.assertEqual(res1["action"], "MOVE")

        # 2. Tap index on middle
        lm_tap = self._create_mock_landmarks(index_tip_y=0.4, middle_tip_y=0.4, tap_close=True)
        res2 = engine.process(lm_tap, timestamp=1.05)
        self.assertEqual(res2["action"], "TAP_CONTACT")

        # 3. Release tap quickly (< 250ms) -> Must trigger "CLICK"
        res3 = engine.process(lm_open, timestamp=1.15)
        self.assertEqual(res3["action"], "CLICK")

    def test_click_anchor_lock(self):
        """Verifies that coordinates are anchored during tap contact to eliminate aim drift."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(index_tip_y=0.4, middle_tip_y=0.4, tap_close=False)
        r_move = engine.process(lm_open, timestamp=1.0)
        anchor_x, anchor_y = r_move["cursor_x"], r_move["cursor_y"]

        # Tap occurs
        lm_tap = self._create_mock_landmarks(index_tip_y=0.4, middle_tip_y=0.4, tap_close=True)
        r_tap = engine.process(lm_tap, timestamp=1.05)

        # Output cursor position during tap MUST match the locked anchor position
        self.assertEqual(r_tap["cursor_x"], anchor_x)
        self.assertEqual(r_tap["cursor_y"], anchor_y)

    def test_super_gesture_detection(self):
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_super = self._create_mock_landmarks(super_pose=True)
        is_detected = engine.is_super_gesture(lm_super)
        self.assertTrue(is_detected, "Super gesture should be detected when last 3 fingers are upright.")


class TestInputAndAutostart(unittest.TestCase):
    def test_mouse_simulator_bounds(self):
        mouse = MouseSimulator()
        self.assertGreater(mouse.screen_width, 0)
        self.assertGreater(mouse.screen_height, 0)

    def test_autostart_command_string(self):
        cmd = get_launch_command()
        self.assertIn("main.py", cmd)


if __name__ == "__main__":
    unittest.main()
