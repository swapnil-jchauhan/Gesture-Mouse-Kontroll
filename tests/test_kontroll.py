"""
Unit & Integration Test Suite for Project Kontroll.
Verifies:
1. 1€ filtering & kinetic deadband stillness jitter suppression
2. Rapid velocity tracking response
3. Instantaneous Single Click
4. Rapid Double Click detection & coordinate lock
5. Intentional Drag & Select state machine
6. Pre-Tap Anchor Lock deflection prevention
7. Magnetic Target Snapper & Breakout velocity
8. Super Activation Gesture
9. Hardware mouse simulator bounds & autostart registry
"""

import unittest
import time
from types import SimpleNamespace

from src.core.filter import OneEuroFilter, Point2DOneEuroFilter
from src.core.gestures import GestureEngine
from src.core.target_lock import TargetLockManager, ROLE_SYSTEM_PUSHBUTTON
from src.core.input_simulator import MouseSimulator
from src.service.autostart import is_autostart_enabled, get_launch_command


class TestOneEuroFilter(unittest.TestCase):
    def test_low_velocity_jitter_suppression(self):
        """Simulates noisy sensor values around a fixed point to test smoothing."""
        filt = OneEuroFilter(freq=60.0, min_cutoff=0.5, beta=0.01)
        base = 500.0
        outputs = []
        t = 0.0
        for i in range(30):
            jitter = (1 if i % 2 == 0 else -1) * 3.0
            val = base + jitter
            out = filt.filter(val, timestamp=t)
            outputs.append(out)
            t += 1.0 / 60.0

        raw_variance = 3.0
        filtered_deviations = [abs(x - base) for x in outputs[10:]]
        max_filtered_dev = max(filtered_deviations)
        self.assertLess(max_filtered_dev, raw_variance * 0.4,
                        f"Expected filtered deviation < 1.2, got {max_filtered_dev}")

    def test_kinetic_deadband_zero_jitter(self):
        """Verifies that Point2DOneEuroFilter completely clamps micro-jitter to 0 px when hovering still."""
        filt = Point2DOneEuroFilter(freq=60.0, min_cutoff=0.5, deadband_radius=2.8)
        base_x, base_y = 500.0, 500.0
        # Initialize filter with stable base
        filt.filter(base_x, base_y, timestamp=0.0)

        # Micro-tremors of 1.5 pixels (typical hand tremor)
        t = 0.05
        locked_points = []
        for i in range(10):
            t += 1.0 / 60.0
            wobble_x = base_x + (1.2 if i % 2 == 0 else -1.2)
            wobble_y = base_y + (-0.9 if i % 2 == 0 else 0.9)
            ox, oy = filt.filter(wobble_x, wobble_y, timestamp=t)
            locked_points.append((ox, oy))

        # Output points must remain clamped within deadband radius of initial base
        for ox, oy in locked_points:
            self.assertAlmostEqual(ox, base_x, delta=0.5, msg="Deadband must eliminate micro-tremor")
            self.assertAlmostEqual(oy, base_y, delta=0.5, msg="Deadband must eliminate micro-tremor")

    def test_high_velocity_zero_lag(self):
        """Simulates a rapid swipe to verify the filter adapts without dragging behind."""
        filt = OneEuroFilter(freq=60.0, min_cutoff=0.8, beta=0.05)
        t = 0.0
        for i in range(10):
            val = i * 100.0
            out = filt.filter(val, timestamp=t)
            t += 1.0 / 60.0

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
            # Move index tip to touch middle tip (ratio < 0.25)
            lm[8] = SimpleNamespace(x=0.518, y=middle_tip_y, z=0.0)

        if super_pose:
            # Thumb (4) and Index (8) close together
            lm[4] = SimpleNamespace(x=0.49, y=0.55, z=0.0)
            lm[8] = SimpleNamespace(x=0.50, y=0.55, z=0.0)
            # Middle (12), Ring (16), Pinky (20) extended up (y tip < y pip)
            lm[10] = SimpleNamespace(x=0.52, y=0.50, z=0.0)
            lm[12] = SimpleNamespace(x=0.52, y=0.30, z=0.0)

            lm[14] = SimpleNamespace(x=0.55, y=0.52, z=0.0)
            lm[16] = SimpleNamespace(x=0.55, y=0.32, z=0.0)

            lm[18] = SimpleNamespace(x=0.58, y=0.55, z=0.0)
            lm[20] = SimpleNamespace(x=0.58, y=0.35, z=0.0)

        return lm

    def test_single_click_detection(self):
        """Verifies quick tap and release (< 380 ms) emits crisp CLICK."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(tap_close=False)
        res1 = engine.process(lm_open, timestamp=1.0)
        self.assertEqual(res1["action"], "MOVE")

        # Contact
        lm_tap = self._create_mock_landmarks(tap_close=True)
        res2 = engine.process(lm_tap, timestamp=1.05)
        self.assertEqual(res2["action"], "TAP_CONTACT")

        # Release at 1.20s (150 ms contact) -> Single Click!
        res3 = engine.process(lm_open, timestamp=1.20)
        self.assertEqual(res3["action"], "CLICK")

    def test_double_click_detection(self):
        """Verifies two consecutive quick taps trigger DOUBLE_CLICK at the same anchor coordinate."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(tap_close=False)
        lm_tap = self._create_mock_landmarks(tap_close=True)

        # Tap 1
        engine.process(lm_open, timestamp=1.0)
        engine.process(lm_tap, timestamp=1.05)
        r_click1 = engine.process(lm_open, timestamp=1.18)
        self.assertEqual(r_click1["action"], "CLICK")
        pos1 = (r_click1["cursor_x"], r_click1["cursor_y"])

        # Tap 2 (120ms later)
        engine.process(lm_tap, timestamp=1.30)
        r_click2 = engine.process(lm_open, timestamp=1.42)
        self.assertEqual(r_click2["action"], "DOUBLE_CLICK")
        pos2 = (r_click2["cursor_x"], r_click2["cursor_y"])

        # Second click must hit identical coordinate as first click
        self.assertEqual(pos1, pos2, "Double click must hit exact same anchor coordinate")

    def test_intentional_drag_and_release(self):
        """Verifies holding fingers together for >= 420 ms enters DRAG mode."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(tap_close=False)
        lm_tap = self._create_mock_landmarks(tap_close=True)

        # Contact begins
        engine.process(lm_open, timestamp=1.0)
        r_down = engine.process(lm_tap, timestamp=1.05)
        self.assertEqual(r_down["action"], "TAP_CONTACT")

        # After 450 ms of continuous contact -> DRAG_START
        r_drag = engine.process(lm_tap, timestamp=1.52)
        self.assertEqual(r_drag["action"], "DRAG_START")
        self.assertEqual(engine.tap_state, "DRAG")

        # Moving while in drag
        r_drag_move = engine.process(lm_tap, timestamp=1.60)
        self.assertEqual(r_drag_move["action"], "DRAG_MOVE")

        # Release fingers -> DRAG_RELEASE
        r_release = engine.process(lm_open, timestamp=1.70)
        self.assertEqual(r_release["action"], "DRAG_RELEASE")
        self.assertEqual(engine.tap_state, "UP")

    def test_click_anchor_lock(self):
        """Verifies that coordinates are locked during tap contact to eliminate aim drift."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(tap_close=False)
        r_move = engine.process(lm_open, timestamp=1.0)
        anchor_x, anchor_y = r_move["cursor_x"], r_move["cursor_y"]

        # Tap occurs
        lm_tap = self._create_mock_landmarks(tap_close=True)
        r_tap = engine.process(lm_tap, timestamp=1.05)

        # Output cursor position during tap MUST match the locked anchor position
        self.assertEqual(r_tap["cursor_x"], anchor_x)
        self.assertEqual(r_tap["cursor_y"], anchor_y)

    def test_super_gesture_detection(self):
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_super = self._create_mock_landmarks(super_pose=True)
        is_detected = engine.is_super_gesture(lm_super)
        self.assertTrue(is_detected, "Super gesture should be detected when last 3 fingers are upright.")


