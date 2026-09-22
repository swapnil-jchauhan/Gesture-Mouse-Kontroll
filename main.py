"""
Project Kontroll: Jarvis-Grade Virtual AR Gesture Mouse & OS Controller.
Main Application Orchestrator & Background Service.
"""

import sys
import os
import argparse
import time

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


class KontrollApp:
    def __init__(self, show_debug: bool = False, is_autostart_launch: bool = False):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 1. Initialize Mouse Simulator
        self.mouse = MouseSimulator()

        # 2. Initialize HUD Overlay (Transparent, Click-Through)
        self.hud = JarvisHudOverlay()

        # 3. Initialize Gesture Engine
        self.gestures = GestureEngine(
            screen_width=self.mouse.screen_width,
            screen_height=self.mouse.screen_height,
            on_state_change=self._on_gesture_state_toggled,
        )

        # 4. Initialize Hand Tracker (Threaded Camera + MediaPipe)
        self.tracker = HandTracker(camera_index=0, width=640, height=480, target_fps=60)
        self.tracker.start()

        # 5. Initialize Diagnostic & Calibration Window
        self.debug_window = DebugWindow(self.tracker, self.gestures)
        if show_debug:
            self.debug_window.show()

        # 6. Initialize System Tray
        self.tray = SystemTrayManager(
            on_toggle_active=self._toggle_active_manual,
            on_open_calibration=self._open_calibration,
            on_exit=self.shutdown,
        )

        # 7. High-Rate Processing Loop (60 Hz Qt Timer)
        self.loop_timer = QTimer()
        self.loop_timer.timeout.connect(self._process_frame_tick)
        self.loop_timer.start(16)  # ~60 FPS

        # Initial Boot Greeting HUD
        if is_autostart_launch:
            # Let the desktop finish loading, then flash Jarvis HUD
            QTimer.singleShot(1500, lambda: self.hud.trigger_popup(True))
        else:
            QTimer.singleShot(400, lambda: self.hud.trigger_popup(True))

    def _on_gesture_state_toggled(self, is_active: bool):
        """Called automatically when the 'Super' gesture is detected."""
        self.hud.trigger_popup(is_active)
        self.tray.update_state(is_active)

    def _toggle_active_manual(self):
        """Called via tray context menu."""
        self.gestures.is_active = not self.gestures.is_active
        is_active = self.gestures.is_active
        self.hud.trigger_popup(is_active)
        self.tray.update_state(is_active)

    def _open_calibration(self):
        self.debug_window.show()
        self.debug_window.raise_()
        self.debug_window.activateWindow()

    def _process_frame_tick(self):
        """Core high-frequency tick executed on the main GUI thread."""
        landmarks, _, timestamp, has_hand, _ = self.tracker.get_latest_data()

        if not has_hand or landmarks is None:
            # If hand left the frame while dragging, release drag safely
            if self.mouse.is_dragging:
                self.mouse.left_up()
                self.gestures.tap_state = "UP"
            return

        # Process gestures through state machine & 1€ filter
        result = self.gestures.process(landmarks, timestamp=timestamp)

        # Handle 'Super' state toggle if just fired
        if result.get("toggled"):
            # Callback already invoked via on_state_change
            pass

        # If system is active, dispatch mouse hardware events
        if result.get("active"):
            action = result.get("action", "MOVE")
            cx = result.get("cursor_x", self.mouse.screen_width // 2)
            cy = result.get("cursor_y", self.mouse.screen_height // 2)

            # Move mouse cursor
            self.mouse.move_to(cx, cy)

            # Dispatch clicks & drags
            if action == "CLICK":
                self.mouse.click()
            elif action == "DRAG_START":
                self.mouse.left_down()
            elif action == "DRAG_RELEASE":
                self.mouse.left_up()

    def run(self):
        return self.app.exec()

    def shutdown(self):
        """Graceful shutdown of background threads and services."""
        if self.mouse.is_dragging:
            self.mouse.left_up()
        self.tracker.stop()
        self.app.quit()


def main():
    parser = argparse.ArgumentParser(description="Project Kontroll: Jarvis AR Gesture Mouse")
    parser.add_argument("--debug", "--calibrate", action="store_true", help="Launch directly into calibration view")
    parser.add_argument("--autostart", action="store_true", help="Indicates launch originated from Windows startup")
    args = parser.parse_args()

    app = KontrollApp(show_debug=args.debug, is_autostart_launch=args.autostart)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
