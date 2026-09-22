"""
Windows System Tray Controller for Project Kontroll.
Uses PyQt6 QSystemTrayIcon for seamless integration with Windows 11 notification area.
Provides autostart toggling, calibration launch, and status monitoring.
"""

from typing import Optional, Callable
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from src.service.autostart import is_autostart_enabled, enable_autostart, disable_autostart


def create_tray_icon_pixmap(is_active: bool = True) -> QPixmap:
    """Generates a crisp, high-DPI cyber-reactor system tray icon."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    center = size / 2.0
    color = QColor(0, 240, 255) if is_active else QColor(255, 170, 0)

    # Outer hex / ring
    pen = QPen(color, 4)
    painter.setPen(pen)
    painter.drawEllipse(6, 6, size - 12, size - 12)

    # Inner core
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    core_size = 18 if is_active else 12
    painter.drawEllipse(int(center - core_size / 2), int(center - core_size / 2), core_size, core_size)

    # 3 Arc ticks
    painter.setPen(QPen(QColor(255, 255, 255, 220), 3))
    painter.drawArc(12, 12, size - 24, size - 24, 45 * 16, 45 * 16)
    painter.drawArc(12, 12, size - 24, size - 24, 165 * 16, 45 * 16)
    painter.drawArc(12, 12, size - 24, size - 24, 285 * 16, 45 * 16)

    painter.end()
    return pixmap


class SystemTrayManager:
    """
    Manages the Windows 11 Taskbar System Tray icon, menu, and state.
    """

    def __init__(
        self,
        on_toggle_active: Callable[[], None],
        on_open_calibration: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        self.on_toggle_active = on_toggle_active
        self.on_open_calibration = on_open_calibration
        self.on_exit = on_exit

        self.tray_icon = QSystemTrayIcon()
        self.is_active = True

        self._build_menu()
        self.update_state(True)
        self.tray_icon.show()

    def _build_menu(self):
        self.menu = QMenu()
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #0d131f;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                padding: 6px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1e3a5f;
                color: #00f0ff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #1e293b;
                margin: 4px 8px;
            }
        """)

        # Header Title
        self.header_action = self.menu.addAction("PROJECT KONTROLL // AR MOUSE")
        self.header_action.setEnabled(False)

        self.menu.addSeparator()

        # Status Action
        self.status_action = self.menu.addAction("● Status: Active")
        self.status_action.triggered.connect(self.on_toggle_active)

        # Calibration
        self.calib_action = self.menu.addAction("Launch Calibration & Diagnostics")
        self.calib_action.triggered.connect(self.on_open_calibration)

        self.menu.addSeparator()

        # Run on Startup Toggle
        self.startup_action = self.menu.addAction("Run on Windows Startup")
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(is_autostart_enabled())
        self.startup_action.triggered.connect(self._toggle_autostart)

        self.menu.addSeparator()

        # Exit
        self.exit_action = self.menu.addAction("Exit Kontroll")
        self.exit_action.triggered.connect(self.on_exit)

        self.tray_icon.setContextMenu(self.menu)

    def _toggle_autostart(self, checked: bool):
        if checked:
            enable_autostart()
        else:
            disable_autostart()
        self.startup_action.setChecked(is_autostart_enabled())

    def update_state(self, is_active: bool):
        """Updates tray icon visual state and tooltip."""
        self.is_active = is_active
        pixmap = create_tray_icon_pixmap(is_active)
        self.tray_icon.setIcon(QIcon(pixmap))

        if is_active:
            self.status_action.setText("● Status: Active (Tracking ON)")
            self.tray_icon.setToolTip("Project Kontroll: ONLINE (Index-Tap to Click, Super-Gesture to Standby)")
        else:
            self.status_action.setText("○ Status: Standby (Paused)")
            self.tray_icon.setToolTip("Project Kontroll: STANDBY (Use Super-Gesture 👌 to activate)")