class TestTargetLockManager(unittest.TestCase):
    def test_magnetic_attraction_and_breakout(self):
        """Tests that magnetic lock snaps towards targets at low velocity and breaks out at high velocity."""
        mgr = TargetLockManager(capture_radius=40.0, breakout_velocity=350.0)
        # Mock a close button target
        mgr._override_target = {
            "role": ROLE_SYSTEM_PUSHBUTTON,
            "role_name": "CLOSE [X]",
            "rect": (1300, 50, 46, 32),
            "center": (1323.0, 66.0),
        }

        # 1. Cursor nearby at low velocity (slow approach: 15 px/s)
        near_x, near_y = 1310.0, 60.0
        snapped_x, snapped_y, is_locked, desc = mgr.apply_magnetic_lock(near_x, near_y, velocity=15.0, timestamp=1.0)
        self.assertTrue(is_locked)
        self.assertEqual(desc, "CLOSE [X]")
        # Must be pulled closer to center (1323, 66) than near_x (1310)
        self.assertGreater(snapped_x, near_x)

        # 2. Fast flick breakout (velocity = 450 px/s > 350 px/s breakout threshold)
        bx, by, is_locked2, desc2 = mgr.apply_magnetic_lock(near_x, near_y, velocity=450.0, timestamp=1.1)
        self.assertFalse(is_locked2, "High velocity must trigger instant breakout from magnetic lock")
        self.assertEqual(bx, int(near_x))


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
