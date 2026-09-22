"""
Real-time Camera Calibration & Diagnostic Visualizer for Project Kontroll.
Displays live tracking skeleton, active virtual mousepad bounds, tap distance metrics, and FPS.
"""

from typing import Optional
import cv2
import numpy as np

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QProgressBar


class DebugWindow(QWidget):
    """
    Diagnostic & Calibration Window accessible from the System Tray.
    """

    def __init__(self, tracker, gesture_engine):
        super().__init__()
        self.tracker = tracker
        self.gesture_engine = gesture_engine

        self.setWindowTitle("Project Kontroll // Diagnostic & Calibration HUD")
        self.resize(720, 620)
        self.setStyleSheet("""
            QWidget {
                background-color: #0b0f19;
                color: #e0f0ff;
                font-family: 'Segoe UI', Consolas, sans-serif;
            }
            QLabel {
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
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("border: 2px solid #142845; border-radius: 8px; background-color: #04060a;")
        layout.addWidget(self.video_label)

        # Telemetry Row 1: Metrics
        telemetry_layout = QHBoxLayout()

        self.fps_label = QLabel("FPS: --")
        self.status_label = QLabel("STATUS: ACTIVE")
        self.status_label.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.super_label = QLabel("SUPER GESTURE: OFF")
        self.super_label.setStyleSheet("color: #718096;")

        telemetry_layout.addWidget(self.fps_label)
        telemetry_layout.addWidget(self.status_label)
        telemetry_layout.addWidget(self.super_label)
        layout.addLayout(telemetry_layout)

        # Telemetry Row 2: Tap Ratio Bar
        bar_layout = QHBoxLayout()
        bar_layout.addWidget(QLabel("Tap Ratio (Index->Middle):"))
        self.tap_bar = QProgressBar()
        self.tap_bar.setRange(0, 100)
        self.tap_bar.setValue(100)
        bar_layout.addWidget(self.tap_bar)
        layout.addLayout(bar_layout)

        # Refresh Timer (30 FPS GUI update)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_frame)
        self.timer.start(33)

    def _refresh_frame(self):
        if not self.isVisible():
            return

        landmarks, frame, ts, has_hand, fps = self.tracker.get_latest_data()
        self.fps_label.setText(f"CAMERA: {fps:.1f} FPS")

        is_active = self.gesture_engine.is_active
        self.status_label.setText("STATUS: ONLINE" if is_active else "STATUS: STANDBY")
        self.status_label.setStyleSheet("color: #00f0ff; font-weight: bold;" if is_active else "color: #ffaa00; font-weight: bold;")

        if frame is None:
            return

        # Create overlay canvas
        display_frame = frame.copy()
        h, w, _ = display_frame.shape

        # Draw Active Mousepad Box
        bx1 = int(self.gesture_engine.box_xmin * w)
        bx2 = int(self.gesture_engine.box_xmax * w)
        by1 = int(self.gesture_engine.box_ymin * h)
        by2 = int(self.gesture_engine.box_ymax * h)
        cv2.rectangle(display_frame, (bx1, by1), (bx2, by2), (255, 240, 0), 2)
        cv2.putText(display_frame, "ACTIVE VIRTUAL MOUSEPAD", (bx1 + 5, by1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 240, 0), 1)

        # Draw Landmarks if present
        if landmarks:
            # Draw skeletal lines for fingers
            connections = [
                (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
                (0, 5), (5, 6), (6, 7), (7, 8),        # Index
                (0, 9), (9, 10), (10, 11), (11, 12),   # Middle
                (0, 13), (13, 14), (14, 15), (15, 16), # Ring
                (0, 17), (17, 18), (18, 19), (19, 20), # Pinky
                (5, 9), (9, 13), (13, 17)              # Palm base
            ]

            points = []
            for lm in landmarks:
                px = int(lm.x * w)
                py = int(lm.y * h)
                points.append((px, py))

            for p1, p2 in connections:
                cv2.line(display_frame, points[p1], points[p2], (180, 120, 40), 1)

            for idx, pt in enumerate(points):
                color = (0, 255, 255) if idx in (8, 12) else (100, 200, 255)
                cv2.circle(display_frame, pt, 3 if idx not in (8, 12) else 6, color, -1)

            # Highlight Index & Middle tips
            p8 = points[8]
            p12 = points[12]
            cv2.line(display_frame, p8, p12, (0, 255, 0), 2)

            # Tap ratio calculation
            scale = self.gesture_engine._get_hand_scale(landmarks)
            dist = self.gesture_engine._dist_3d(landmarks[8], landmarks[12])
            ratio = dist / scale

            # Update tap progress bar (inverted: smaller distance -> fuller bar)
            pct = max(0, min(100, int((1.0 - (ratio / 0.6)) * 100)))
            self.tap_bar.setValue(pct)

            # Super gesture status
            is_super = self.gesture_engine.is_super_gesture(landmarks)
            if is_super:
                self.super_label.setText("SUPER GESTURE: DETECTED! 👌")
                self.super_label.setStyleSheet("color: #00f0ff; font-weight: bold;")
            else:
                self.super_label.setText("SUPER GESTURE: OFF")
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
