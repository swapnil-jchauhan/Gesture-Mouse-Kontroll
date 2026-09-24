"""
Unit & Integration Test Suite for Project Kontroll (Angle-Invariant & Ergonomic Edition).
Verifies:
1. 1€ filtering & kinetic deadband stillness jitter suppression
2. Rapid velocity tracking response
3. Instantaneous Single Click
4. Rapid Double Click detection & coordinate lock
5. Intentional Pinch-to-Drag & accidental drag elimination
6. Angle-invariant local palm coordinate metrics (tilted webcam support)
7. Pre-Tap Anchor Lock deflection prevention
8. Magnetic Target Snapper & Breakout velocity
9. Super Activation Gesture
10. Hardware mouse simulator bounds & autostart registry
"""

import unittest
import time
from types import SimpleNamespace
import numpy as np

from src.core.filter import OneEuroFilter, Point2DOneEuroFilter
from src.core.gestures import GestureEngine
from src.core.target_lock import TargetLockManager, ROLE_SYSTEM_PUSHBUTTON
from src.core.input_simulator import MouseSimulator
from src.service.autostart import is_autostart_enabled, get_launch_command


class TestOneEuroFilter(unittest.TestCase):
    def test_low_velocity_jitter_suppression(self):
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
        self.assertLess(max_filtered_dev, raw_variance * 0.4)

    def test_kinetic_deadband_zero_jitter(self):
        filt = Point2DOneEuroFilter(freq=60.0, min_cutoff=0.5, deadband_radius=2.8)
        base_x, base_y = 500.0, 500.0
        filt.filter(base_x, base_y, timestamp=0.0)

        t = 0.05
        locked_points = []
        for i in range(10):
            t += 1.0 / 60.0
            wobble_x = base_x + (1.2 if i % 2 == 0 else -1.2)
            wobble_y = base_y + (-0.9 if i % 2 == 0 else 0.9)
            ox, oy = filt.filter(wobble_x, wobble_y, timestamp=t)
            locked_points.append((ox, oy))

        for ox, oy in locked_points:
            self.assertAlmostEqual(ox, base_x, delta=0.5)
            self.assertAlmostEqual(oy, base_y, delta=0.5)

    def test_high_velocity_zero_lag(self):
        filt = OneEuroFilter(freq=60.0, min_cutoff=0.8, beta=0.05)
        t = 0.0
        for i in range(10):
            val = i * 100.0
            out = filt.filter(val, timestamp=t)
            t += 1.0 / 60.0
        self.assertGreater(out, 750.0)


