"""
Real-time Camera Calibration & Diagnostic Visualizer for Project Kontroll.
Displays live tracking skeleton, ergonomic comfort bounds, angle-invariant tap metrics,
detected camera tilt angle, and camera mounting selector.
"""

from typing import Optional
import cv2
import numpy as np

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QProgressBar, QComboBox


class DebugWindow(QWidget):
    """
    Diagnostic & Calibration Window accessible from the System Tray.
    """

    def __init__(self, tracker, gesture_engine):
        super().__init__()
        self.tracker = tracker
        self.gesture_engine = gesture_engine

        self.setWindowTitle("Project Kontroll // Diagnostic & Calibration HUD")
        self.resize(760, 680)
        self.setStyleSheet("""
            QWidget {
                background-color: #0b0f19;
                color: #e0f0ff;
                font-family: 'Segoe UI', Consolas, sans-serif;
            }
            QLabel {
                font-size: 12px;
            }
            QComboBox {
                background-color: #101a2e;
                color: #00f0ff;
                border: 1px solid #1a365d;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QProgressBar {
                border: 1px solid #1a365d;
                border-radius: 4px;
                background-color: #060911;
                text-align: center;
                color: #00f0ff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052cc, stop:1 #00f0ff);
            }
            QPushButton {
                background-color: #102a45;
                color: #00f0ff;
                border: 1px solid #00f0ff;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00f0ff;
                color: #0b0f19;
            }
        """)

        layout = QVBoxLayout(self)

        # Video Viewport
        self.video_label = QLabel("Initializing Video Feed...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(640, 440)
        self.video_label.setStyleSheet("border: 2px solid #142845; border-radius: 8px; background-color: #04060a;")
        layout.addWidget(self.video_label)

        # Controls Row: Camera Mount / Tilt Mode Selector
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Webcam Mount:"))
        self.mount_combo = QComboBox()
        self.mount_combo.addItems([
            "Auto-Compensate Angle (Recommended)",
            "Left Monitor (Tilted ~35°)",
            "Center Monitor (0° Straight)",
            "Right Monitor (Tilted ~35°)"
        ])
        modes = ["auto", "left", "center", "right"]
        if self.gesture_engine.mount_mode in modes:
            self.mount_combo.setCurrentIndex(modes.index(self.gesture_engine.mount_mode))
        self.mount_combo.currentIndexChanged.connect(self._on_mount_changed)
        ctrl_layout.addWidget(self.mount_combo)

        self.tilt_label = QLabel("TILT: 0.0°")
        self.tilt_label.setStyleSheet("color: #00f0ff; font-weight: bold; padding-left: 10px;")
        ctrl_layout.addWidget(self.tilt_label)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Telemetry Row 1: Metrics
        telemetry_layout = QHBoxLayout()
        self.fps_label = QLabel("CAMERA: -- FPS")
        self.status_label = QLabel("STATUS: ACTIVE")
        self.status_label.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.shaka_label = QLabel("SHAKA: OFF 🤙")
        self.shaka_label.setStyleSheet("color: #718096;")
        self.super_label = QLabel("DRAG POSE: OFF")
        self.super_label.setStyleSheet("color: #718096;")
        self.lock_label = QLabel("TARGET: FREE")
        self.lock_label.setStyleSheet("color: #718096; font-weight: bold;")

        telemetry_layout.addWidget(self.fps_label)
        telemetry_layout.addWidget(self.status_label)
        telemetry_layout.addWidget(self.shaka_label)
        telemetry_layout.addWidget(self.super_label)
        telemetry_layout.addWidget(self.lock_label)
        layout.addLayout(telemetry_layout)

        # Telemetry Row 2: Tap Ratio Bar & Action Status
        bar_layout = QHBoxLayout()
        bar_layout.addWidget(QLabel("Local Tap Ratio:"))
        self.tap_bar = QProgressBar()
        self.tap_bar.setRange(0, 100)
        self.tap_bar.setValue(100)
        bar_layout.addWidget(self.tap_bar)

        self.action_label = QLabel("ACTION: MOVE")
        self.action_label.setStyleSheet("color: #00f0ff; font-weight: bold; padding-left: 10px;")
        bar_layout.addWidget(self.action_label)
        layout.addLayout(bar_layout)

        # Refresh Timer (30 FPS GUI update)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_frame)
        self.timer.start(33)

    def _on_mount_changed(self, idx: int):
        modes = ["auto", "left", "center", "right"]
        if 0 <= idx < len(modes):
            self.gesture_engine.mount_mode = modes[idx]

    def _refresh_frame(self):
        if not self.isVisible():
            return

        landmarks, frame, ts, has_hand, fps = self.tracker.get_latest_data()
        self.fps_label.setText(f"CAMERA: {fps:.1f} FPS")

        is_active = self.gesture_engine.is_active
        self.status_label.setText("STATUS: ONLINE" if is_active else "STATUS: STANDBY")
        self.status_label.setStyleSheet("color: #00f0ff; font-weight: bold;" if is_active else "color: #ffaa00; font-weight: bold;")

        # Update tilt telemetry
        tilt = getattr(self.gesture_engine, "detected_tilt_angle", 0.0)
        if abs(tilt) > 15:
            direction = "LEFT" if tilt > 0 else "RIGHT"
            self.tilt_label.setText(f"TILT: {direction} ({abs(tilt):.1f}°)")
        else:
            self.tilt_label.setText(f"TILT: CENTER ({abs(tilt):.1f}°)")

        # Update Target Lock
        if getattr(self.gesture_engine, "last_is_locked", False):
            desc = getattr(self.gesture_engine, "last_target_desc", "TARGET") or "TARGET"
            self.lock_label.setText(f"TARGET: LOCKED [{desc}] 🧲")
            self.lock_label.setStyleSheet("color: #00f0ff; font-weight: bold;")
        else:
            self.lock_label.setText("TARGET: FREE")
            self.lock_label.setStyleSheet("color: #718096; font-weight: bold;")

        # Action Label & Telemetry
        if not has_hand or landmarks is None:
            self.action_label.setText("NO HAND")
            self.action_label.setStyleSheet("color: #718096; font-style: italic; padding-left: 10px;")
            self.tap_bar.setValue(0)
            self.shaka_label.setText("SHAKA: OFF")
            self.shaka_label.setStyleSheet("color: #718096;")
            self.super_label.setText("DRAG POSE: OFF")
            self.super_label.setStyleSheet("color: #718096;")
            self.lock_label.setText("TARGET: FREE")
            self.lock_label.setStyleSheet("color: #718096; font-weight: bold;")
        else:
            is_shaka = self.gesture_engine.is_shaka_gesture(landmarks)
            is_dragging = getattr(self.gesture_engine, "is_dragging", False)
            tap_state = getattr(self.gesture_engine, "tap_state", "UP")
            right_state = getattr(self.gesture_engine, "right_click_state", "UP")

            if is_shaka:
                self.shaka_label.setText("SHAKA: ACTIVE 🤙")
                self.shaka_label.setStyleSheet("color: #00f0ff; font-weight: bold;")
                self.action_label.setText("ACTION: SHAKA TOGGLE 🤙")
                self.action_label.setStyleSheet("color: #00f0ff; font-weight: bold; padding-left: 10px;")
            else:
                self.shaka_label.setText("SHAKA: OFF")
                self.shaka_label.setStyleSheet("color: #718096;")

                if is_dragging:
                    self.action_label.setText("ACTION: DRAGGING (👌)")
                    self.action_label.setStyleSheet("color: #ffaa00; font-weight: bold; padding-left: 10px;")
                elif tap_state == "DOWN":
                    self.action_label.setText("ACTION: LEFT CLICK CONTACT ⚡")
                    self.action_label.setStyleSheet("color: #00ffaa; font-weight: bold; padding-left: 10px;")
                elif right_state == "DOWN":
                    self.action_label.setText("ACTION: RIGHT CLICK CONTACT ⚡")
                    self.action_label.setStyleSheet("color: #00e0ff; font-weight: bold; padding-left: 10px;")
                else:
                    self.action_label.setText("ACTION: MOVE")
                    self.action_label.setStyleSheet("color: #00f0ff; font-weight: bold; padding-left: 10px;")

        if frame is None:
            return

        # Mirror video preview so it acts naturally like a selfie / looking glass
        display_frame = cv2.flip(frame, 1)
        h, w, _ = display_frame.shape

        # Draw Ergonomic Comfort Zone (Yellow box) in mirrored frame space
        bx1 = int((1.0 - self.gesture_engine.box_xmax) * w)
        bx2 = int((1.0 - self.gesture_engine.box_xmin) * w)
        by1 = int(self.gesture_engine.box_ymin * h)
        by2 = int(self.gesture_engine.box_ymax * h)
        cv2.rectangle(display_frame, (bx1, by1), (bx2, by2), (255, 240, 0), 2)
        cv2.putText(display_frame, "ERGONOMIC COMFORT ZONE (REST ELBOW ON DESK)", (bx1 + 5, by1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 240, 0), 1)

        # Draw Landmarks if present
        if landmarks:
            connections = [
                (0, 1), (1, 2), (2, 3), (3, 4),
                (0, 5), (5, 6), (6, 7), (7, 8),
                (0, 9), (9, 10), (10, 11), (11, 12),
                (0, 13), (13, 14), (14, 15), (15, 16),
                (0, 17), (17, 18), (18, 19), (19, 20),
                (5, 9), (9, 13), (13, 17)
            ]

            points = []
            for lm in landmarks:
                px = int((1.0 - lm.x) * w)
                py = int(lm.y * h)
                points.append((px, py))

            for p1, p2 in connections:
                cv2.line(display_frame, points[p1], points[p2], (180, 120, 40), 1)

            for idx, pt in enumerate(points):
                color = (0, 255, 255) if idx in (4, 8, 12, 20) else (100, 200, 255)
                cv2.circle(display_frame, pt, 3 if idx not in (4, 8, 12, 20) else 6, color, -1)

            # Thumb (4), Index (8), Middle (12) tracking lines
            p4 = points[4]
            p8 = points[8]
            p12 = points[12]
            # Cyan line between Thumb and Index (Left Click / Drag)
            cv2.line(display_frame, p4, p8, (255, 240, 0), 2)
            # Green line between Index and Middle (Right Click)
            cv2.line(display_frame, p8, p12, (0, 255, 0), 1)

            # Compute Metric
            scale = self.gesture_engine._get_hand_scale(landmarks)
            tap_ratio, _ = self.gesture_engine.compute_tap_metric(landmarks, scale)

            # Update tap progress bar (reaches 100% on contact)
            pct = max(0, min(100, int(((0.45 - tap_ratio) / (0.45 - 0.25)) * 100)))
            self.tap_bar.setValue(pct)

            # Drag pose status
            is_super = self.gesture_engine.is_super_gesture(landmarks)
            if is_super:
                self.super_label.setText("DRAG POSE: ACTIVE 👌")
                self.super_label.setStyleSheet("color: #00f0ff; font-weight: bold;")
            else:
                self.super_label.setText("DRAG POSE: OFF")
                self.super_label.setStyleSheet("color: #718096;")

        # Convert to QPixmap
        display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        bytes_per_line = 3 * w
        q_img = QImage(display_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        self.video_label.setPixmap(pixmap.scaled(
            self.video_label.width(), self.video_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
