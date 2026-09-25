"""
Futuristic Jarvis Holographic HUD Overlay & Full-Screen Dynamic Boot Sequence.
Provides:
1. FullScreenJarvisBootOverlay: Full-screen cinematic holographic boot sequence
   matching the Jarvis HUD architecture with 3D rotating wireframe globe,
   parametric orbital rings, amber/cyan segmented reactor core, volumetric
   projector beam, floor ripples, telemetry cards, and audio waveform analysis.
2. JarvisHudOverlay: Compact runtime holographic notification banner for
   mode changes (Shaka gesture 🤙) and launcher for the boot sequence.
"""

import sys
import math
import time
import random
import threading
import ctypes
from typing import Optional, Callable, List

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QRadialGradient, QLinearGradient, QPainterPath
)
from PyQt6.QtWidgets import QWidget, QApplication

# Win32 click-through constants
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080


from src.core.voice import play_boot_greeting, play_gesture_toggle_voice, stop_audio


def play_jarvis_sound(is_active: bool):
    """Plays the RyanNeural British voice announcement for activation or standby."""
    play_gesture_toggle_voice(is_active)


def play_boot_chime(frequency: int = 0, duration_ms: int = 0):
    """No-op stub for backward compatibility without winsound beeps."""
    pass


def play_jarvis_boot_symphony():
    """Plays the RyanNeural British time-based greeting on boot."""
    play_boot_greeting()


