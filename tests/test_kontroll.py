"""
Unit & Integration Test Suite for Project Kontroll (OS Aim Assist & New Gestures Edition).
Verifies:
1. 1€ filtering & kinetic deadband stillness jitter suppression
2. Rapid velocity tracking response
3. Closed-Fist Index-Thumb Left Click & Rapid Double Click
4. Index-Thumb with 3 Fingers UP for Drag & Drop
5. Index-on-Middle Tap for Right Click
6. Open-hand false-click immunity (must be closed fist for left click)
7. OS-Level Sticky Aim Assist Cling & Breakout
8. Hand exit immediate state reset
9. Hardware mouse simulator bounds & autostart registry
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
    def _create_mock_landmarks(
        self,
        fist_closed=False,
        fist_left_tap=False,
        drag_super_pose=False,
        right_click_tap=False,
    ):
        lm = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        # Wrist = 0
        lm[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        # Middle MCP = 9 (scale = 0.3)
        lm[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)

        # Knuckles
        lm[5] = SimpleNamespace(x=0.42, y=0.52, z=0.0)   # Index MCP
        lm[17] = SimpleNamespace(x=0.58, y=0.52, z=0.0)  # Pinky MCP

        # Thumb
        lm[2] = SimpleNamespace(x=0.38, y=0.65, z=0.0)
        lm[3] = SimpleNamespace(x=0.38, y=0.58, z=0.0)
        lm[4] = SimpleNamespace(x=0.38, y=0.52, z=0.0)

        # Index tip (8), PIP (6)
        lm[6] = SimpleNamespace(x=0.40, y=0.45, z=0.0)
        lm[8] = SimpleNamespace(x=0.40, y=0.35, z=0.0)   # extended index by default

        # Middle tip (12), PIP (10)
        lm[10] = SimpleNamespace(x=0.50, y=0.45, z=0.0)
        lm[12] = SimpleNamespace(x=0.50, y=0.35, z=0.0)  # extended middle by default

        # Ring (16, 14)
        lm[14] = SimpleNamespace(x=0.54, y=0.47, z=0.0)
        lm[16] = SimpleNamespace(x=0.54, y=0.37, z=0.0)

        # Pinky (20, 18)
        lm[18] = SimpleNamespace(x=0.58, y=0.49, z=0.0)
        lm[20] = SimpleNamespace(x=0.58, y=0.39, z=0.0)

        if fist_closed:
            # Middle, Ring, Pinky curled into palm (tips y >= pip y)
            lm[12] = SimpleNamespace(x=0.50, y=0.58, z=0.0)
            lm[16] = SimpleNamespace(x=0.54, y=0.60, z=0.0)
            lm[20] = SimpleNamespace(x=0.58, y=0.62, z=0.0)

        if fist_left_tap:
            # Fist closed + Index tip touches Thumb tip
            lm[12] = SimpleNamespace(x=0.50, y=0.58, z=0.0)
            lm[16] = SimpleNamespace(x=0.54, y=0.60, z=0.0)
            lm[20] = SimpleNamespace(x=0.58, y=0.62, z=0.0)
            lm[4] = SimpleNamespace(x=0.42, y=0.50, z=0.0)
            lm[8] = SimpleNamespace(x=0.425, y=0.50, z=0.0)

        if drag_super_pose:
            # Thumb + Index touch, while Middle, Ring, Pinky are straight UP
            lm[4] = SimpleNamespace(x=0.42, y=0.50, z=0.0)
            lm[8] = SimpleNamespace(x=0.425, y=0.50, z=0.0)
            lm[12] = SimpleNamespace(x=0.50, y=0.28, z=0.0)
            lm[16] = SimpleNamespace(x=0.54, y=0.30, z=0.0)
            lm[20] = SimpleNamespace(x=0.58, y=0.32, z=0.0)

        if right_click_tap:
            # Index tip touches Middle tip, both extended
            lm[8] = SimpleNamespace(x=0.495, y=0.35, z=0.0)
            lm[12] = SimpleNamespace(x=0.50, y=0.35, z=0.0)

        return lm

    def test_closed_fist_left_click(self):
        """Verifies closed-fist index-on-thumb tap triggers left click on release."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_fist = self._create_mock_landmarks(fist_closed=True)
        res1 = engine.process(lm_fist, timestamp=1.0)
        self.assertEqual(res1["action"], "MOVE")

        lm_tap = self._create_mock_landmarks(fist_left_tap=True)
        res2 = engine.process(lm_tap, timestamp=1.05)
        self.assertEqual(res2["action"], "TAP_CONTACT")

        res3 = engine.process(lm_fist, timestamp=1.18)
        self.assertEqual(res3["action"], "CLICK")

    def test_closed_fist_double_click(self):
        """Verifies rapid second tap triggers double click."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_fist = self._create_mock_landmarks(fist_closed=True)
        lm_tap = self._create_mock_landmarks(fist_left_tap=True)

        engine.process(lm_fist, timestamp=1.0)
        engine.process(lm_tap, timestamp=1.05)
        r1 = engine.process(lm_fist, timestamp=1.15)
        self.assertEqual(r1["action"], "CLICK")

        engine.process(lm_tap, timestamp=1.25)
        r2 = engine.process(lm_fist, timestamp=1.35)
        self.assertEqual(r2["action"], "DOUBLE_CLICK")

    def test_open_hand_no_left_click(self):
        """Touching index to thumb while hand is open (not a fist) does NOT trigger left click."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        # Index and thumb touching, but fingers are open (not a fist, not super)
        lm_open_touch = self._create_mock_landmarks(fist_closed=False)
        lm_open_touch[4] = SimpleNamespace(x=0.42, y=0.50, z=0.0)
        lm_open_touch[8] = SimpleNamespace(x=0.425, y=0.50, z=0.0)

        scale = engine._get_hand_scale(lm_open_touch)
        tap_ratio, is_contact = engine.compute_tap_metric(lm_open_touch, scale)
        self.assertFalse(is_contact)

    def test_drag_super_gesture_and_release(self):
        """Index on thumb with last three fingers UP engages Drag."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(fist_closed=False)
        lm_drag = self._create_mock_landmarks(drag_super_pose=True)

        engine.process(lm_open, timestamp=1.0)
        engine.process(lm_drag, timestamp=1.05)
        # Held >= 150ms
        r_drag = engine.process(lm_drag, timestamp=1.25)
        self.assertEqual(r_drag["action"], "DRAG_START")
        self.assertTrue(engine.is_dragging)

        # Release drag
        r_release = engine.process(lm_open, timestamp=1.35)
        self.assertEqual(r_release["action"], "DRAG_RELEASE")
        self.assertFalse(engine.is_dragging)

    def test_right_click_index_middle_tap(self):
        """Tapping index on middle fingertip triggers Right Click."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(fist_closed=False)
        lm_right_tap = self._create_mock_landmarks(right_click_tap=True)

        engine.process(lm_open, timestamp=1.0)
        r_down = engine.process(lm_right_tap, timestamp=1.05)
        self.assertEqual(r_down["action"], "RIGHT_CONTACT")

        r_up = engine.process(lm_open, timestamp=1.18)
        self.assertEqual(r_up["action"], "RIGHT_CLICK")

    def test_reset_hand_state(self):
        """When hand leaves view, reset_hand_state clears all active states."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_tap = self._create_mock_landmarks(fist_left_tap=True)
        engine.process(lm_tap, timestamp=1.0)
        self.assertEqual(engine.tap_state, "DOWN")

        engine.reset_hand_state()
        self.assertEqual(engine.tap_state, "UP")
        self.assertEqual(engine.right_click_state, "UP")
        self.assertFalse(engine.is_dragging)


    def test_fist_closed_helper(self):
        """Verifies fist detection helper accurately differentiates open hand vs closed fist."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_open = self._create_mock_landmarks(fist_closed=False)
        scale_open = engine._get_hand_scale(lm_open)
        self.assertFalse(engine.is_fist_closed(lm_open, scale_open))

        lm_fist = self._create_mock_landmarks(fist_closed=True)
        scale_fist = engine._get_hand_scale(lm_fist)
        self.assertTrue(engine.is_fist_closed(lm_fist, scale_fist))

    def test_right_click_middle_curled_immune(self):
        """If middle finger is curled, index touching it does NOT trigger right click."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm = self._create_mock_landmarks(right_click_tap=True)
        # Force middle finger curled
        lm[12] = SimpleNamespace(x=0.50, y=0.58, z=0.0)
        res = engine.process(lm, timestamp=1.0)
        self.assertNotEqual(res["action"], "RIGHT_CONTACT")


class TestTargetLockManager(unittest.TestCase):
    def test_sticky_aim_assist_cling_and_breakout(self):
        """Verifies cursor CLINGS directly to button center and breaks out on fast flick."""
        mgr = TargetLockManager(capture_radius=40.0, breakout_velocity=260.0)
        mgr._override_target = {
            "role": ROLE_SYSTEM_PUSHBUTTON,
            "role_name": "CLOSE [X]",
            "rect": (1300, 50, 46, 32),
            "center": (1323.0, 66.0),
        }

        near_x, near_y = 1315.0, 58.0
        snapped_x, snapped_y, is_locked, desc = mgr.apply_magnetic_lock(near_x, near_y, velocity=20.0, timestamp=1.0)
        self.assertTrue(is_locked)
        self.assertEqual(desc, "CLOSE [X]")
        # Must CLING directly to center (1323, 66)
        self.assertEqual(snapped_x, 1323)
        self.assertEqual(snapped_y, 66)

        # Fast hand flick exceeds breakout velocity
        bx, by, is_locked2, desc2 = mgr.apply_magnetic_lock(near_x, near_y, velocity=350.0, timestamp=1.1)
        self.assertFalse(is_locked2)
        self.assertEqual(bx, int(near_x))

    def test_sticky_aim_assist_inside_bounding_box(self):
        """Verifies cursor inside element bounding box clings to center even if not dead-center."""
        mgr = TargetLockManager(capture_radius=30.0, breakout_velocity=260.0)
        mgr._override_target = {
            "role": ROLE_SYSTEM_PUSHBUTTON,
            "role_name": "MAXIMIZE [□]",
            "rect": (1250, 50, 46, 32),
            "center": (1273.0, 66.0),
        }

        corner_x, corner_y = 1252.0, 52.0
        snapped_x, snapped_y, is_locked, desc = mgr.apply_magnetic_lock(corner_x, corner_y, velocity=15.0, timestamp=1.0)
        self.assertTrue(is_locked)
        self.assertEqual(snapped_x, 1273)
        self.assertEqual(snapped_y, 66)


class TestInputAndAutostart(unittest.TestCase):
    def test_mouse_simulator_bounds(self):
        mouse = MouseSimulator()
        self.assertGreater(mouse.screen_width, 0)
        self.assertGreater(mouse.screen_height, 0)

    def test_autostart_command_string(self):
        cmd = get_launch_command()
        self.assertIn("main.py", cmd)
        self.assertIn("--autostart", cmd)


if __name__ == "__main__":
    unittest.main()