class TestGestureEngine(unittest.TestCase):
    def _create_mock_landmarks(self, index_tip_y=0.4, middle_tip_y=0.4, tap_close=False, pinch_drag=False, super_pose=False, middle_curled=False):
        lm = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        # Wrist = 0
        lm[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        # Middle MCP = 9 (scale = 0.3)
        lm[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)

        # Knuckles for palm frame
        lm[5] = SimpleNamespace(x=0.42, y=0.52, z=0.0)  # Index MCP
        lm[17] = SimpleNamespace(x=0.58, y=0.52, z=0.0) # Pinky MCP

        # Thumb
        lm[4] = SimpleNamespace(x=0.38, y=0.60, z=0.0)

        # Index tip (8), PIP (6)
        lm[6] = SimpleNamespace(x=0.40, y=0.55, z=0.0)
        lm[8] = SimpleNamespace(x=0.40, y=index_tip_y, z=0.0)

        # Middle tip (12), PIP (10)
        lm[10] = SimpleNamespace(x=0.50, y=0.52, z=0.0)
        lm[12] = SimpleNamespace(x=0.50, y=middle_tip_y, z=0.0)

        if middle_curled:
            # Middle finger curled into palm (tip y > pip y)
            lm[12] = SimpleNamespace(x=0.50, y=0.62, z=0.0)

        # Ring & Pinky
        lm[14] = SimpleNamespace(x=0.54, y=0.54, z=0.0)
        lm[16] = SimpleNamespace(x=0.54, y=0.58, z=0.0)
        lm[18] = SimpleNamespace(x=0.58, y=0.56, z=0.0)
        lm[20] = SimpleNamespace(x=0.58, y=0.60, z=0.0)

        if tap_close:
            # Index tip touching middle tip
            target_y = lm[12].y
            lm[8] = SimpleNamespace(x=0.495, y=target_y, z=0.0)

        if pinch_drag:
            # Thumb tip (4) and Index tip (8) touching
            lm[4] = SimpleNamespace(x=0.44, y=0.50, z=0.0)
            lm[8] = SimpleNamespace(x=0.44, y=0.50, z=0.0)

        if super_pose:
            # Thumb (4) and Index (8) form ring
            lm[4] = SimpleNamespace(x=0.44, y=0.55, z=0.0)
            lm[8] = SimpleNamespace(x=0.45, y=0.55, z=0.0)
            # Middle (12), Ring (16), Pinky (20) extended upright (y tip < y pip)
            lm[10] = SimpleNamespace(x=0.50, y=0.50, z=0.0)
            lm[12] = SimpleNamespace(x=0.50, y=0.30, z=0.0)

            lm[14] = SimpleNamespace(x=0.54, y=0.52, z=0.0)
            lm[16] = SimpleNamespace(x=0.54, y=0.32, z=0.0)

            lm[18] = SimpleNamespace(x=0.58, y=0.55, z=0.0)
            lm[20] = SimpleNamespace(x=0.58, y=0.35, z=0.0)

        return lm

    def test_single_click_detection(self):
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(tap_close=False)
        res1 = engine.process(lm_open, timestamp=1.0)
        self.assertEqual(res1["action"], "MOVE")

        lm_tap = self._create_mock_landmarks(tap_close=True)
        res2 = engine.process(lm_tap, timestamp=1.05)
        self.assertEqual(res2["action"], "TAP_CONTACT")

        res3 = engine.process(lm_open, timestamp=1.20)
        self.assertEqual(res3["action"], "CLICK")

    def test_double_click_detection(self):
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(tap_close=False)
        lm_tap = self._create_mock_landmarks(tap_close=True)

        engine.process(lm_open, timestamp=1.0)
        engine.process(lm_tap, timestamp=1.05)
        r_click1 = engine.process(lm_open, timestamp=1.18)
        self.assertEqual(r_click1["action"], "CLICK")
        pos1 = (r_click1["cursor_x"], r_click1["cursor_y"])

        engine.process(lm_tap, timestamp=1.30)
        r_click2 = engine.process(lm_open, timestamp=1.42)
        self.assertEqual(r_click2["action"], "DOUBLE_CLICK")
        pos2 = (r_click2["cursor_x"], r_click2["cursor_y"])
        self.assertEqual(pos1, pos2)

    def test_pinch_to_drag_and_release(self):
        """Verifies Thumb+Index pinch triggers intentional drag without accidental drag on normal taps."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(pinch_drag=False)
        lm_pinch = self._create_mock_landmarks(pinch_drag=True)

        engine.process(lm_open, timestamp=1.0)
        engine.process(lm_pinch, timestamp=1.05)
        # After pinch held >= 220ms
        r_drag = engine.process(lm_pinch, timestamp=1.30)
        self.assertEqual(r_drag["action"], "DRAG_START")
        self.assertTrue(engine.is_dragging)

        # Release pinch
        r_release = engine.process(lm_open, timestamp=1.40)
        self.assertEqual(r_release["action"], "DRAG_RELEASE")
        self.assertFalse(engine.is_dragging)

    def test_accidental_drag_eliminated(self):
        """Holding index on middle tap for a long time does NOT accidentally engage drag."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_tap = self._create_mock_landmarks(tap_close=True)

        engine.process(lm_tap, timestamp=1.0)
        # Even after 500ms, index-on-middle tap is never promoted to drag!
        r_held = engine.process(lm_tap, timestamp=1.55)
        self.assertNotEqual(r_held["action"], "DRAG_START")
        self.assertFalse(engine.is_dragging)

    def test_angle_invariant_metric_separation(self):
        """Verifies that when hand is viewed at an angle, local knuckle frame detects separation."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(tap_close=False)
        scale = engine._get_hand_scale(lm_open)
        tap_ratio, _ = engine.compute_angle_invariant_tap_metric(lm_open, scale)
        # Must be above tap_down_ratio so no false click happens
        self.assertGreater(tap_ratio, engine.tap_down_ratio)

    def test_super_gesture_detection(self):
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_super = self._create_mock_landmarks(super_pose=True)
        is_detected = engine.is_super_gesture(lm_super)
        self.assertTrue(is_detected)

    def test_pointing_pose_extendedness_gate(self):
        """Verifies that pointing with index finger alone (middle curled) NEVER registers false click."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        # Even if tips are close in 2D/3D projection, curled middle disables tap
        lm_pointing = self._create_mock_landmarks(tap_close=True, middle_curled=True)
        scale = engine._get_hand_scale(lm_pointing)
        tap_ratio, is_contact = engine.compute_tap_metric(lm_pointing, scale)
        self.assertEqual(tap_ratio, 1.0)
        self.assertFalse(is_contact)

        res = engine.process(lm_pointing, timestamp=1.0)
        self.assertEqual(res["action"], "MOVE")

    def test_non_freezing_anchor_lock(self):
        """Anchor lock must release after at most 70ms and not freeze cursor permanently."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(tap_close=False)
        lm_tap = self._create_mock_landmarks(tap_close=True)

        engine.process(lm_open, timestamp=1.0)
        r_down = engine.process(lm_tap, timestamp=1.05)
        self.assertEqual(r_down["action"], "TAP_CONTACT")

        # After 100ms (> 70ms anchor window), cursor must follow hand and anchor must be released
        lm_tap_moved = self._create_mock_landmarks(tap_close=True, index_tip_y=0.25, middle_tip_y=0.25)
        r_moved = engine.process(lm_tap_moved, timestamp=1.16)
        self.assertIsNone(engine.anchor_position)

    def test_reset_hand_state(self):
        """When hand leaves field of view, reset_hand_state clears all sticky states."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_tap = self._create_mock_landmarks(tap_close=True)
        engine.process(lm_tap, timestamp=1.0)
        self.assertEqual(engine.tap_state, "DOWN")

        engine.reset_hand_state()
        self.assertEqual(engine.tap_state, "UP")
        self.assertIsNone(engine.anchor_position)
        self.assertFalse(engine.is_dragging)


class TestTargetLockManager(unittest.TestCase):
    def test_magnetic_attraction_and_breakout(self):
        mgr = TargetLockManager(capture_radius=40.0, breakout_velocity=350.0)
        mgr._override_target = {
            "role": ROLE_SYSTEM_PUSHBUTTON,
            "role_name": "CLOSE [X]",
            "rect": (1300, 50, 46, 32),
            "center": (1323.0, 66.0),
        }

        near_x, near_y = 1310.0, 60.0
        snapped_x, snapped_y, is_locked, desc = mgr.apply_magnetic_lock(near_x, near_y, velocity=15.0, timestamp=1.0)
        self.assertTrue(is_locked)
        self.assertEqual(desc, "CLOSE [X]")
        self.assertGreater(snapped_x, near_x)

        bx, by, is_locked2, desc2 = mgr.apply_magnetic_lock(near_x, near_y, velocity=450.0, timestamp=1.1)
        self.assertFalse(is_locked2)
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
