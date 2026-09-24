"""
Futuristic Jarvis Holographic HUD Overlay for Project Kontroll.
Renders an animated, glowing sci-fi HUD reticle with click-through capability,
zero focus stealing, and multi-stage boot sequence animation.
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
                winsound.Beep(880, 70)   # A5
                winsound.Beep(1320, 110) # E6
            else:
                winsound.Beep(1100, 70)
                winsound.Beep(660, 120)
        except Exception:
            pass

    threading.Thread(target=_audio_worker, daemon=True).start()


def play_boot_chime(frequency: int, duration_ms: int):
    """Plays an individual note during the boot sequence."""
    def _worker():
        try:
            import winsound
            winsound.Beep(frequency, duration_ms)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


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

        # Positioning
        self.hud_width = 540
        self.hud_height = 200
        self.resize(self.hud_width, self.hud_height)
        self._center_top()

        # Animation states
        self.opacity = 0.0
        self.target_opacity = 0.0
        self.angle_inner = 0.0
        self.angle_outer = 0.0
        self.pulse_phase = 0.0
        self.rotation_speed_mult = 1.0

        # State info
        self.is_system_active = True
        self.status_title = "JARVIS ONLINE"
        self.status_subtitle = "KONTROLL AR SYSTEM // ACTIVE"
        self.status_badge = "120HZ ADAPTIVE FILTER // OS AIM ASSIST"
        self.status_color = QColor(0, 240, 255)

        # 60 FPS animation ticker
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._update_animation)
        self.anim_timer.start(16)

        # Auto-hide timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self._fade_out)

    def _center_top(self):
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            x = (geom.width() - self.hud_width) // 2
            y = 50
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

    def trigger_boot_sequence(self):
        """
        Triggers a multi-stage holographic boot sequence with rising audio frequencies.
        """
        self.rotation_speed_mult = 3.0
        self.target_opacity = 1.0
        self.show()
        self.raise_()

        # Stage 0: Initializing
        self.status_title = "INITIALIZING JARVIS PROTOCOL..."
        self.status_subtitle = "KERNEL V2.4 // LINKING ACCESSIBILITY BUS"
        self.status_badge = "STATUS: MOUNTING OPTICAL CHANNELS"
        self.status_color = QColor(0, 200, 255)
        play_boot_chime(520, 90)

        # Stage 1: Optical sensors
        QTimer.singleShot(900, lambda: self._boot_stage_1())
        # Stage 2: Aim assist
        QTimer.singleShot(1800, lambda: self._boot_stage_2())
        # Stage 3: Operational
        QTimer.singleShot(2700, lambda: self._boot_stage_3())
        # Dismiss
        QTimer.singleShot(4200, lambda: self._fade_out())

    def _boot_stage_1(self):
        self.status_title = "CALIBRATING OPTICAL SENSORS..."
        self.status_subtitle = "120HZ ADAPTIVE 1€ FILTER ONLINE"
        self.status_badge = "SENSORS: ACTIVE // MJPG DIRECTSHOW 60FPS"
        self.status_color = QColor(0, 240, 255)
        play_boot_chime(880, 90)

    def _boot_stage_2(self):
        self.status_title = "ENGAGING OS STICKY AIM ASSIST..."
        self.status_subtitle = "SYSTEM-WIDE TARGET CLING ENGAGED"
        self.status_badge = "STICKY AIM ASSIST: ZERO CURSOR DRIFT"
        self.status_color = QColor(0, 255, 180)
        play_boot_chime(1320, 90)

    def _boot_stage_3(self):
        self.status_title = "JARVIS AR FULLY OPERATIONAL"
        self.status_subtitle = "ALL SYSTEMS NOMINAL // WELCOME BACK"
        self.status_badge = "READY // FIST-THUMB TO CLICK, 👌 TO DRAG"
        self.status_color = QColor(0, 255, 255)
        self.rotation_speed_mult = 1.0
        play_boot_chime(1760, 150)

    def trigger_popup(self, is_active: bool):
        """Triggers the holographic HUD presentation."""
        self.is_system_active = is_active
        self.rotation_speed_mult = 1.0
        if is_active:
            self.status_title = "JARVIS ONLINE"
            self.status_subtitle = "KONTROLL AR SYSTEM // ACTIVE"
            self.status_badge = "OS STICKY AIM ASSIST // READY"
            self.status_color = QColor(0, 240, 255)
        else:
            self.status_title = "SYSTEM STANDBY"
            self.status_subtitle = "KONTROLL TRACKING // PAUSED"
            self.status_badge = "STANDBY // RE-ENGAGE WITH SYSTEM TRAY"
            self.status_color = QColor(255, 170, 0)

        play_jarvis_sound(is_active)

        self.target_opacity = 1.0
        self.show()
        self.raise_()

        self.dismiss_timer.stop()
        self.dismiss_timer.start(2000)

    def _fade_out(self):
        self.target_opacity = 0.0

    def _update_animation(self):
        """60 FPS rotation & alpha transition step."""
        alpha_speed = 0.15
        self.opacity += (self.target_opacity - self.opacity) * alpha_speed
        if self.opacity < 0.01 and self.target_opacity == 0.0:
            self.opacity = 0.0
            self.hide()

        # Reticle rotations
        self.angle_inner += 2.8 * self.rotation_speed_mult
        self.angle_outer -= 1.6 * self.rotation_speed_mult
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
        cx = 80.0
        cy = h / 2.0

        col = self.status_color

        # 1. Background Sci-Fi Tech Container
        bg_rect = QRectF(10, 15, w - 20, h - 30)
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor(8, 14, 28, 220))
        grad.setColorAt(0.5, QColor(10, 24, 45, 200))
        grad.setColorAt(1.0, QColor(4, 8, 16, 220))

        painter.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 170), 1.5))
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(bg_rect, 14, 14)

        # Tech Corner Accent Lines
        corner_pen = QPen(col, 2.5)
        painter.setPen(corner_pen)
        painter.drawLine(int(bg_rect.left()), int(bg_rect.top() + 15), int(bg_rect.left()), int(bg_rect.top()))
        painter.drawLine(int(bg_rect.left()), int(bg_rect.top()), int(bg_rect.left() + 25), int(bg_rect.top()))
        painter.drawLine(int(bg_rect.right()), int(bg_rect.bottom() - 15), int(bg_rect.right()), int(bg_rect.bottom()))
        painter.drawLine(int(bg_rect.right()), int(bg_rect.bottom()), int(bg_rect.right() - 25), int(bg_rect.bottom()))

        # 2. Holographic Rotating Arc Reactor Reticle
        outer_pen = QPen(QColor(col.red(), col.green(), col.blue(), 200), 2.0)
        painter.setPen(outer_pen)
        r_outer = 45.0
        for i in range(3):
            start_deg = int(self.angle_outer + i * 120) * 16
            span_deg = 80 * 16
            painter.drawArc(QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2), start_deg, span_deg)

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
        text_x = 155
        font_title = QFont("Segoe UI", 15, QFont.Weight.Bold)
        font_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255, 245))
        painter.drawText(text_x, int(cy - 6), self.status_title)

        font_sub = QFont("Consolas", 10, QFont.Weight.DemiBold)
        font_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        painter.setFont(font_sub)
        painter.setPen(col)
        painter.drawText(text_x, int(cy + 18), self.status_subtitle)

        font_micro = QFont("Consolas", 8)
        painter.setFont(font_micro)
        painter.setPen(QColor(160, 190, 220, 180))
        painter.drawText(text_x, int(cy + 36), self.status_badge)
