"""
Futuristic Jarvis Holographic HUD Overlay for Project Kontroll.
Renders an animated, glowing sci-fi HUD reticle with click-through capability and zero focus stealing.
"""

import sys
import math
import threading
import ctypes
from ctypes import wintypes
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, QLinearGradient
from PyQt6.QtWidgets import QWidget, QApplication

# Win32 click-through constants
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080


def play_jarvis_sound(is_active: bool):
    """Generates a high-tech synthetic audio chime in the background."""
    def _audio_worker():
        try:
            import winsound
            if is_active:
                # Rising two-tone affirmative Jarvis chirp
                winsound.Beep(880, 70)   # A5
                winsound.Beep(1320, 110) # E6
            else:
                # Descending standby chime
                winsound.Beep(1100, 70)
                winsound.Beep(660, 120)
        except Exception:
            pass

    threading.Thread(target=_audio_worker, daemon=True).start()


class JarvisHudOverlay(QWidget):
    """
    Transparent, click-through, always-on-top holographic Jarvis HUD.
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

        # Position in top-right or center-top of primary screen
        self.hud_width = 460
        self.hud_height = 200
        self.resize(self.hud_width, self.hud_height)
        self._center_top()

        # Animation states
        self.opacity = 0.0
        self.target_opacity = 0.0
        self.angle_inner = 0.0
        self.angle_outer = 0.0
        self.pulse_phase = 0.0

        # State info
        self.is_system_active = True
        self.status_title = "JARVIS ONLINE"
        self.status_subtitle = "KONTROLL AR SYSTEM // ACTIVE"
        self.status_color = QColor(0, 240, 255) # Neon Cyan

        # Lifecycle Timer: 60 FPS animation ticker
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._update_animation)
        self.anim_timer.start(16) # ~60 FPS

        # Auto-hide timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self._fade_out)

    def _center_top(self):
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            x = (geom.width() - self.hud_width) // 2
            y = 50 # 50px from top of screen
            self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        self._enable_click_through()

    def _enable_click_through(self):
        """Invokes Win32 API to make the window completely click-through (pass-through)."""
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW)

    def trigger_popup(self, is_active: bool):
        """Triggers the holographic HUD presentation."""
        self.is_system_active = is_active
        if is_active:
            self.status_title = "JARVIS ONLINE"
            self.status_subtitle = "KONTROLL AR SYSTEM // ACTIVE"
            self.status_color = QColor(0, 240, 255) # Glowing Electric Cyan
        else:
            self.status_title = "SYSTEM STANDBY"
            self.status_subtitle = "KONTROLL TRACKING // PAUSED"
            self.status_color = QColor(255, 170, 0) # High-Tech Amber

        # Play audio chirp
        play_jarvis_sound(is_active)

        # Show & Fade in
        self.target_opacity = 1.0
        self.show()
        self.raise_()

        # Schedule auto-hide after 2.0 seconds
        self.dismiss_timer.stop()
        self.dismiss_timer.start(2000)

    def _fade_out(self):
        self.target_opacity = 0.0

    def _update_animation(self):
        """60 FPS rotation & alpha transition step."""
        # Smooth alpha interpolation
        alpha_speed = 0.15
        self.opacity += (self.target_opacity - self.opacity) * alpha_speed
        if self.opacity < 0.01 and self.target_opacity == 0.0:
            self.opacity = 0.0
            self.hide()

        # Reticle rotations
        self.angle_inner += 2.8
        self.angle_outer -= 1.6
        self.pulse_phase += 0.08

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

        # 1. Background Sci-Fi Tech Pill Container
        bg_rect = QRectF(10, 15, w - 20, h - 30)
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor(8, 14, 28, 210))
        grad.setColorAt(0.5, QColor(10, 24, 45, 190))
        grad.setColorAt(1.0, QColor(4, 8, 16, 210))

        painter.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 160), 1.5))
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(bg_rect, 14, 14)

        # Tech Corner Accent Lines
        corner_pen = QPen(col, 2.5)
        painter.setPen(corner_pen)
        # Top-left accent
        painter.drawLine(int(bg_rect.left()), int(bg_rect.top() + 15), int(bg_rect.left()), int(bg_rect.top()))
        painter.drawLine(int(bg_rect.left()), int(bg_rect.top()), int(bg_rect.left() + 25), int(bg_rect.top()))
        # Bottom-right accent
        painter.drawLine(int(bg_rect.right()), int(bg_rect.bottom() - 15), int(bg_rect.right()), int(bg_rect.bottom()))
        painter.drawLine(int(bg_rect.right()), int(bg_rect.bottom()), int(bg_rect.right() - 25), int(bg_rect.bottom()))

        # 2. Holographic Rotating Arc Reactor Reticle
        # Outer Segmented Arc
        outer_pen = QPen(QColor(col.red(), col.green(), col.blue(), 200), 2.0)
        painter.setPen(outer_pen)
        r_outer = 45.0
        for i in range(3):
            start_deg = int(self.angle_outer + i * 120) * 16
            span_deg = 80 * 16
            painter.drawArc(QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2), start_deg, span_deg)

        # Inner Segmented Arc
        inner_pen = QPen(col, 2.5)
        painter.setPen(inner_pen)
        r_inner = 32.0
        for i in range(4):
            start_deg = int(self.angle_inner + i * 90) * 16
            span_deg = 45 * 16
            painter.drawArc(QRectF(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2), start_deg, span_deg)

        # Center Glowing Core
        pulse = (math.sin(self.pulse_phase) + 1.0) / 2.0
        core_r = 10.0 + pulse * 4.0
        core_grad = QRadialGradient(cx, cy, core_r)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
        core_grad.setColorAt(0.6, col)
        core_grad.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # 3. Typography & Status Readout
        text_x = 150
        # Title
        font_title = QFont("Segoe UI", 16, QFont.Weight.Bold)
        font_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255, 245))
        painter.drawText(text_x, int(cy - 6), self.status_title)

        # Subtitle
        font_sub = QFont("Consolas", 10, QFont.Weight.DemiBold)
        font_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        painter.setFont(font_sub)
        painter.setPen(col)
        painter.drawText(text_x, int(cy + 18), self.status_subtitle)

        # Live Metric Badges
        font_micro = QFont("Consolas", 8)
        painter.setFont(font_micro)
        painter.setPen(QColor(160, 190, 220, 180))
        painter.drawText(text_x, int(cy + 36), "1€ ADAPTIVE FILTER // SENDINPUT KERNEL")
