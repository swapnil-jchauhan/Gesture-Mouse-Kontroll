"""
Unit & Integration Test Suite for Project Kontroll (God-Tier Tracking Overhaul Edition).
Verifies the 5 Core Engineering Pillars:
1. Sub-Pixel Pyramidal Lucas-Kanade Optical Flow Refinement & Stillness Guarantee (Pillar 1)
2. 3D Desk Homography & Perspective Un-Tilting (Pillar 2)
3. Orthogonal Natural Gestures: Closed-Fist Left Click, Middle-Thumb Right Click,
   Super-Gesture Drag, Hawaiian Shaka Toggle, 0% Collinear Occlusion Ghost Clicks (Pillar 3)
4. Relative Ballistics with Biomechanical Air-Clutching & Dynamic S-Curve (Pillar 4)
5. Viscous Deceleration Aim Assist Bubbles & Click Anchor (Pillar 5)
6. 120 FPS Jarvis Boot Sequence, RyanNeural British Voice, and Zero-Dash/Slash Formatting.
"""

import unittest
import time
import math
import os
import ast
import re
from types import SimpleNamespace
import numpy as np
import cv2

from src.core.filter import OneEuroFilter, Point2DOneEuroFilter
from src.core.optical_flow import SubPixelOpticalFlowTracker
from src.core.homography import DeskHomography
from src.core.ballistics import RelativeBallisticsEngine
from src.core.gestures import GestureEngine
from src.core.target_lock import TargetLockManager, ROLE_SYSTEM_PUSHBUTTON
from src.core.input_simulator import MouseSimulator
from src.service.autostart import is_autostart_enabled, get_launch_command
from src.core.voice import PROJECT_ROOT


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


class TestOpticalFlow(unittest.TestCase):
    def test_optical_flow_stillness(self):
        """
        Pillar 1 Acceptance Test:
        Verify that identical consecutive frames or sub-pixel noise yields zero displacement (dx = 0.0, dy = 0.0).
        """
        tracker = SubPixelOpticalFlowTracker(roi_size=48, stillness_threshold=0.40)

        # Create a synthetic 640x480 frame with natural visual texture/corners
        frame1 = np.zeros((480, 640), dtype=np.uint8)
        for i in range(200, 280, 8):
            cv2.line(frame1, (i, 200), (i, 280), 200, 2)
            cv2.line(frame1, (200, i), (280, i), 150, 2)
        cv2.circle(frame1, (320, 240), 18, 255, -1)

        # Initial frame
        dx0, dy0, x0, y0 = tracker.update(frame1, (320.0, 240.0), has_hand=True, timestamp=1.0)
        self.assertEqual(dx0, 0.0)
        self.assertEqual(dy0, 0.0)

        # Consecutive identical frame: laser-mouse stillness guarantee!
        dx1, dy1, x1, y1 = tracker.update(frame1, (320.0, 240.0), has_hand=True, timestamp=1.033)
        self.assertEqual(dx1, 0.0)
        self.assertEqual(dy1, 0.0)
        self.assertTrue(tracker.is_still)

        # Frame with sub-pixel sensor noise added (< stillness_threshold)
        noise = np.random.normal(0, 0.2, frame1.shape).astype(np.int16)
        noisy_frame = np.clip(frame1.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        dx2, dy2, x2, y2 = tracker.update(noisy_frame, (320.1, 240.1), has_hand=True, timestamp=1.066)
        self.assertEqual(dx2, 0.0)
        self.assertEqual(dy2, 0.0)
        self.assertTrue(tracker.is_still)


class TestHomography(unittest.TestCase):
    def test_homography_tilted_sweep(self):
        """
        Pillar 2 Acceptance Test:
        Verify that a 35° angled physical movement vector maps to a pure horizontal screen vector after desk un-tilting.
        """
        homography = DeskHomography(mode="left", default_tilt_deg=35.0, pitch_deg=0.0)

        theta = math.radians(35.0)
        # In a 35° yaw setup, physical rightward movement creates an angled vector in camera frame
        length = 120.0
        dx_cam = length * math.cos(theta)
        dy_cam = length * math.sin(theta)

        dx_desk, dy_desk = homography.transform_vector(dx_cam, dy_cam)
        self.assertAlmostEqual(dy_desk, 0.0, places=3)
        self.assertAlmostEqual(dx_desk, length, places=3)

    def test_homography_palm_normal(self):
        """Verifies palm normal computation from 3D knuckle landmarks."""
        lm = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)    # Wrist
        lm[5] = SimpleNamespace(x=0.45, y=0.50, z=0.0)  # Index MCP
        lm[17] = SimpleNamespace(x=0.55, y=0.50, z=0.0) # Pinky MCP

        normal = DeskHomography.compute_palm_normal(lm)
        self.assertEqual(len(normal), 3)
        self.assertAlmostEqual(np.linalg.norm(normal), 1.0, places=5)


