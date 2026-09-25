"""
Project Kontroll: Jarvis-Grade Virtual AR Gesture Mouse & OS Controller.
Main Application Orchestrator & 120 Hz Background Extrapolator.
"""

import sys
import os
import argparse
import time
import math

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt

from src.core.tracker import HandTracker
from src.core.gestures import GestureEngine
from src.core.input_simulator import MouseSimulator
from src.ui.hud_overlay import JarvisHudOverlay
from src.ui.debug_window import DebugWindow
from src.ui.tray import SystemTrayManager
from src.service.session import is_workstation_unlocked


class KontrollApp:
    def __init__(self, show_debug: bool = False, is_autostart_launch: bool = False, is_boot_launch: bool = False):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 1. Initialize Mouse Simulator
        self.mouse = MouseSimulator()

        # 2. Initialize HUD Overlay (Transparent, Click-Through)
        self.hud = JarvisHudOverlay()

        # 3. Initialize Gesture Engine (5 Core Pillars - defaults to Standby)
        self.gestures = GestureEngine(
            screen_width=self.mouse.screen_width,
            screen_height=self.mouse.screen_height,
            on_state_change=self._on_gesture_state_toggled,
            initial_active=False,
        )

        # 4. Initialize Hand Tracker (Threaded Camera + MediaPipe + Sub-Pixel Optical Flow)
        self.tracker = HandTracker(camera_index=0, width=640, height=480, target_fps=60)
        self.tracker.start()

        # 5. Initialize Diagnostic & Calibration Window
        self.debug_window = DebugWindow(self.tracker, self.gestures)
        if show_debug:
            self.debug_window.show()

        # 6. Initialize System Tray (reflects Standby by default)
        self.tray = SystemTrayManager(
            on_toggle_active=self._toggle_active_manual,
            on_open_calibration=self._open_calibration,
            on_exit=self.shutdown,
            on_mount_mode_change=self._set_mount_mode,
            on_tracking_mode_change=self._set_tracking_mode,
            on_replay_boot=self._replay_boot_sequence,
            initial_active=self.gestures.is_active,
        )

        # 7. 120 Hz Motion Extrapolator & High-Rate Loop (8ms = ~125 Hz)
        self.last_frame_timestamp = 0.0
        self.current_cursor_x = float(self.mouse.screen_width // 2)
        self.current_cursor_y = float(self.mouse.screen_height // 2)
        self.target_cursor_x = float(self.mouse.screen_width // 2)
        self.target_cursor_y = float(self.mouse.screen_height // 2)
        self.vel_x = 0.0
        self.vel_y = 0.0
        self.last_tick_time = time.perf_counter()

        self.loop_timer = QTimer()
        self.loop_timer.timeout.connect(self._process_frame_tick)
        self.loop_timer.start(8)  # 120 Hz

        # Initial Jarvis Boot Sequence HUD (post-login verification)
        if is_boot_launch:
            QTimer.singleShot(100, lambda: self.hud.trigger_boot_sequence())
        else:
            self._schedule_boot_after_login(is_autostart=is_autostart_launch)

    def _schedule_boot_after_login(self, is_autostart: bool):
        """
        Ensures the Jarvis dynamic boot sequence only executes AFTER the user enters their password
        and reaches their interactive unlocked desktop.
        """
        # If launched manually and workstation is already unlocked, start after short 350ms delay
        if not is_autostart and is_workstation_unlocked():
            QTimer.singleShot(350, lambda: self.hud.trigger_boot_sequence())
            return

        # On autostart / system boot or if workstation is currently locked:
        # Poll workstation unlock status every 300ms until user logs in.
        self._login_check_timer = QTimer()
        self._login_check_timer.setInterval(300)

        def _check_unlocked():
            if is_workstation_unlocked():
                self._login_check_timer.stop()
                # User has entered password and desktop is active.
                # Allow an 800ms buffer for desktop shell to paint, then fire boot sequence!
                QTimer.singleShot(800, lambda: self.hud.trigger_boot_sequence())

        self._login_check_timer.timeout.connect(_check_unlocked)
        self._login_check_timer.start()

    def _set_mount_mode(self, mode: str):
        self.gestures.mount_mode = mode

    def _set_tracking_mode(self, mode: str):
        self.gestures.set_tracking_mode(mode)

    def _replay_boot_sequence(self):
        self.hud.trigger_boot_sequence()

    def _on_gesture_state_toggled(self, is_active: bool):
        self.hud.trigger_popup(is_active)
        self.tray.update_state(is_active)

    def _toggle_active_manual(self):
        self.gestures.is_active = not self.gestures.is_active
        is_active = self.gestures.is_active
        self.hud.trigger_popup(is_active)
        self.tray.update_state(is_active)

    def _open_calibration(self):
        self.debug_window.show()
        self.debug_window.raise_()
        self.debug_window.activateWindow()

    def _process_frame_tick(self):
        """120 Hz High-Rate Tick: processes new camera frames and dispatches hardware mouse events."""
        now = time.perf_counter()
        dt = max(1e-4, min(0.04, now - self.last_tick_time))
        self.last_tick_time = now

        landmarks, _, timestamp, has_hand, _ = self.tracker.get_latest_data()

        if not has_hand or landmarks is None:
            if self.mouse.is_dragging:
                self.mouse.left_up()
            self.gestures.reset_hand_state()
            self.vel_x = 0.0
            self.vel_y = 0.0
            return

        # New Camera Frame Arrived
        if timestamp > self.last_frame_timestamp:
            self.last_frame_timestamp = timestamp

            # Process Dual-Engine Pipeline: Optical Flow delta + Global landmarks
            flow_delta = self.tracker.get_optical_flow_delta()
            result = self.gestures.process(
                landmarks, timestamp=timestamp, optical_flow_delta=flow_delta
            )

            if result.get("active"):
                action = result.get("action", "MOVE")
                target_x = float(result.get("cursor_x", self.target_cursor_x))
                target_y = float(result.get("cursor_y", self.target_cursor_y))

                self.current_cursor_x = target_x
                self.current_cursor_y = target_y

                # Direct zero-lag hardware dispatch
                self.mouse.move_to(int(round(target_x)), int(round(target_y)))

                # Handle actions
                if action == "CLICK":
                    self.mouse.click()
                elif action == "DOUBLE_CLICK":
                    self.mouse.double_click()
                elif action == "RIGHT_CLICK":
                    self.mouse.right_click()
                elif action == "DRAG_START":
                    self.mouse.drag_start()
                elif action == "DRAG_RELEASE":
                    self.mouse.left_up()

    def run(self):
        return self.app.exec()

    def shutdown(self):
        if hasattr(self, "_login_check_timer") and self._login_check_timer.isActive():
            self._login_check_timer.stop()
        if self.mouse.is_dragging:
            self.mouse.left_up()
        from src.core.voice import stop_audio
        stop_audio()
        self.tracker.stop()
        self.app.quit()


def main():
    parser = argparse.ArgumentParser(description="Project Kontroll: Jarvis AR Gesture Mouse")
    parser.add_argument("--debug", "--calibrate", action="store_true", help="Launch directly into calibration view")
    parser.add_argument("--autostart", action="store_true", help="Indicates launch originated from Windows startup")
    parser.add_argument("--boot", action="store_true", help="Launch directly into full-screen dynamic Jarvis boot sequence")
    args = parser.parse_args()

    app = KontrollApp(show_debug=args.debug, is_autostart_launch=args.autostart, is_boot_launch=args.boot)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