class FullScreenJarvisBootOverlay(QWidget):
    """
    Cinematic Full-Screen Jarvis Holographic Boot Sequence.
    Renders multi-layered 3D holographic elements, telemetry cards, audio waveform,
    and volumetric projector beam matching the reference cyber-HUD interface.
    """

    def __init__(self, on_complete: Optional[Callable[[], None]] = None, play_audio: bool = True):
        super().__init__()
        self.on_complete = on_complete

        # Frameless, Always on top, Tool window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Cover entire screen
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            self.setGeometry(geom)
            self.w = geom.width()
            self.h = geom.height()
        else:
            self.w, self.h = 1920, 1080
            self.resize(self.w, self.h)

        # Animation parameters & state
        self.opacity = 0.0
        self.target_opacity = 1.0
        self.start_time = time.perf_counter()
        self.elapsed = 0.0
        self.is_closing = False

        # Rotation angles
        self.angle_outer = 0.0
        self.angle_inner = 0.0
        self.orbital_angle = 0.0
        self.globe_angle = 0.0
        self.pulse_phase = 0.0

        # Telemetry mock dynamic values
        self.audio_bars: List[float] = [0.1] * 14
        self.cpu_load = 3.0
        self.gpu_load = 14.0

        # 120 FPS animation timer (8ms)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._on_tick)
        self.anim_timer.start(8)

        # Audio sequence trigger
        if play_audio:
            play_jarvis_boot_symphony()

    def keyPressEvent(self, event):
        """Allow skipping boot sequence instantly with Esc, Space, or Enter."""
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space, Qt.Key.Key_Return):
            self._dismiss_immediately()
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Clicking anywhere skips boot sequence immediately."""
        self._dismiss_immediately()
        super().mousePressEvent(event)

    def _dismiss_immediately(self):
        if not self.is_closing:
            self.is_closing = True
            self.target_opacity = 0.0
            stop_audio()

    def closeEvent(self, event):
        """Clean up 120 FPS timer and audio device handles on widget close."""
        self.anim_timer.stop()
        stop_audio()
        super().closeEvent(event)

    def _on_tick(self):
        now = time.perf_counter()
        self.elapsed = now - self.start_time

        # Smooth alpha transitions at 120 FPS
        alpha_rate = 0.085 if not self.is_closing else 0.12
        self.opacity += (self.target_opacity - self.opacity) * alpha_rate

        # Extended duration: complete after 8.0 seconds (~8.0 to 8.5 seconds with smooth fade)
        if self.elapsed >= 8.0 and not self.is_closing:
            self.is_closing = True
            self.target_opacity = 0.0

        if self.is_closing and self.opacity < 0.015:
            self.anim_timer.stop()
            self.close()
            if self.on_complete:
                self.on_complete()
            return

        # Continuous Holographic Physics Rotations calibrated for 120 FPS
        spin_mult = 2.2 if self.elapsed < 2.5 else 1.0
        self.angle_outer += 0.7 * spin_mult
        self.angle_inner -= 1.1 * spin_mult
        self.orbital_angle += 0.9 * spin_mult
        self.globe_angle += 0.4 * spin_mult
        self.pulse_phase += 0.045

        # Dynamic audio visualizer bars
        for i in range(len(self.audio_bars)):
            target = 0.15 + 0.7 * abs(math.sin(self.pulse_phase * 1.5 + i * 0.7)) * random.uniform(0.6, 1.0)
            self.audio_bars[i] += (target - self.audio_bars[i]) * 0.18

        # Slight jitter on resource bars for realism
        self.cpu_load = 3.0 + 1.2 * math.sin(self.pulse_phase * 0.5)
        self.gpu_load = 14.0 + 2.0 * math.cos(self.pulse_phase * 0.4)

        self.update()

    def paintEvent(self, event):
        if self.opacity <= 0.005:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.opacity)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0 - 25.0

        # Stage Progression (0 to 1 scaling factors calibrated for 8-second duration)
        t = self.elapsed
        stage_bg = min(1.0, t / 0.6)
        stage_core = max(0.0, min(1.0, (t - 0.5) / 1.0))
        stage_telemetry = max(0.0, min(1.0, (t - 1.6) / 1.2))
        stage_lock = max(0.0, min(1.0, (t - 3.2) / 1.2))

        # 1. Dark Vignette Background & Holographic Ambience
        self._draw_background(painter, w, h, cx, cy, stage_bg)

        # 2. Raster Scanlines
        self._draw_scanlines(painter, w, h)

        # 3. Corner Tech Brackets & Coordinates
        self._draw_corner_brackets(painter, w, h, stage_bg)

        # 4. Volumetric Holographic Projector Beam & Floor Ripples
        if stage_core > 0.05:
            self._draw_projector_beam_and_ripples(painter, cx, cy, stage_core)

        # 5. Central 3D Arc Reactor, Wireframe Globe & Orbital Rings
        if stage_core > 0.01:
            self._draw_central_reactor(painter, cx, cy, stage_core, stage_lock)

        # 6. Left Telemetry Cards (SYSTEM STATUS, AUDIO ANALYSIS, SESSION)
        if stage_telemetry > 0.01:
            self._draw_left_telemetry(painter, stage_telemetry)

        # 7. Right Telemetry Cards (CONNECTED SYSTEMS, DATA SCOPE, RESOURCES)
        if stage_telemetry > 0.01:
            self._draw_right_telemetry(painter, w, stage_telemetry)

        # 8. Bottom Mode Buttons & Controls Strip
        self._draw_bottom_strip(painter, w, h, stage_telemetry)

    # -------------------------------------------------------------------------
    # Render Components
    # -------------------------------------------------------------------------

    def _draw_background(self, painter: QPainter, w: int, h: int, cx: float, cy: float, stage: float):
        """Draws the deep dark cyber vignette backdrop with radial core illumination."""
        # Deep space backdrop
        bg_brush = QBrush(QColor(3, 8, 16, int(240 * stage)))
        painter.fillRect(0, 0, w, h, bg_brush)

        # Radial core holographic glow
        glow_rad = QRadialGradient(cx, cy, 550)
        glow_rad.setColorAt(0.0, QColor(0, 180, 255, int(45 * stage)))
        glow_rad.setColorAt(0.4, QColor(0, 90, 180, int(20 * stage)))
        glow_rad.setColorAt(1.0, QColor(3, 8, 16, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow_rad))
        painter.drawRect(0, 0, w, h)

    def _draw_scanlines(self, painter: QPainter, w: int, h: int):
        """Subtle horizontal CRT holographic scanlines."""
        pen = QPen(QColor(0, 220, 255, 10), 1)
        painter.setPen(pen)
        step = 4
        for y in range(0, h, step):
            painter.drawLine(0, y, w, y)

    def _draw_corner_brackets(self, painter: QPainter, w: int, h: int, stage: float):
        """Sci-fi HUD corner brackets with system coordinate tags."""
        pen = QPen(QColor(0, 210, 255, int(150 * stage)), 1.5)
        painter.setPen(pen)

        margin = 35
        bracket_len = 38

        # Top-Left
        painter.drawLine(margin, margin + bracket_len, margin, margin)
        painter.drawLine(margin, margin, margin + bracket_len, margin)
        # Top-Right
        painter.drawLine(w - margin - bracket_len, margin, w - margin, margin)
        painter.drawLine(w - margin, margin, w - margin, margin + bracket_len)
        # Bottom-Left
        painter.drawLine(margin, h - margin - bracket_len, margin, h - margin)
        painter.drawLine(margin, h - margin, margin + bracket_len, h - margin)
        # Bottom-Right
        painter.drawLine(w - margin - bracket_len, h - margin, w - margin, h - margin)
        painter.drawLine(w - margin, h - margin - bracket_len, w - margin, h - margin)

        # Corner Micro-Text Metadata
        font = QFont("Consolas", 7)
        painter.setFont(font)
        painter.setPen(QColor(0, 190, 240, int(120 * stage)))
        painter.drawText(margin + 6, margin + 14, "SYS.REC . 0x7F2A")
        painter.drawText(w - margin - 85, margin + 14, "FOV 84 DEG . NATIVE")
        painter.drawText(margin + 6, h - margin - 6, "120HZ OPTICAL BUS")
        painter.drawText(w - margin - 110, h - margin - 6, "ESC . SKIP BOOT")

    def _draw_projector_beam_and_ripples(self, painter: QPainter, cx: float, cy: float, stage: float):
        """Holographic light cone projecting downward onto floor perspective ripples."""
        floor_y = cy + 280.0
        top_y = cy + 115.0

        # 1. Volumetric Light Cone Trapezoid
        beam_path = QPainterPath()
        beam_path.moveTo(cx - 70.0, top_y)
        beam_path.lineTo(cx + 70.0, top_y)
        beam_path.lineTo(cx + 260.0, floor_y)
        beam_path.lineTo(cx - 260.0, floor_y)
        beam_path.closeSubpath()

        beam_grad = QLinearGradient(cx, top_y, cx, floor_y)
        beam_grad.setColorAt(0.0, QColor(0, 230, 255, int(42 * stage)))
        beam_grad.setColorAt(0.5, QColor(0, 160, 230, int(20 * stage)))
        beam_grad.setColorAt(0.95, QColor(0, 110, 190, int(8 * stage)))
        beam_grad.setColorAt(1.0, QColor(0, 80, 150, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(beam_grad))
        painter.drawPath(beam_path)

        # 2. Concentric Floor Ripples (Perspective Ellipses)
        floor_pen = QPen(QColor(0, 220, 255, int(70 * stage)), 1.2)
        painter.setPen(floor_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        pulse = (math.sin(self.pulse_phase) + 1.0) / 2.0
        for r_x in [130.0, 185.0, 255.0]:
            r_y = r_x * 0.22
            dynamic_rx = r_x + pulse * 6.0
            dynamic_ry = r_y + pulse * 1.5
            painter.drawEllipse(QPointF(cx, floor_y), dynamic_rx, dynamic_ry)

        # 3. Floor Label Readout
        font_standby = QFont("Segoe UI", 12, QFont.Weight.Bold)
        font_standby.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.5)
        painter.setFont(font_standby)
        painter.setPen(QColor(0, 240, 255, int(210 * stage)))
        painter.drawText(int(cx - 90), int(floor_y + 6), "S T A N D B Y")

        font_sub = QFont("Segoe UI", 8, QFont.Weight.Medium)
        font_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        painter.setFont(font_sub)
        painter.setPen(QColor(0, 190, 230, int(150 * stage)))
        floor_sub_text = "OPTICAL SENSORS . 120HZ BUS READY"
        fm_sub = painter.fontMetrics()
        sub_w = fm_sub.horizontalAdvance(floor_sub_text)
        painter.drawText(int(cx - sub_w / 2.0), int(floor_y + 24), floor_sub_text)

    def _draw_central_reactor(self, painter: QPainter, cx: float, cy: float, stage: float, stage_lock: float):
        """
        Renders the multi-layered sci-fi Arc Reactor with outer tick dial,
        amber/cyan segmented arcs, 3D inclined orbital tracks, rotating wireframe globe,
        and central glowing typography.
        """
        # Outer Dial Tick Ring (Radius ~210)
        r_dial = 212.0
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(72):
            angle_deg = i * 5.0
            rad = math.radians(angle_deg)
            is_major = (i % 6 == 0)
            tick_len = 13.0 if is_major else 5.0
            c_alpha = int((190 if is_major else 90) * stage)
            tick_color = QColor(0, 240, 255, c_alpha)

            x1 = cx + (r_dial - tick_len) * math.cos(rad)
            y1 = cy + (r_dial - tick_len) * math.sin(rad)
            x2 = cx + r_dial * math.cos(rad)
            y2 = cy + r_dial * math.sin(rad)

            painter.setPen(QPen(tick_color, 1.5 if is_major else 1.0))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Cardinal Orientation Crosshair Ticks (N, S, E, W)
        cardinal_pen = QPen(QColor(0, 240, 255, int(230 * stage)), 2.0)
        painter.setPen(cardinal_pen)
        painter.drawLine(int(cx), int(cy - r_dial - 25), int(cx), int(cy - r_dial + 8))
        painter.drawLine(int(cx), int(cy + r_dial - 8), int(cx), int(cy + r_dial + 25))
        painter.drawLine(int(cx - r_dial - 25), int(cy), int(cx - r_dial + 8), int(cy))
        painter.drawLine(int(cx + r_dial - 8), int(cy), int(cx + r_dial + 25), int(cy))

        # Concentric Segmented Rings with Distinct Amber Accent (matching image)
        # Ring 1: Outer Layer (Radius 184)
        r1 = 184.0
        rect1 = QRectF(cx - r1, cy - r1, r1 * 2, r1 * 2)

        # Cyan Segments
        pen_cyan_outer = QPen(QColor(0, 220, 255, int(200 * stage)), 2.2)
        painter.setPen(pen_cyan_outer)
        painter.drawArc(rect1, int((self.angle_outer + 0) * 16), int(70 * 16))
        painter.drawArc(rect1, int((self.angle_outer + 210) * 16), int(60 * 16))

        # Amber / Orange Segments (#FFB300)
        pen_amber_outer = QPen(QColor(255, 179, 0, int(240 * stage)), 2.8)
        painter.setPen(pen_amber_outer)
        # Bold amber arc on the left side
        painter.drawArc(rect1, int((self.angle_outer + 125) * 16), int(65 * 16))
        # Small amber accent on the upper-right
        painter.drawArc(rect1, int((self.angle_outer + 310) * 16), int(22 * 16))

        # Ring 2: Counter-Rotating Middle Ring (Radius 158)
        r2 = 158.0
        rect2 = QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2)
        pen_cyan_mid = QPen(QColor(0, 200, 255, int(180 * stage)), 1.8)
        painter.setPen(pen_cyan_mid)
        for k in range(4):
            start = int((self.angle_inner + k * 90) * 16)
            painter.drawArc(rect2, start, int(45 * 16))

        # Ring 3: Inner Solid Reticle with Gap Cuts (Radius 140)
        r3 = 140.0
        rect3 = QRectF(cx - r3, cy - r3, r3 * 2, r3 * 2)
        pen_cyan_fine = QPen(QColor(0, 240, 255, int(150 * stage)), 1.2)
        painter.setPen(pen_cyan_fine)
        for k in range(4):
            start = int((k * 90 + 8) * 16)
            painter.drawArc(rect3, start, int(74 * 16))

        # 3D Inclined Parametric Orbital Rings with Traveling Satellite Nodes
        self._draw_3d_orbital_rings(painter, cx, cy, stage)

        # Rotating 3D Wireframe Globe
        self._draw_wireframe_globe(painter, cx, cy, stage)

        # Central Neon Flare
        pulse = (math.sin(self.pulse_phase) + 1.0) / 2.0
        flare_r = 75.0 + pulse * 14.0
        flare_grad = QRadialGradient(cx, cy, flare_r)
        flare_grad.setColorAt(0.0, QColor(0, 240, 255, int(80 * stage)))
        flare_grad.setColorAt(0.5, QColor(0, 160, 240, int(35 * stage)))
        flare_grad.setColorAt(1.0, QColor(0, 100, 200, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(flare_grad))
        painter.drawEllipse(QPointF(cx, cy), flare_r, flare_r)

        # Central Typography: J . A . R . V . I . S .
        title_color = QColor(230, 252, 255, int(255 * stage))
        font_title = QFont("Segoe UI", 25, QFont.Weight.Bold)
        font_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6.0)
        painter.setFont(font_title)

        title_text = "J . A . R . V . I . S ."
        title_w = painter.fontMetrics().horizontalAdvance(title_text)
        # Halo back-pass
        painter.setPen(QColor(0, 240, 255, int(130 * stage)))
        painter.drawText(int(cx - title_w / 2.0 - 1), int(cy + 10), title_text)
        painter.setPen(title_color)
        painter.drawText(int(cx - title_w / 2.0), int(cy + 9), title_text)

        # Subtitle: OPTICAL TRACKING . 120HZ GESTURE BUS . AIM ASSIST
        font_sub = QFont("Consolas", 7, QFont.Weight.DemiBold)
        font_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
        painter.setFont(font_sub)
        painter.setPen(QColor(0, 220, 255, int(190 * stage)))
        sub_text = "OPTICAL TRACKING . 120HZ GESTURE BUS . AIM ASSIST"
        sub_w = painter.fontMetrics().horizontalAdvance(sub_text)
        painter.drawText(int(cx - sub_w / 2.0), int(cy + 28), sub_text)

    def _draw_3d_orbital_rings(self, painter: QPainter, cx: float, cy: float, stage: float):
        """
        Draws 3D inclined orbital ellipses with mathematically projected coordinates
        and animated orbiting nodes (including the distinctive amber node).
        """
        orbits = [
            # (radius, tilt_deg, rot_deg, speed, node_color, is_amber)
            (225.0, 65.0, 28.0, 0.022, QColor(0, 240, 255), False),
            (205.0, -56.0, -32.0, -0.018, QColor(255, 179, 0), True),
            (185.0, 72.0, 80.0, 0.015, QColor(0, 210, 255), False),
        ]

        for idx, (r, tilt_deg, rot_deg, speed, node_col, is_amber) in enumerate(orbits):
            rad_tilt = math.radians(tilt_deg)
            rad_rot = math.radians(rot_deg)

            # Build 3D Projected Path
            path = QPainterPath()
            steps = 48
            for s in range(steps + 1):
                t = (s / steps) * 2.0 * math.pi
                x0 = r * math.cos(t)
                y0 = r * math.sin(t) * math.cos(rad_tilt)
                xr = x0 * math.cos(rad_rot) - y0 * math.sin(rad_rot)
                yr = x0 * math.sin(rad_rot) + y0 * math.cos(rad_rot)
                pt = QPointF(cx + xr, cy + yr)
                if s == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)

            pen_alpha = int((140 if not is_amber else 170) * stage)
            pen_color = QColor(0, 200, 255, pen_alpha) if not is_amber else QColor(255, 179, 0, pen_alpha)
            painter.setPen(QPen(pen_color, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

            # Orbiting Satellite Node
            node_t = (self.orbital_angle * speed * 2.5 + idx * 1.8) % (2.0 * math.pi)
            nx0 = r * math.cos(node_t)
            ny0 = r * math.sin(node_t) * math.cos(rad_tilt)
            nxr = nx0 * math.cos(rad_rot) - ny0 * math.sin(rad_rot)
            nyr = nx0 * math.sin(rad_rot) + ny0 * math.cos(rad_rot)
            node_pt = QPointF(cx + nxr, cy + nyr)

            # Draw Node with Glow
            node_rad = 3.5 if is_amber else 3.0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(node_col.red(), node_col.green(), node_col.blue(), int(255 * stage))))
            painter.drawEllipse(node_pt, node_rad, node_rad)

            # Outer node flare
            painter.setBrush(QBrush(QColor(node_col.red(), node_col.green(), node_col.blue(), int(90 * stage))))
            painter.drawEllipse(node_pt, node_rad * 2.2, node_rad * 2.2)

    def _draw_wireframe_globe(self, painter: QPainter, cx: float, cy: float, stage: float):
        """Renders the central 3D wireframe rotating globe."""
        rg = 122.0
        globe_pen = QPen(QColor(0, 190, 240, int(75 * stage)), 1.0)
        painter.setPen(globe_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Latitude Parallels
        for lat in [-48.0, -24.0, 0.0, 24.0, 48.0]:
            rad_lat = math.radians(lat)
            y_lat = cy + rg * math.sin(rad_lat)
            rx = rg * math.cos(rad_lat)
            ry = rx * 0.30
            painter.drawEllipse(QPointF(cx, y_lat), rx, ry)

        # Rotating Longitude Meridians
        for offset in [0.0, 36.0, 72.0, 108.0, 144.0]:
            rad_m = math.radians(self.globe_angle + offset)
            rx = rg * abs(math.cos(rad_m))
            painter.drawEllipse(QPointF(cx, cy), rx, rg)

    def _draw_left_telemetry(self, painter: QPainter, stage: float):
        """Renders the Left Holographic Telemetry Cards matching the reference screenshot."""
        card_w = 210
        x = 55
        card_alpha = int(stage * 255)

        # Card 1: SYSTEM STATUS
        y1 = 65
        self._draw_cyber_panel(painter, x, y1, card_w, 115, "SYSTEM STATUS", stage)
        font_body = QFont("Consolas", 8)
        painter.setFont(font_body)

        # Rows
        rows1 = [
            ("CORE", "ONLINE", QColor(0, 240, 255)),
            ("TRACKER", "OPTICAL 120HZ", QColor(200, 230, 255)),
            ("ENGINE", "MEDIAPIPE V2", QColor(200, 230, 255)),
            ("UPTIME", f"00.00.{int(self.elapsed):02d}", QColor(0, 240, 255)),
        ]
        self._draw_key_value_rows(painter, x + 12, y1 + 32, card_w - 24, rows1, stage)

        # Card 2: OPTICAL BUS
        y2 = 195
        self._draw_cyber_panel(painter, x, y2, card_w, 115, "OPTICAL BUS", stage)

        # Key-Value & Animated Waveform
        painter.setPen(QColor(130, 180, 220, int(200 * stage)))
        painter.drawText(x + 12, y2 + 35, "INPUT")

        # Draw animated optical signal visualizer bar meter
        bar_start_x = x + 75
        bar_y = y2 + 35
        bar_w = 6
        for b_idx, amp in enumerate(self.audio_bars):
            bx = bar_start_x + b_idx * (bar_w + 3)
            bh = int(amp * 16.0)
            painter.fillRect(bx, bar_y - bh, bar_w, bh, QColor(0, 240, 255, int(220 * stage)))

        rows2 = [
            ("CAMERA", "DIRECTSHOW 60", QColor(200, 230, 255)),
            ("INJECTION", "WIN32 HARDWARE", QColor(0, 255, 170)),
        ]
        self._draw_key_value_rows(painter, x + 12, y2 + 65, card_w - 24, rows2, stage)

        # Card 3: SESSION BUS
        y3 = 325
        self._draw_cyber_panel(painter, x, y3, card_w, 95, "SESSION BUS", stage)
        rows3 = [
            ("LATENCY", "8 MS NATIVE", QColor(0, 240, 255)),
            ("BUS RATE", "120 HZ", QColor(200, 230, 255)),
            ("DISPATCH", "ZERO LAG", QColor(0, 255, 170)),
        ]
        self._draw_key_value_rows(painter, x + 12, y3 + 32, card_w - 24, rows3, stage)

    def _draw_right_telemetry(self, painter: QPainter, w: int, stage: float):
        """Renders the Right Holographic Telemetry Cards matching the reference screenshot."""
        card_w = 210
        x = w - card_w - 55

        # Card 1: CONNECTED SYSTEMS
        y1 = 65
        self._draw_cyber_panel(painter, x, y1, card_w, 125, "CONNECTED SYSTEMS", stage)
        rows1 = [
            (". MOTION TRACKER", "ONLINE", QColor(0, 240, 255)),
            (". GESTURE ENGINE", "120 HZ", QColor(200, 230, 255)),
            (". WEBCAM STREAM", "DIRECTSHOW", QColor(0, 255, 170)),
            (". STICKY AIM ASSIST", "ACTIVE", QColor(0, 240, 255)),
            (". OS INPUT INJECTION", "WIN32", QColor(140, 180, 210)),
        ]
        self._draw_key_value_rows(painter, x + 12, y1 + 30, card_w - 24, rows1, stage, line_h=17)

        # Card 2: AIM ASSIST CONTROL
        y2 = 205
        self._draw_cyber_panel(painter, x, y2, card_w, 105, "AIM ASSIST CONTROL", stage)
        rows2 = [
            (". TARGET CLING", "42 PX", QColor(0, 255, 170)),
            (". BREAKOUT SPEED", "750 PX SEC", QColor(200, 230, 255)),
            (". STICKY MAGNET", "ACTIVE", QColor(0, 240, 255)),
            (". BUTTON CLING", "LOCKED", QColor(200, 230, 255)),
        ]
        self._draw_key_value_rows(painter, x + 12, y2 + 30, card_w - 24, rows2, stage, line_h=17)

        # Card 3: SYSTEM RESOURCES
        y3 = 325
        self._draw_cyber_panel(painter, x, y3, card_w, 95, "SYSTEM RESOURCES", stage)
        painter.setFont(QFont("Consolas", 8))

        # CPU Progress Bar
        painter.setPen(QColor(130, 180, 220, int(200 * stage)))
        painter.drawText(x + 12, y3 + 32, "CPU LOAD")
        painter.drawText(x + card_w - 38, y3 + 32, f"{int(self.cpu_load)}%")
        self._draw_progress_bar(painter, x + 12, y3 + 40, card_w - 24, 4, self.cpu_load / 100.0, stage)

        # GPU Progress Bar
        painter.drawText(x + 12, y3 + 64, "GPU LOAD")
        painter.drawText(x + card_w - 38, y3 + 64, f"{int(self.gpu_load)}%")
        self._draw_progress_bar(painter, x + 12, y3 + 72, card_w - 24, 4, self.gpu_load / 100.0, stage)

    def _draw_cyber_panel(self, painter: QPainter, x: int, y: int, w: int, h: int, title: str, stage: float):
        """Draws an individual sci-fi bordered telemetry card panel."""
        alpha = int(stage * 255)

        # Panel translucent backdrop
        rect = QRectF(x, y, w, h)
        panel_grad = QLinearGradient(x, y, x + w, y + h)
        panel_grad.setColorAt(0.0, QColor(6, 16, 32, int(190 * stage)))
        panel_grad.setColorAt(1.0, QColor(4, 10, 22, int(210 * stage)))

        painter.setPen(QPen(QColor(0, 180, 230, int(110 * stage)), 1.2))
        painter.setBrush(QBrush(panel_grad))
        painter.drawRect(rect)

        # Header Title Bar
        header_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        header_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        painter.setFont(header_font)
        painter.setPen(QColor(0, 240, 255, int(230 * stage)))
        painter.drawText(x + 12, y + 16, title)

        # Accent Corner notch on panel
        painter.setPen(QPen(QColor(0, 240, 255, int(200 * stage)), 2.0))
        painter.drawLine(x, y + 6, x, y)
        painter.drawLine(x, y, x + 6, y)
        painter.drawLine(x + w - 6, y, x + w, y)
        painter.drawLine(x + w, y, x + w, y + 6)

    def _draw_key_value_rows(self, painter: QPainter, x: int, start_y: int, width: int, rows: list, stage: float, line_h: int = 18):
        """Renders aligned key-value telemetry rows."""
        painter.setFont(QFont("Consolas", 8))
        fm = painter.fontMetrics()
        for idx, (key, val, col) in enumerate(rows):
            cur_y = start_y + idx * line_h
            painter.setPen(QColor(130, 180, 220, int(190 * stage)))
            painter.drawText(x, cur_y, key)

            painter.setPen(QColor(col.red(), col.green(), col.blue(), int(230 * stage)))
            # Right-aligned value using exact font advance
            val_w = fm.horizontalAdvance(val)
            painter.drawText(x + width - val_w, cur_y, val)

    def _draw_progress_bar(self, painter: QPainter, x: int, y: int, w: int, h: int, frac: float, stage: float):
        """Renders a sleek futuristic horizontal progress bar."""
        # Track
        painter.fillRect(x, y, w, h, QColor(0, 60, 90, int(150 * stage)))
        # Fill (clamped between 0.0 and 1.0)
        clamped_frac = max(0.0, min(1.0, frac))
        fill_w = int(w * clamped_frac)
        if fill_w > 0:
            painter.fillRect(x, y, fill_w, h, QColor(0, 240, 255, int(230 * stage)))

    def _draw_bottom_strip(self, painter: QPainter, w: int, h: int, stage: float):
        """Draws the bottom row mode buttons in pure English for Project Kontroll."""
        btn_y = h - 55
        btn_h = 26

        buttons = [
            # (label, is_highlighted, is_amber)
            ("120HZ GESTURE BUS", False, True),
            ("OPTICAL TRACKING", True, False),
            ("AIM ASSIST ACTIVE", False, False),
            ("DIRECT OS INJECTION", False, False),
            ("SHAKA STANDBY", False, False),
        ]

        font_btn = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        painter.setFont(font_btn)
        fm = painter.fontMetrics()

        btn_widths = [fm.horizontalAdvance(label) + 24 for label, _, _ in buttons]
        total_btn_w = sum(btn_widths) + (len(buttons) - 1) * 10
        start_x = int((w - total_btn_w) / 2.0)
        cur_x = start_x

        for (label, is_active, is_amber), btn_w in zip(buttons, btn_widths):
            btn_rect = QRectF(cur_x, btn_y, btn_w, btn_h)

            if is_active:
                # Solid glowing cyan button
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(0, 240, 255, int(230 * stage))))
                painter.drawRoundedRect(btn_rect, 3, 3)
                painter.setPen(QColor(3, 8, 16))
                painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, label)
            elif is_amber:
                # Amber accent button
                painter.setPen(QPen(QColor(255, 179, 0, int(220 * stage)), 1.2))
                painter.setBrush(QBrush(QColor(40, 25, 0, int(160 * stage))))
                painter.drawRoundedRect(btn_rect, 3, 3)
                painter.setPen(QColor(255, 179, 0, int(240 * stage)))
                painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, label)
            else:
                # Dark cyan tech button
                painter.setPen(QPen(QColor(0, 160, 210, int(130 * stage)), 1.0))
                painter.setBrush(QBrush(QColor(4, 16, 30, int(170 * stage))))
                painter.drawRoundedRect(btn_rect, 3, 3)
                painter.setPen(QColor(0, 200, 240, int(180 * stage)))
                painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, label)

            cur_x += btn_w + 10



class JarvisHudOverlay(QWidget):
    """
    Holographic HUD Manager for Project Kontroll.
    - Manages the full-screen cinematic boot sequence (FullScreenJarvisBootOverlay).
    - Renders the sleek top-banner notification overlay for mode changes (🤙 Shaka gesture).
    """

    def __init__(self):
        super().__init__()

        # Window Flags: Frameless, On-Top, Tool window (no taskbar button)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # Positioning for Runtime Popups
        self.hud_width = 540
        self.hud_height = 180
        self.resize(self.hud_width, self.hud_height)
        self._center_top()

        # Animation states for popup
        self.opacity = 0.0
        self.target_opacity = 0.0
        self.angle_inner = 0.0
        self.angle_outer = 0.0
        self.pulse_phase = 0.0

        # State info
        self.is_system_active = True
        self.status_title = "JARVIS ONLINE"
        self.status_subtitle = "KONTROLL AR SYSTEM . ACTIVE"
        self.status_badge = "OS STICKY AIM ASSIST . READY"
        self.status_color = QColor(0, 240, 255)

        # 120 FPS animation ticker (8ms)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._update_animation)
        self.anim_timer.start(8)

        # Auto-hide timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self._fade_out)

        # Active full-screen boot instance
        self._boot_window: Optional[FullScreenJarvisBootOverlay] = None

    def _center_top(self):
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            x = (geom.width() - self.hud_width) // 2
            y = 40
            self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        self._enable_click_through()

    def _enable_click_through(self):
        """Win32 API to make popup window completely pass-through."""
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW)
        except Exception:
            pass

    def closeEvent(self, event):
        """Clean up 120 FPS timer and dismiss timer on HUD close."""
        self.anim_timer.stop()
        self.dismiss_timer.stop()
        super().closeEvent(event)

    def trigger_boot_sequence(self):
        """
        Triggers the dynamic, full-screen sci-fi Jarvis boot sequence
        matching the user's reference HUD image.
        """
        if self._boot_window is not None:
            try:
                self._boot_window.anim_timer.stop()
                self._boot_window.close()
            except Exception:
                pass
            self._boot_window = None

        self._boot_window = FullScreenJarvisBootOverlay(on_complete=self._on_boot_complete)
        self._boot_window.show()
        self._boot_window.raise_()
        self._boot_window.activateWindow()

    def _on_boot_complete(self):
        self._boot_window = None

    def trigger_popup(self, is_active: bool):
        """Triggers the compact holographic HUD notification on state toggle (🤙 Shaka)."""
        self.is_system_active = is_active
        if is_active:
            self.status_title = "JARVIS ONLINE"
            self.status_subtitle = "KONTROLL AR SYSTEM . ACTIVE"
            self.status_badge = "OS STICKY AIM ASSIST . READY"
            self.status_color = QColor(0, 240, 255)
        else:
            self.status_title = "SYSTEM STANDBY"
            self.status_subtitle = "KONTROLL TRACKING . PAUSED"
            self.status_badge = "STANDBY . RESUME WITH SHAKA"
            self.status_color = QColor(255, 170, 0)

        play_jarvis_sound(is_active)

        self.target_opacity = 1.0
        self.show()
        self.raise_()

        self.dismiss_timer.stop()
        # Extended duration: keep popup visible for entire voice announcement (~3.5-3.8s)
        self.dismiss_timer.start(3800)

    def _fade_out(self):
        self.target_opacity = 0.0

    def _update_animation(self):
        """120 FPS rotation & alpha transition step for popup."""
        alpha_speed = 0.08
        self.opacity += (self.target_opacity - self.opacity) * alpha_speed
        if self.opacity < 0.01 and self.target_opacity == 0.0:
            self.opacity = 0.0
            self.hide()

        # Reticle rotations calibrated for 120 FPS
        self.angle_inner += 1.4
        self.angle_outer -= 0.8
        self.pulse_phase += 0.04

        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        if self.opacity <= 0.001:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.opacity)

        w = self.width()
        h = self.height()
        cx = 75.0
        cy = h / 2.0

        col = self.status_color

        # Background Sci-Fi Tech Container
        bg_rect = QRectF(8, 12, w - 16, h - 24)
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor(6, 14, 28, 225))
        grad.setColorAt(0.5, QColor(10, 24, 45, 210))
        grad.setColorAt(1.0, QColor(4, 8, 18, 225))

        painter.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 170), 1.5))
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(bg_rect, 10, 10)

        # Tech Corner Accent Lines
        corner_pen = QPen(col, 2.2)
        painter.setPen(corner_pen)
        painter.drawLine(int(bg_rect.left()), int(bg_rect.top() + 15), int(bg_rect.left()), int(bg_rect.top()))
        painter.drawLine(int(bg_rect.left()), int(bg_rect.top()), int(bg_rect.left() + 25), int(bg_rect.top()))
        painter.drawLine(int(bg_rect.right()), int(bg_rect.bottom() - 15), int(bg_rect.right()), int(bg_rect.bottom()))
        painter.drawLine(int(bg_rect.right()), int(bg_rect.bottom()), int(bg_rect.right() - 25), int(bg_rect.bottom()))

        # Holographic Rotating Arc Reactor Reticle
        outer_pen = QPen(QColor(col.red(), col.green(), col.blue(), 200), 2.0)
        painter.setPen(outer_pen)
        r_outer = 42.0
        for i in range(3):
            start_deg = int(self.angle_outer + i * 120) * 16
            span_deg = 80 * 16
            painter.drawArc(QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2), start_deg, span_deg)

        inner_pen = QPen(col, 2.5)
        painter.setPen(inner_pen)
        r_inner = 30.0
        for i in range(4):
            start_deg = int(self.angle_inner + i * 90) * 16
            span_deg = 45 * 16
            painter.drawArc(QRectF(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2), start_deg, span_deg)

        # Center Glowing Core
        pulse = (math.sin(self.pulse_phase) + 1.0) / 2.0
        core_r = 9.0 + pulse * 3.5
        core_grad = QRadialGradient(cx, cy, core_r)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
        core_grad.setColorAt(0.6, col)
        core_grad.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # Typography & Status Readout
        text_x = 145
        font_title = QFont("Segoe UI", 14, QFont.Weight.Bold)
        font_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255, 245))
        painter.drawText(text_x, int(cy - 6), self.status_title)

        font_sub = QFont("Consolas", 9, QFont.Weight.DemiBold)
        font_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        painter.setFont(font_sub)
        painter.setPen(col)
        painter.drawText(text_x, int(cy + 16), self.status_subtitle)

        font_micro = QFont("Consolas", 8)
        painter.setFont(font_micro)
        painter.setPen(QColor(160, 190, 220, 180))
        painter.drawText(text_x, int(cy + 34), self.status_badge)