class TestRelativeBallistics(unittest.TestCase):
    def test_relative_ballistics_clutching(self):
        """
        Pillar 4 Acceptance Test:
        Verify that relaxing pointing pose immediately stops cursor dispatch (clutch disengage).
        """
        ballistics = RelativeBallisticsEngine(screen_width=1920, screen_height=1080, mode="relative")

        # 1. Engaged pointing pose moves cursor
        start_x, start_y = ballistics.cursor_x, ballistics.cursor_y
        x1, y1, v1 = ballistics.update(dx=30.0, dy=15.0, dt=0.016, is_engaged=True)
        self.assertNotEqual(x1, start_x)
        self.assertNotEqual(y1, start_y)
        self.assertGreater(v1, 0.0)

        # 2. Relaxed / Clutched hand disengages tracking completely
        x2, y2, v2 = ballistics.update(dx=80.0, dy=60.0, dt=0.016, is_engaged=False)
        self.assertEqual(x2, x1)
        self.assertEqual(y2, y1)
        self.assertEqual(v2, 0.0)

    def test_air_clutch_pose_classification(self):
        """Verify biomechanical pointing pose is engaged while open flat hand or curled index clutches."""
        ballistics = RelativeBallisticsEngine()

        # Mock Pointing Pose (Index extended, middle/ring/pinky curled)
        lm_pointing = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm_pointing[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        lm_pointing[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)
        lm_pointing[5] = SimpleNamespace(x=0.42, y=0.52, z=0.0)
        lm_pointing[6] = SimpleNamespace(x=0.40, y=0.45, z=0.0)
        lm_pointing[8] = SimpleNamespace(x=0.40, y=0.32, z=0.0)  # Extended index
        # Curled middle, ring, pinky
        lm_pointing[12] = SimpleNamespace(x=0.50, y=0.58, z=0.0)
        lm_pointing[16] = SimpleNamespace(x=0.54, y=0.60, z=0.0)
        lm_pointing[20] = SimpleNamespace(x=0.58, y=0.62, z=0.0)

        scale = 0.30
        is_pointing, is_clutched = ballistics.check_air_clutch(lm_pointing, scale)
        self.assertTrue(is_pointing)
        self.assertFalse(is_clutched)

        # Mock Flat Open Hand (all 5 fingers extended) -> Clutched
        lm_flat = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm_flat[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        lm_flat[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)
        lm_flat[8] = SimpleNamespace(x=0.40, y=0.30, z=0.0)
        lm_flat[10] = SimpleNamespace(x=0.50, y=0.45, z=0.0)
        lm_flat[12] = SimpleNamespace(x=0.50, y=0.30, z=0.0)  # Extended middle
        lm_flat[14] = SimpleNamespace(x=0.54, y=0.45, z=0.0)
        lm_flat[16] = SimpleNamespace(x=0.54, y=0.30, z=0.0)  # Extended ring
        lm_flat[18] = SimpleNamespace(x=0.58, y=0.45, z=0.0)
        lm_flat[20] = SimpleNamespace(x=0.58, y=0.30, z=0.0)  # Extended pinky

        is_pointing_flat, is_clutched_flat = ballistics.check_air_clutch(lm_flat, scale)
        self.assertTrue(is_clutched_flat)


class TestTargetLockViscous(unittest.TestCase):
    def test_viscous_aim_assist_deceleration(self):
        """
        Pillar 5 Acceptance Test:
        Verify that entering button proximity scales velocity down smoothly without position jumping.
        """
        mgr = TargetLockManager(capture_radius=42.0, breakout_velocity=750.0, bubble_radius=35.0, max_damping=0.65)

        # Outside bubble (> 35 px): normal 1.0 scale
        scale_far = mgr.compute_viscous_scale(distance_to_target=60.0, velocity=50.0)
        self.assertEqual(scale_far, 1.0)

        # At boundary (35 px): 1.0 scale
        scale_boundary = mgr.compute_viscous_scale(distance_to_target=35.0, velocity=50.0)
        self.assertEqual(scale_boundary, 1.0)

        # Inside deceleration bubble (17.5 px half-way): scales down smoothly by ~32.5%
        scale_mid = mgr.compute_viscous_scale(distance_to_target=17.5, velocity=50.0)
        self.assertAlmostEqual(scale_mid, 1.0 - 0.65 * 0.5, places=2)

        # At target center (0 px): scaled down by max 65% (scale = 0.35)
        scale_center = mgr.compute_viscous_scale(distance_to_target=0.0, velocity=50.0)
        self.assertAlmostEqual(scale_center, 0.35, places=2)

        # Fast intentional flick (>= 750 px/s): breaks out instantly (scale = 1.0)
        scale_breakout = mgr.compute_viscous_scale(distance_to_target=10.0, velocity=850.0)
        self.assertEqual(scale_breakout, 1.0)


class TestGestureEngine(unittest.TestCase):
    def _create_mock_landmarks(
        self,
        fist_closed=False,
        fist_left_tap=False,
        drag_super_pose=False,
        right_click_tap=False,
        shaka_pose=False,
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
            # Middle tip touches Thumb tip (Pillar 3 Orthogonal Right Click)
            lm[4] = SimpleNamespace(x=0.46, y=0.50, z=0.0)
            lm[12] = SimpleNamespace(x=0.465, y=0.50, z=0.0)
            lm[16] = SimpleNamespace(x=0.54, y=0.60, z=0.0)
            lm[20] = SimpleNamespace(x=0.58, y=0.62, z=0.0)

        if shaka_pose:
            # Thumb (4) and Pinky (20) extended OUT, Index (8), Middle (12), Ring (16) curled
            lm[4] = SimpleNamespace(x=0.22, y=0.44, z=0.0)
            lm[20] = SimpleNamespace(x=0.74, y=0.38, z=0.0)
            lm[6] = SimpleNamespace(x=0.42, y=0.55, z=0.0)
            lm[8] = SimpleNamespace(x=0.42, y=0.62, z=0.0)
            lm[10] = SimpleNamespace(x=0.50, y=0.55, z=0.0)
            lm[12] = SimpleNamespace(x=0.50, y=0.62, z=0.0)
            lm[14] = SimpleNamespace(x=0.56, y=0.55, z=0.0)
            lm[16] = SimpleNamespace(x=0.56, y=0.62, z=0.0)

        return lm

    def test_default_standby_state(self):
        """Verifies GestureEngine defaults to STANDBY (is_active=False) on initialization."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        self.assertFalse(engine.is_active)
        lm_open = self._create_mock_landmarks(fist_closed=False)
        res = engine.process(lm_open, timestamp=1.0)
        self.assertFalse(res["active"])
        self.assertEqual(res["action"], "STANDBY")

    def test_closed_fist_left_click(self):
        """Verifies closed-fist index-on-thumb tap triggers left click on release."""
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
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
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
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
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        lm_open_touch = self._create_mock_landmarks(fist_closed=False)
        lm_open_touch[4] = SimpleNamespace(x=0.42, y=0.50, z=0.0)
        lm_open_touch[8] = SimpleNamespace(x=0.425, y=0.50, z=0.0)

        scale = engine._get_hand_scale(lm_open_touch)
        tap_ratio, is_contact = engine.compute_tap_metric(lm_open_touch, scale)
        self.assertFalse(is_contact)

    def test_drag_super_gesture_and_release(self):
        """Index on thumb with last three fingers UP engages Drag."""
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        lm_open = self._create_mock_landmarks(fist_closed=False)
        lm_drag = self._create_mock_landmarks(drag_super_pose=True)

        engine.process(lm_open, timestamp=1.0)
        engine.process(lm_drag, timestamp=1.05)
        r_drag = engine.process(lm_drag, timestamp=1.25)
        self.assertEqual(r_drag["action"], "DRAG_START")
        self.assertTrue(engine.is_dragging)

        # Release drag
        r_release = engine.process(lm_open, timestamp=1.35)
        self.assertEqual(r_release["action"], "DRAG_RELEASE")
        self.assertFalse(engine.is_dragging)

    def test_middle_thumb_right_click(self):
        """
        Pillar 3 Acceptance Test:
        Verifies that index pointing produces zero right-click triggers, and middle-to-thumb tap triggers right-click.
        """
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        lm_open = self._create_mock_landmarks(fist_closed=False)

        # 1. Pointing freely forward produces zero right clicks
        res_move = engine.process(lm_open, timestamp=1.0)
        self.assertEqual(res_move["action"], "MOVE")

        # 2. Middle finger taps thumb triggers right click
        lm_right_tap = self._create_mock_landmarks(right_click_tap=True)
        r_down = engine.process(lm_right_tap, timestamp=1.05)
        self.assertEqual(r_down["action"], "RIGHT_CONTACT")

        r_up = engine.process(lm_open, timestamp=1.18)
        self.assertEqual(r_up["action"], "RIGHT_CLICK")

    def test_collinear_occlusion_zero_ghost_right_click(self):
        """When index touches middle finger (collinear line of sight occlusion), NO right click is triggered."""
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        lm = self._create_mock_landmarks(fist_closed=False)
        # Index and middle overlap in perspective along the camera ray
        lm[8] = SimpleNamespace(x=0.495, y=0.35, z=0.0)
        lm[12] = SimpleNamespace(x=0.50, y=0.35, z=0.0)
        lm[4] = SimpleNamespace(x=0.38, y=0.52, z=0.0)

        res = engine.process(lm, timestamp=1.0)
        self.assertNotEqual(res["action"], "RIGHT_CONTACT")
        self.assertNotEqual(res["action"], "RIGHT_CLICK")

    def test_reset_hand_state(self):
        """When hand leaves view, reset_hand_state clears all active states."""
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        lm_tap = self._create_mock_landmarks(fist_left_tap=True)
        engine.process(lm_tap, timestamp=1.0)
        self.assertEqual(engine.tap_state, "DOWN")

        engine.reset_hand_state()
        self.assertEqual(engine.tap_state, "UP")
        self.assertEqual(engine.right_click_state, "UP")
        self.assertFalse(engine.is_dragging)

    def test_fist_closed_helper(self):
        """Verifies fist detection helper accurately differentiates open hand vs closed fist."""
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        lm_open = self._create_mock_landmarks(fist_closed=False)
        scale_open = engine._get_hand_scale(lm_open)
        self.assertFalse(engine.is_fist_closed(lm_open, scale_open))

        lm_fist = self._create_mock_landmarks(fist_closed=True)
        scale_fist = engine._get_hand_scale(lm_fist)
        self.assertTrue(engine.is_fist_closed(lm_fist, scale_fist))

    def test_mirrored_horizontal_tracking(self):
        """Moving hand to physical right (camera image left) moves cursor to the right on screen."""
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        engine.mount_mode = "center"

        # In camera frame, x=0.35 is camera-left (user's physical right)
        lm_right = self._create_mock_landmarks()
        lm_right[8] = SimpleNamespace(x=0.35, y=0.60, z=0.0)
        r_right = engine.process(lm_right, timestamp=1.0)

        # In camera frame, x=0.65 is camera-right (user's physical left)
        lm_left = self._create_mock_landmarks()
        lm_left[8] = SimpleNamespace(x=0.65, y=0.60, z=0.0)
        r_left = engine.process(lm_left, timestamp=1.1)

        self.assertGreater(r_right["cursor_x"], r_left["cursor_x"])

    def test_shaka_gesture_detection(self):
        """Verifies Shaka gesture (🤙, thumb & pinky out, middle 3 curled) is accurately detected."""
        engine = GestureEngine(screen_width=1920, screen_height=1080)
        lm_shaka = self._create_mock_landmarks(shaka_pose=True)
        self.assertTrue(engine.is_shaka_gesture(lm_shaka))

        lm_open = self._create_mock_landmarks(fist_closed=False)
        self.assertFalse(engine.is_shaka_gesture(lm_open))

        lm_fist = self._create_mock_landmarks(fist_closed=True)
        self.assertFalse(engine.is_shaka_gesture(lm_fist))

    def test_shaka_activation_toggle(self):
        """Holding Shaka gesture for >= 0.35s toggles system state between STANDBY and ACTIVE."""
        toggled_states = []
        engine = GestureEngine(screen_width=1920, screen_height=1080, on_state_change=lambda s: toggled_states.append(s))
        self.assertFalse(engine.is_active)

        lm_shaka = self._create_mock_landmarks(shaka_pose=True)
        lm_open = self._create_mock_landmarks(fist_closed=False)

        # Open hand while in standby returns STANDBY action and no clicks
        res_standby = engine.process(lm_open, timestamp=0.5)
        self.assertFalse(res_standby["active"])
        self.assertEqual(res_standby["action"], "STANDBY")

        # Start holding Shaka
        engine.process(lm_shaka, timestamp=1.0)
        self.assertFalse(engine.is_active)

        # Held for 0.40s -> Toggles from STANDBY to ACTIVE
        res_toggle1 = engine.process(lm_shaka, timestamp=1.40)
        self.assertTrue(engine.is_active)
        self.assertIn(True, toggled_states)

        # Open hand while active returns MOVE
        res_move = engine.process(lm_open, timestamp=1.50)
        self.assertTrue(res_move["active"])
        self.assertEqual(res_move["action"], "MOVE")

        # Hold Shaka again to toggle back to STANDBY
        engine.process(lm_shaka, timestamp=2.0)
        res_toggle2 = engine.process(lm_shaka, timestamp=2.40)
        self.assertFalse(engine.is_active)
        self.assertIn(False, toggled_states)


class TestTargetLockManager(unittest.TestCase):
    def test_sticky_aim_assist_cling_and_breakout(self):
        """Verifies cursor CLINGS directly to button center, resists twitch, and breaks out on intentional flick."""
        mgr = TargetLockManager(capture_radius=42.0, breakout_velocity=750.0)
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

        # Finger twitch velocity (e.g. 400 px/s) while hovering button stays firmly locked!
        sx, sy, is_locked_twitch, _ = mgr.apply_magnetic_lock(near_x, near_y, velocity=400.0, timestamp=1.05)
        self.assertTrue(is_locked_twitch)
        self.assertEqual(sx, 1323)
        self.assertEqual(sy, 66)

        # Deliberate fast flick away (velocity > 750 px/s at dist >= 35) breaks out cleanly
        flick_x, flick_y = 1260.0, 50.0
        bx, by, is_locked2, desc2 = mgr.apply_magnetic_lock(flick_x, flick_y, velocity=850.0, timestamp=1.1)
        self.assertFalse(is_locked2)
        self.assertEqual(bx, int(flick_x))

    def test_sticky_aim_assist_click_anchor(self):
        """Verifies that during active click motion (is_clicking=True), lock is firmly anchored."""
        mgr = TargetLockManager(capture_radius=42.0, breakout_velocity=750.0)
        mgr._override_target = {
            "role": ROLE_SYSTEM_PUSHBUTTON,
            "role_name": "SUBMIT",
            "rect": (500, 400, 80, 40),
            "center": (540.0, 420.0),
        }
        # Initial lock onto button
        mgr.apply_magnetic_lock(535.0, 415.0, velocity=15.0, timestamp=1.0)
        self.assertTrue(mgr.is_locked)

        # Finger twitch tap with high velocity and slight drift while clicking
        sx, sy, locked, _ = mgr.apply_magnetic_lock(560.0, 435.0, velocity=600.0, timestamp=1.05, is_clicking=True)
        self.assertTrue(locked)
        self.assertEqual(sx, 540)
        self.assertEqual(sy, 420)

    def test_sticky_aim_assist_inside_bounding_box(self):
        """Verifies cursor inside element bounding box clings to center even if not dead-center."""
        mgr = TargetLockManager(capture_radius=30.0, breakout_velocity=750.0)
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

    def test_drag_start_initiates_double_click_hold(self):
        mouse = MouseSimulator()
        self.assertFalse(mouse._is_left_down)
        mouse.drag_start()
        self.assertTrue(mouse._is_left_down)
        mouse.left_up()
        self.assertFalse(mouse._is_left_down)


class TestJarvisHudOverlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        import sys
        if QApplication.instance() is None:
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def test_fullscreen_boot_overlay_initialization_and_tick(self):
        from src.ui.hud_overlay import FullScreenJarvisBootOverlay
        overlay = FullScreenJarvisBootOverlay(play_audio=False)
        self.assertGreater(overlay.w, 0)
        self.assertGreater(overlay.h, 0)
        self.assertGreaterEqual(overlay.target_opacity, 1.0)

        # Simulate animation tick
        overlay._on_tick()
        self.assertGreater(overlay.angle_outer, 0.0)
        self.assertGreater(overlay.pulse_phase, 0.0)
        overlay.anim_timer.stop()
        overlay.close()

    def test_fullscreen_boot_overlay_dismiss(self):
        from src.ui.hud_overlay import FullScreenJarvisBootOverlay
        completed = []
        overlay = FullScreenJarvisBootOverlay(on_complete=lambda: completed.append(True), play_audio=False)
        self.assertFalse(overlay.is_closing)
        overlay._dismiss_immediately()
        self.assertTrue(overlay.is_closing)
        self.assertEqual(overlay.target_opacity, 0.0)
        overlay.anim_timer.stop()
        overlay.close()

    def test_hud_overlay_popup_and_boot_trigger(self):
        from src.ui.hud_overlay import JarvisHudOverlay
        hud = JarvisHudOverlay()
        hud.trigger_popup(is_active=True)
        self.assertEqual(hud.status_title, "JARVIS ONLINE")
        self.assertEqual(hud.target_opacity, 1.0)

        hud.trigger_popup(is_active=False)
        self.assertEqual(hud.status_title, "SYSTEM STANDBY")

        # Test boot sequence trigger
        hud.trigger_boot_sequence()
        self.assertIsNotNone(hud._boot_window)
        hud._boot_window.anim_timer.stop()
        hud._boot_window.close()
        hud.anim_timer.stop()
        hud.close()

    def test_fullscreen_boot_overlay_paint_rendering(self):
        from PyQt6.QtGui import QPixmap
        from src.ui.hud_overlay import FullScreenJarvisBootOverlay
        overlay = FullScreenJarvisBootOverlay(play_audio=False)
        overlay.resize(1920, 1080)
        overlay.opacity = 1.0

        pixmap = QPixmap(1920, 1080)
        for elapsed_test in [0.3, 1.0, 2.0, 3.5, 5.0, 7.5, 8.2]:
            overlay.elapsed = elapsed_test
            overlay.render(pixmap)

        overlay.anim_timer.stop()
        overlay.close()


class TestVoiceSubsystem(unittest.TestCase):
    def test_dynamic_greeting_by_local_hour(self):
        import datetime
        from src.core.voice import get_boot_greeting_type, get_boot_greeting_text, get_boot_audio_path

        # Morning hours (< 12)
        for h in [0, 5, 8, 11]:
            dt = datetime.datetime(2026, 9, 25, h, 30)
            self.assertEqual(get_boot_greeting_type(dt), "morning")
            self.assertEqual(get_boot_greeting_text(dt), "Good morning. Systems online sir.")
            self.assertTrue(get_boot_audio_path(dt).endswith("boot_morning.mp3"))

        # Afternoon hours (12 <= h < 17)
        for h in [12, 13, 15, 16]:
            dt = datetime.datetime(2026, 9, 25, h, 30)
            self.assertEqual(get_boot_greeting_type(dt), "afternoon")
            self.assertEqual(get_boot_greeting_text(dt), "Good afternoon. Systems online sir.")
            self.assertTrue(get_boot_audio_path(dt).endswith("boot_afternoon.mp3"))

        # Evening hours (>= 17)
        for h in [17, 18, 21, 23]:
            dt = datetime.datetime(2026, 9, 25, h, 30)
            self.assertEqual(get_boot_greeting_type(dt), "evening")
            self.assertEqual(get_boot_greeting_text(dt), "Good evening. Systems online sir.")
            self.assertTrue(get_boot_audio_path(dt).endswith("boot_evening.mp3"))

    def test_shaka_activation_audio_paths(self):
        from src.core.voice import get_activation_audio_path
        act_path = get_activation_audio_path(True)
        self.assertTrue(act_path.endswith("control_activated.mp3"))

        deact_path = get_activation_audio_path(False)
        self.assertTrue(deact_path.endswith("control_deactivated.mp3"))

    def test_cached_audio_files_exist_and_non_empty(self):
        from src.core.voice import AUDIO_DIR, VOICE_PHRASES
        for filename in VOICE_PHRASES:
            file_path = os.path.join(AUDIO_DIR, filename)
            self.assertTrue(os.path.exists(file_path), f"Missing voice asset: {filename}")
            self.assertGreater(os.path.getsize(file_path), 5000, f"Asset too small: {filename}")

    def test_play_and_stop_audio_lifecycle(self):
        from src.core.voice import play_boot_greeting, stop_audio
        play_boot_greeting()
        time.sleep(0.05)
        stop_audio()

    def test_rapid_voice_interruption(self):
        from src.core.voice import play_gesture_toggle_voice, stop_audio
        play_gesture_toggle_voice(True)
        time.sleep(0.02)
        play_gesture_toggle_voice(False)
        time.sleep(0.02)
        play_gesture_toggle_voice(True)
        time.sleep(0.05)
        stop_audio()


class TestHudOverlayEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        import sys
        if QApplication.instance() is None:
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def test_120_fps_timers(self):
        from src.ui.hud_overlay import FullScreenJarvisBootOverlay, JarvisHudOverlay
        boot = FullScreenJarvisBootOverlay(play_audio=False)
        self.assertEqual(boot.anim_timer.interval(), 8)
        boot.anim_timer.stop()
        boot.close()

        hud = JarvisHudOverlay()
        self.assertEqual(hud.anim_timer.interval(), 8)
        hud.anim_timer.stop()
        hud.close()

    def test_popup_lasts_full_voice_duration(self):
        from src.ui.hud_overlay import JarvisHudOverlay
        hud = JarvisHudOverlay()
        hud.trigger_popup(is_active=True)
        self.assertGreaterEqual(hud.dismiss_timer.interval(), 3500)
        hud.anim_timer.stop()
        hud.close()

    def test_no_dashes_or_slashes_in_hud_status(self):
        from src.ui.hud_overlay import JarvisHudOverlay
        hud = JarvisHudOverlay()
        for active in [True, False]:
            hud.trigger_popup(is_active=active)
            for text in [hud.status_title, hud.status_subtitle, hud.status_badge]:
                self.assertNotIn("-", text, f"Dash found in text: {text}")
                self.assertNotIn("/", text, f"Slash found in text: {text}")
        hud.anim_timer.stop()
        hud.close()

    def test_boot_sequence_extended_duration(self):
        from src.ui.hud_overlay import FullScreenJarvisBootOverlay
        boot = FullScreenJarvisBootOverlay(play_audio=False)
        now = time.perf_counter()
        boot.start_time = now - 5.0
        boot._on_tick()
        self.assertFalse(boot.is_closing)

        boot.start_time = now - 8.1
        boot._on_tick()
        self.assertTrue(boot.is_closing)
        boot.anim_timer.stop()
        boot.close()

    def test_source_code_cleanliness(self):
        from src.core.voice import PROJECT_ROOT

        # 1. Verify no Japanese characters exist anywhere in src/
        japanese_pattern = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]")
        src_dir = os.path.join(PROJECT_ROOT, "src")
        for root, _, files in os.walk(src_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        code = f.read()
                    self.assertFalse(
                        bool(japanese_pattern.search(code)),
                        f"Japanese text found in {file}"
                    )

        # 2. Verify hud_overlay.py string literals contain zero dashes or slashes
        hud_path = os.path.join(PROJECT_ROOT, "src", "ui", "hud_overlay.py")
        with open(hud_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value
                if val in docstrings:
                    continue
                if val.startswith("__") and val.endswith("__"):
                    continue
                self.assertNotIn("-", val, f"Dash found in hud_overlay.py string: {val!r}")
                self.assertNotIn("/", val, f"Slash found in hud_overlay.py string: {val!r}")

        # 3. Verify tray.py menu action titles do not contain slashes
        tray_path = os.path.join(PROJECT_ROOT, "src", "ui", "tray.py")
        with open(tray_path, "r", encoding="utf-8") as f:
            tray_content = f.read()
        self.assertNotIn("PROJECT KONTROLL //", tray_content)
        self.assertNotIn("Auto-Compensate", tray_content)

        # 4. Verify debug_window.py does not contain // or CAMERA: -- FPS
        debug_path = os.path.join(PROJECT_ROOT, "src", "ui", "debug_window.py")
        with open(debug_path, "r", encoding="utf-8") as f:
            debug_content = f.read()
        self.assertNotIn("Project Kontroll //", debug_content)
        self.assertNotIn("CAMERA: -- FPS", debug_content)


class TestDeepRobustnessAndEdgeCases(unittest.TestCase):
    def test_optical_flow_stillness_in_gesture_engine(self):
        """
        Verify that when optical_flow_delta is (0.0, 0.0), GestureEngine maintains
        laser-mouse stillness and does NOT fall back to noisy MediaPipe landmark jitter.
        """
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        lm_base = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm_base[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        lm_base[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)
        lm_base[5] = SimpleNamespace(x=0.42, y=0.52, z=0.0)
        lm_base[17] = SimpleNamespace(x=0.58, y=0.52, z=0.0)
        lm_base[4] = SimpleNamespace(x=0.38, y=0.52, z=0.0)
        lm_base[8] = SimpleNamespace(x=0.40, y=0.35, z=0.0)
        # Curled middle, ring, pinky -> pointing pose
        lm_base[12] = SimpleNamespace(x=0.50, y=0.58, z=0.0)
        lm_base[16] = SimpleNamespace(x=0.54, y=0.60, z=0.0)
        lm_base[20] = SimpleNamespace(x=0.58, y=0.62, z=0.0)

        # Initial frame
        res1 = engine.process(lm_base, timestamp=1.0, optical_flow_delta=(0.0, 0.0))
        x1, y1 = res1["cursor_x"], res1["cursor_y"]

        # Second frame: Raw MediaPipe landmarks jitter significantly (e.g. 15 px noise)
        import copy
        lm_jitter = copy.deepcopy(lm_base)
        lm_jitter[8].x += 0.015
        lm_jitter[8].y -= 0.015

        # Optical flow accurately reports physical hand stillness (0.0, 0.0)
        res2 = engine.process(lm_jitter, timestamp=1.033, optical_flow_delta=(0.0, 0.0))
        x2, y2 = res2["cursor_x"], res2["cursor_y"]

        # Cursor MUST remain identically stationary
        self.assertEqual(x2, x1, "Cursor moved despite optical flow stillness guarantee")
        self.assertEqual(y2, y1, "Cursor moved despite optical flow stillness guarantee")

    def test_optical_flow_multi_frame_translation_with_outlier_rejection(self):
        """
        Verify that over 40 frames of synthetic translation, SubPixelOpticalFlowTracker
        maintains sub-pixel precision with zero outlier spikes and zero drift.
        """
        tracker = SubPixelOpticalFlowTracker()
        h, w = 720, 1280
        base = np.zeros((h, w), dtype=np.uint8)
        for i in range(20, 700, 15):
            for j in range(20, 1200, 15):
                base[i:i+5, j:j+5] = 200

        curr_x, curr_y = 600.0, 360.0
        tracker.update(base, (curr_x, curr_y), timestamp=0.0)

        for t in range(1, 40):
            curr_x += 2.0
            curr_y += 1.0
            M = np.float32([[1, 0, 2.0*t], [0, 1, 1.0*t]])
            f = cv2.warpAffine(base, M, (w, h))
            dx, dy, fx, fy = tracker.update(f, (curr_x, curr_y), timestamp=t*0.016)
            self.assertAlmostEqual(dx, 2.0, delta=0.5, msg=f"Frame {t} dx spiked to {dx}")
            self.assertAlmostEqual(dy, 1.0, delta=0.5, msg=f"Frame {t} dy spiked to {dy}")

    def test_viscous_aim_assist_approach_damping(self):
        """
        Verify that when approaching a button outside its bounds, apply_magnetic_lock
        dampens velocity smoothly rather than hard-teleporting to target center,
        and firmly locks to center on click intent.
        """
        mgr = TargetLockManager(capture_radius=42.0, breakout_velocity=750.0, bubble_radius=35.0, max_damping=0.65)
        mgr._override_target = {
            "role": ROLE_SYSTEM_PUSHBUTTON,
            "role_name": "CLOSE [X]",
            "rect": (1300, 50, 46, 32),
            "center": (1323.0, 66.0),
        }

        # Initialize position 30px to the left of the button
        mgr.last_output_pos = (1270.0, 66.0)

        # Approach position: 1285.0 (15px step towards button, 15px from button left edge)
        raw_x, raw_y = 1285.0, 66.0
        sx, sy, is_locked, name = mgr.apply_magnetic_lock(raw_x, raw_y, velocity=50.0, timestamp=1.0, is_clicking=False)

        self.assertTrue(is_locked)
        self.assertEqual(name, "CLOSE [X]")
        # Must NOT hard-teleport to center (1323)
        self.assertNotEqual(sx, 1323)
        # Must have decelerated step towards button
        self.assertGreater(sx, 1270.0)
        self.assertLess(sx, 1285.0)

        # Active click intent firmly locks to target center
        sx_click, sy_click, is_locked_click, _ = mgr.apply_magnetic_lock(
            raw_x, raw_y, velocity=50.0, timestamp=1.05, is_clicking=True
        )
        self.assertTrue(is_locked_click)
        self.assertEqual(sx_click, 1323)
        self.assertEqual(sy_click, 66)

    def test_left_right_click_mutual_exclusion(self):
        """
        Verify that Middle-Thumb Right Click and Closed-Fist Left Click are mutually exclusive
        and neither can corrupt the other's action state.
        """
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        # Create mock landmark setup
        lm = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        lm[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)
        lm[5] = SimpleNamespace(x=0.42, y=0.52, z=0.0)
        lm[17] = SimpleNamespace(x=0.58, y=0.52, z=0.0)

        # Right click: Middle touches thumb, index is not touching thumb
        lm[4] = SimpleNamespace(x=0.46, y=0.50, z=0.0)   # Thumb
        lm[12] = SimpleNamespace(x=0.465, y=0.50, z=0.0) # Middle (touching thumb)
        lm[8] = SimpleNamespace(x=0.40, y=0.35, z=0.0)   # Index extended
        lm[16] = SimpleNamespace(x=0.54, y=0.60, z=0.0)  # Ring curled
        lm[20] = SimpleNamespace(x=0.58, y=0.62, z=0.0)  # Pinky curled

        r1 = engine.process(lm, timestamp=1.0)
        self.assertEqual(r1["action"], "RIGHT_CONTACT")
        self.assertEqual(engine.tap_state, "UP")

        # Release middle finger
        lm[12].x = 0.50
        lm[12].y = 0.35
        r2 = engine.process(lm, timestamp=1.12)
        self.assertEqual(r2["action"], "RIGHT_CLICK")
        self.assertEqual(engine.tap_state, "UP")

    def test_relative_tracking_hand_reentry_preserves_position(self):
        """
        In Relative Mode, when the hand leaves the frame and re-enters at a different location,
        the cursor must remain where the user left it and NOT jump to absolute coordinates.
        """
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        engine.set_tracking_mode("relative")

        lm1 = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm1[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        lm1[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)
        lm1[5] = SimpleNamespace(x=0.42, y=0.52, z=0.0)
        lm1[17] = SimpleNamespace(x=0.58, y=0.52, z=0.0)
        lm1[8] = SimpleNamespace(x=0.40, y=0.35, z=0.0)
        lm1[4] = SimpleNamespace(x=0.38, y=0.52, z=0.0)
        lm1[12] = SimpleNamespace(x=0.50, y=0.58, z=0.0)
        lm1[16] = SimpleNamespace(x=0.54, y=0.60, z=0.0)
        lm1[20] = SimpleNamespace(x=0.58, y=0.62, z=0.0)

        # Frame 1: Establish position
        res1 = engine.process(lm1, timestamp=1.0)
        # Move slightly
        res2 = engine.process(lm1, timestamp=1.016, optical_flow_delta=(5.0, 2.0))
        # Let filter settle onto stationary cursor
        for step in range(1, 6):
            res2 = engine.process(lm1, timestamp=1.016 + step * 0.016, optical_flow_delta=(0.0, 0.0))
        saved_x = res2["cursor_x"]
        saved_y = res2["cursor_y"]

        # Hand leaves view
        engine.reset_hand_state()

        # Hand re-enters at a completely different position in camera space
        lm2 = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm2[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        lm2[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)
        lm2[5] = SimpleNamespace(x=0.42, y=0.52, z=0.0)
        lm2[17] = SimpleNamespace(x=0.58, y=0.52, z=0.0)
        lm2[8] = SimpleNamespace(x=0.85, y=0.20, z=0.0)  # Far corner!
        lm2[4] = SimpleNamespace(x=0.80, y=0.30, z=0.0)
        lm2[12] = SimpleNamespace(x=0.50, y=0.58, z=0.0)
        lm2[16] = SimpleNamespace(x=0.54, y=0.60, z=0.0)
        lm2[20] = SimpleNamespace(x=0.58, y=0.62, z=0.0)

        res3 = engine.process(lm2, timestamp=2.0)
        # The cursor must NOT jump across the screen on re-entry!
        self.assertAlmostEqual(res3["cursor_x"], saved_x, delta=5.0)
        self.assertAlmostEqual(res3["cursor_y"], saved_y, delta=5.0)

    def test_tray_tooltips_reference_shaka_sign(self):
        """Verify tray tooltips accurately reference Shaka Sign and not Super Gesture."""
        tray_path = os.path.join(PROJECT_ROOT, "src", "ui", "tray.py")
        with open(tray_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Shaka Sign", content)
        self.assertNotIn("Super Gesture 👌 to activate", content)


class TestSessionLockDetection(unittest.TestCase):
    def test_session_lock_detection_functions(self):
        """Verifies session lock detector APIs run cleanly without exceptions."""
        from src.service.session import is_workstation_unlocked, is_logonui_active
        unlocked = is_workstation_unlocked()
        logonui = is_logonui_active()
        self.assertIsInstance(unlocked, bool)
        self.assertIsInstance(logonui, bool)

    def test_default_standby_tray_state(self):
        """Verifies SystemTrayManager and icon pixmap default to Standby."""
        from src.ui.tray import create_tray_icon_pixmap, SystemTrayManager
        pm = create_tray_icon_pixmap(is_active=False)
        self.assertFalse(pm.isNull())

        # Test tray manager initialization defaults
        tray = SystemTrayManager(
            on_toggle_active=lambda: None,
            on_open_calibration=lambda: None,
            on_exit=lambda: None,
            initial_active=False,
        )
        self.assertFalse(tray.is_active)
        self.assertIn("Standby", tray.status_action.text())
class TestGodTierPrecisionAndFixes(unittest.TestCase):
    def test_camera_tilt_never_inverts_x_axis(self):
        """Verifies that DeskHomography tilt estimation never inverts the X axis."""
        homography = DeskHomography(mode="auto")
        lm = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)    # Wrist
        lm[5] = SimpleNamespace(x=0.45, y=0.48, z=-0.05) # Index MCP (palm facing camera)
        lm[17] = SimpleNamespace(x=0.55, y=0.52, z=0.02) # Pinky MCP

        tilt = homography.estimate_camera_tilt(lm)
        self.assertGreaterEqual(tilt, -35.0)
        self.assertLessEqual(tilt, 35.0)

        H = homography.get_homography_matrix(landmarks=lm)
        # H[0, 0] must be strictly positive (never inverting horizontal tracking)
        self.assertGreater(H[0, 0], 0.70)

        # Rightward physical vector must remain rightward on desk
        dx_desk, dy_desk = homography.transform_vector(100.0, 0.0, landmarks=lm)
        self.assertGreater(dx_desk, 50.0)

    def test_pointing_pose_zero_ghost_right_click(self):
        """Verifies pointing hand posture with curled middle finger does NOT trigger ghost right clicks."""
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        # Natural pointing hand: Index extended, Middle curled into palm near thumb
        lm = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        lm[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)
        lm[5] = SimpleNamespace(x=0.42, y=0.52, z=0.0)
        lm[17] = SimpleNamespace(x=0.58, y=0.52, z=0.0)
        lm[4] = SimpleNamespace(x=0.40, y=0.52, z=0.0)   # Thumb
        lm[8] = SimpleNamespace(x=0.40, y=0.32, z=0.0)   # Index extended pointing
        lm[6] = SimpleNamespace(x=0.40, y=0.42, z=0.0)
        # Middle finger curled in palm resting near thumb
        lm[10] = SimpleNamespace(x=0.48, y=0.55, z=0.0)
        lm[12] = SimpleNamespace(x=0.44, y=0.56, z=0.0)  # Near thumb
        lm[16] = SimpleNamespace(x=0.54, y=0.62, z=0.0)
        lm[20] = SimpleNamespace(x=0.58, y=0.64, z=0.0)

        for t in [1.0, 1.1, 1.2, 1.3, 1.4]:
            res = engine.process(lm, timestamp=t)
            self.assertEqual(res["action"], "MOVE")
            self.assertNotEqual(res["action"], "RIGHT_CONTACT")
            self.assertNotEqual(res["action"], "RIGHT_CLICK")

    def test_two_finger_pinch_right_click(self):
        """Verifies two finger pinch (Index and Middle touch Thumb) triggers orthogonal Right Click."""
        engine = GestureEngine(screen_width=1920, screen_height=1080, initial_active=True)
        lm = [SimpleNamespace(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lm[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
        lm[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)
        lm[5] = SimpleNamespace(x=0.42, y=0.52, z=0.0)
        lm[17] = SimpleNamespace(x=0.58, y=0.52, z=0.0)
        lm[4] = SimpleNamespace(x=0.42, y=0.50, z=0.0)   # Thumb
        lm[8] = SimpleNamespace(x=0.425, y=0.50, z=0.0)  # Index touching thumb
        lm[12] = SimpleNamespace(x=0.425, y=0.50, z=0.0) # Middle touching thumb
        lm[10] = SimpleNamespace(x=0.46, y=0.48, z=0.0)  # Middle PIP
        lm[14] = SimpleNamespace(x=0.54, y=0.58, z=0.0)  # Ring PIP
        lm[16] = SimpleNamespace(x=0.54, y=0.62, z=0.0)  # Ring curled
        lm[18] = SimpleNamespace(x=0.58, y=0.60, z=0.0)  # Pinky PIP
        lm[20] = SimpleNamespace(x=0.58, y=0.64, z=0.0)  # Pinky curled

        res_contact = engine.process(lm, timestamp=1.0)
        self.assertEqual(res_contact["action"], "RIGHT_CONTACT")

        # Open back up to release click
        lm[8] = SimpleNamespace(x=0.40, y=0.35, z=0.0)
        lm[12] = SimpleNamespace(x=0.50, y=0.35, z=0.0)
        res_release = engine.process(lm, timestamp=1.12)
        self.assertEqual(res_release["action"], "RIGHT_CLICK")

    def test_fast_swipe_optical_flow_fallback(self):
        """Verifies that when optical flow features are lost on a fast swipe, landmark delta is used."""
        tracker = SubPixelOpticalFlowTracker(roi_size=48)
        frame1 = np.zeros((480, 640), dtype=np.uint8)
        cv2.circle(frame1, (300, 240), 20, 255, -1)

        tracker.update(frame1, (300.0, 240.0), has_hand=True, timestamp=1.0)

        # Frame 2: fast hand swipe moves 40 pixels in camera frame (too fast for 48x48 LK ROI)
        frame2 = np.zeros((480, 640), dtype=np.uint8)
        cv2.circle(frame2, (340, 240), 20, 255, -1)

        dx, dy, x, y = tracker.update(frame2, (340.0, 240.0), has_hand=True, timestamp=1.033)
        self.assertAlmostEqual(dx, 40.0, delta=2.0)
        self.assertFalse(tracker.is_still)


if __name__ == "__main__":
    unittest.main()
