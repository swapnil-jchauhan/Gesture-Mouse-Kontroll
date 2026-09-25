"""
3D Desk Homography & Perspective Un-Tilting for Project Kontroll.
Pillar 2: Computes 3D palm plane normal from landmarks and applies projective
homography transformation to un-warp the camera's angled line-of-sight onto the user's
physical flat desk plane. Moving the hand horizontally across the desk produces
true horizontal cursor movement on screen.
"""

import math
from typing import Optional, Tuple, Any, List
import numpy as np


class DeskHomography:
    """
    3D Desk Homography and Perspective Un-Tilter.
    Un-warps tilted and pitched camera perspectives (e.g. 35° side-monitor mounting)
    into a calibrated horizontal desktop coordinate space.
    """

    def __init__(self, mode: str = "center", default_tilt_deg: float = 35.0, pitch_deg: float = 0.0):
        """
        :param mode: 'center' (straight monitor/laptop), 'left' (tilted left monitor), 'right' (tilted right), 'auto'
        :param default_tilt_deg: Angle in degrees for tilted mounts (standard ~35°).
        :param pitch_deg: Downward pitch angle of monitor/webcam (standard 0°).
        """
        self.mode = mode
        self.default_tilt_deg = default_tilt_deg
        self.pitch_deg = pitch_deg
        self.estimated_tilt_deg = 0.0 if mode == "center" else default_tilt_deg
        self._ema_alpha = 0.05
        self._cached_matrix: Optional[np.ndarray] = None
        self._cached_angle: Optional[float] = None

    def set_mode(self, mode: str):
        if mode in ("left", "center", "right", "auto"):
            self.mode = mode
            self._cached_matrix = None

    @staticmethod
    def compute_palm_normal(landmarks) -> np.ndarray:
        """
        Computes the normalized 3D palm plane normal vector n from landmarks:
        Wrist (0), Index MCP (5), Pinky MCP (17).
        """
        w = landmarks[0]
        i_mcp = landmarks[5]
        p_mcp = landmarks[17]

        # Vector 1: Wrist -> Index MCP
        v1 = np.array([
            i_mcp.x - w.x,
            i_mcp.y - w.y,
            getattr(i_mcp, "z", 0.0) - getattr(w, "z", 0.0)
        ], dtype=np.float64)

        # Vector 2: Wrist -> Pinky MCP
        v2 = np.array([
            p_mcp.x - w.x,
            p_mcp.y - w.y,
            getattr(p_mcp, "z", 0.0) - getattr(w, "z", 0.0)
        ], dtype=np.float64)

        # Normal = v1 x v2
        normal = np.cross(v1, v2)
        norm_len = np.linalg.norm(normal)
        if norm_len < 1e-7:
            return np.array([0.0, 0.0, 1.0], dtype=np.float64)
        return normal / norm_len

    def estimate_camera_tilt(self, landmarks) -> float:
        """
        Estimates the camera's tilt angle in degrees based on 3D hand geometry.
        Clamped strictly to [-35.0, 35.0] to prevent axis inversion or runaway rotations.
        """
        if landmarks is None or len(landmarks) < 21:
            return 0.0 if self.mode == "center" else self.default_tilt_deg

        # Hand palm normal estimation
        normal = self.compute_palm_normal(landmarks)
        # MediaPipe camera coordinates: Z points into screen (away from camera).
        # A palm facing the camera has normal[2] < 0.
        # Projecting onto the horizontal plane relative to camera view:
        # atan2(normal[0], -normal[2]) gives 0.0° when facing straight at camera.
        yaw_rad = math.atan2(normal[0], -normal[2]) if abs(normal[2]) > 1e-4 else 0.0
        yaw_deg = math.degrees(yaw_rad)

        # Strictly clamp candidate tilt to physically plausible monitor mount angles [-35°, +35°]
        candidate_tilt = max(-35.0, min(35.0, yaw_deg))

        if abs(candidate_tilt) > 4.0:
            self.estimated_tilt_deg = (
                (1.0 - self._ema_alpha) * self.estimated_tilt_deg + self._ema_alpha * candidate_tilt
            )
        else:
            self.estimated_tilt_deg = (1.0 - self._ema_alpha) * self.estimated_tilt_deg

        return max(-35.0, min(35.0, self.estimated_tilt_deg))

    def get_effective_tilt_deg(self, landmarks=None) -> float:
        """Returns the active un-tilting angle in degrees based on current mode."""
        if self.mode == "left":
            return self.default_tilt_deg
        elif self.mode == "right":
            return -self.default_tilt_deg
        elif self.mode == "center":
            return 0.0
        elif self.mode == "auto":
            if landmarks:
                self.estimate_camera_tilt(landmarks)
            return max(-35.0, min(35.0, self.estimated_tilt_deg))
        return 0.0

    def get_homography_matrix(self, mode: Optional[str] = None, landmarks=None) -> np.ndarray:
        """
        Constructs the 3x3 projective homography transformation matrix that maps
        camera coordinates to calibrated desk plane coordinates.
        Un-tilts by R(-theta) and scales pitch.
        """
        active_mode = mode if mode is not None else self.mode
        if active_mode == "left":
            tilt_deg = self.default_tilt_deg
        elif active_mode == "right":
            tilt_deg = -self.default_tilt_deg
        elif active_mode == "center":
            tilt_deg = 0.0
        elif active_mode == "auto":
            tilt_deg = self.get_effective_tilt_deg(landmarks)
        else:
            tilt_deg = 0.0

        if self._cached_matrix is not None and self._cached_angle == tilt_deg:
            return self._cached_matrix

        theta = math.radians(tilt_deg)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        # Pitch compensation factor (vertical perspective foreshortening)
        pitch_rad = math.radians(self.pitch_deg)
        pitch_scale = 1.0 / max(0.2, math.cos(pitch_rad))

        # Projective un-tilting homography matrix (R(-theta) with pitch correction)
        # Maps camera frame vector [dx_cam, dy_cam, 1]^T to flat desk plane
        H = np.array([
            [cos_t, sin_t, 0.0],
            [-sin_t * pitch_scale, cos_t * pitch_scale, 0.0],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)

        self._cached_matrix = H
        self._cached_angle = tilt_deg
        return H

    def transform_vector(
        self,
        dx: float,
        dy: float,
        landmarks=None,
    ) -> Tuple[float, float]:
        """
        Transforms a 2D motion displacement vector from camera perspective to desk plane.
        A physical horizontal sweep at 35° camera yaw maps cleanly to a pure horizontal vector (dy ≈ 0).
        """
        H = self.get_homography_matrix(landmarks=landmarks)
        # Apply 2x2 linear portion of homography to motion vector
        dx_desk = float(H[0, 0] * dx + H[0, 1] * dy)
        dy_desk = float(H[1, 0] * dx + H[1, 1] * dy)

        # Numerical zero cleanup for near-zero orthogonal components
        if abs(dy_desk) < 1e-5:
            dy_desk = 0.0
        if abs(dx_desk) < 1e-5:
            dx_desk = 0.0

        return dx_desk, dy_desk

    def transform_point(
        self,
        norm_x: float,
        norm_y: float,
        landmarks=None,
        center: Tuple[float, float] = (0.5, 0.6),
    ) -> Tuple[float, float]:
        """
        Transforms a normalized point around a comfortable desk reference center.
        """
        cx, cy = center
        dx = norm_x - cx
        dy = norm_y - cy

        H = self.get_homography_matrix(landmarks=landmarks)
        # Apply transformation relative to center
        rx = float(H[0, 0] * dx + H[0, 1] * dy)
        ry = float(H[1, 0] * dx + H[1, 1] * dy)

        return cx + rx, cy + ry
