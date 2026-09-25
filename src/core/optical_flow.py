"""
Sub-Pixel Pyramidal Lucas-Kanade Optical Flow Refinement for Project Kontroll.
Pillar 1: Meta Orion and Apple Vision Pro level laser mouse stillness.
Extracts a 48x48 ROI around the index fingertip on full-resolution camera frames,
computes sub-pixel displacement vectors, guarantees exact (0.00, 0.00) px delta
when stationary, and anchors against low-frequency neural landmark drift.
"""

import math
import time
from typing import Optional, Tuple, List
import cv2
import numpy as np


class SubPixelOpticalFlowTracker:
    """
    Sub-Pixel Pyramidal Lucas-Kanade Optical Flow Tracker.
    Operates on full-resolution camera frames within a 48x48 ROI around the index fingertip.
    Guarantees zero jitter when hand is physically held stationary.
    """

    def __init__(
        self,
        roi_size: int = 48,
        max_corners: int = 20,
        quality_level: float = 0.02,
        min_distance: float = 4.0,
        stillness_threshold: float = 0.40,
        drift_correction_gain: float = 0.04,
        reanchor_interval: int = 35,
    ):
        self.roi_size = roi_size
        self.max_corners = max_corners
        self.quality_level = quality_level
        self.min_distance = min_distance
        self.stillness_threshold = stillness_threshold
        self.drift_correction_gain = drift_correction_gain
        self.reanchor_interval = reanchor_interval

        # Tracking state
        self.prev_gray: Optional[np.ndarray] = None
        self.prev_pts: Optional[np.ndarray] = None
        self.accumulated_pos: Optional[Tuple[float, float]] = None
        self.frame_counter: int = 0
        self.is_initialized: bool = False
        self.last_displacement: Tuple[float, float] = (0.0, 0.0)
        self.last_timestamp: float = 0.0
        self.active_features_count: int = 0
        self.is_still: bool = True

    def reset(self):
        """Resets tracking state when hand is lost or system resets."""
        self.prev_gray = None
        self.prev_pts = None
        self.accumulated_pos = None
        self.frame_counter = 0
        self.is_initialized = False
        self.last_displacement = (0.0, 0.0)
        self.last_timestamp = 0.0
        self.active_features_count = 0
        self.is_still = True

    def _extract_features_in_roi(self, gray: np.ndarray, center_pt: Tuple[float, float]) -> np.ndarray:
        """
        Extracts Shi-Tomasi corners or high-contrast skin features within the 48x48 ROI.
        Falls back to a dense sub-pixel regular grid if natural skin corners are sparse.
        """
        h, w = gray.shape[:2]
        cx, cy = center_pt
        half = self.roi_size // 2

        x1 = max(0, min(w - self.roi_size, int(round(cx - half))))
        y1 = max(0, min(h - self.roi_size, int(round(cy - half))))
        x2 = min(w, x1 + self.roi_size)
        y2 = min(h, y1 + self.roi_size)

        roi = gray[y1:y2, x1:x2]

        corners = cv2.goodFeaturesToTrack(
            roi,
            maxCorners=self.max_corners,
            qualityLevel=self.quality_level,
            minDistance=self.min_distance,
        )

        pts_list: List[Tuple[float, float]] = []
        if corners is not None and len(corners) >= 4:
            for c in corners:
                pts_list.append((float(c[0][0] + x1), float(c[0][1] + y1)))
        else:
            # Fallback to high-reliability 3x3 anchored sub-pixel skin grid
            step = self.roi_size / 4.0
            for i in range(1, 4):
                for j in range(1, 4):
                    pts_list.append((float(x1 + i * step), float(y1 + j * step)))

        pts_arr = np.array(pts_list, dtype=np.float32).reshape(-1, 1, 2)
        return pts_arr

    def update(
        self,
        frame: np.ndarray,
        landmark_pixel_pos: Optional[Tuple[float, float]],
        has_hand: bool = True,
        timestamp: Optional[float] = None,
    ) -> Tuple[float, float, float, float]:
        """
        Processes camera frame with Sub-Pixel Optical Flow.
        :param frame: Full-resolution camera frame (BGR or Grayscale).
        :param landmark_pixel_pos: Index fingertip (x, y) in camera pixel coordinates.
        :param has_hand: Hand detection presence flag.
        :param timestamp: Frame timestamp.
        :return: (dx, dy, fused_x, fused_y)
                 When physically stationary, dx and dy are guaranteed to be (0.00, 0.00).
        """
        now = timestamp if timestamp is not None else time.perf_counter()

        if not has_hand or landmark_pixel_pos is None or frame is None:
            self.reset()
            return 0.0, 0.0, 0.0, 0.0

        lx, ly = float(landmark_pixel_pos[0]), float(landmark_pixel_pos[1])
        if math.isnan(lx) or math.isnan(ly):
            self.reset()
            return 0.0, 0.0, 0.0, 0.0

        # Convert to single-channel 8-bit grayscale
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # First frame or re-initialization
        if (
            not self.is_initialized
            or self.prev_gray is None
            or self.prev_pts is None
            or len(self.prev_pts) < 4
        ):
            self.prev_pts = self._extract_features_in_roi(gray, (lx, ly))
            self.prev_gray = gray.copy()
            self.accumulated_pos = (lx, ly)
            self.is_initialized = True
            self.frame_counter = 1
            self.last_displacement = (0.0, 0.0)
            self.last_timestamp = now
            self.active_features_count = len(self.prev_pts)
            self.is_still = True
            return 0.0, 0.0, lx, ly

        # Pyramidal Lucas-Kanade Optical Flow (3 pyramid levels, 15x15 window)
        lk_params = dict(
            winSize=(15, 15),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.02),
        )

        curr_pts, status, err = cv2.calcOpticalFlowPyrLK(
            self.prev_gray, gray, self.prev_pts, None, **lk_params
        )

        good_curr = []
        good_prev = []
        half_roi = float(self.roi_size) * 0.75
        if curr_pts is not None and status is not None:
            for i, st in enumerate(status.flatten()):
                if st == 1:
                    c_pt = curr_pts[i][0]
                    p_pt = self.prev_pts[i][0]
                    # Discard points outside the index fingertip ROI
                    if abs(c_pt[0] - lx) <= half_roi and abs(c_pt[1] - ly) <= half_roi:
                        good_curr.append(c_pt)
                        good_prev.append(p_pt)

        if len(good_curr) < 3:
            # Feature tracking lost or fast swipe outside 48x48 ROI:
            # Fall back to neural landmark displacement so fast gestures and flicks never freeze
            prev_x, prev_y = self.accumulated_pos if self.accumulated_pos else (lx, ly)
            dx_fallback = lx - prev_x
            dy_fallback = ly - prev_y
            disp_fallback = math.hypot(dx_fallback, dy_fallback)

            self.prev_pts = self._extract_features_in_roi(gray, (lx, ly))
            self.prev_gray = gray.copy()
            self.accumulated_pos = (lx, ly)
            self.active_features_count = len(self.prev_pts)

            if disp_fallback < self.stillness_threshold:
                self.last_displacement = (0.0, 0.0)
                self.is_still = True
                return 0.0, 0.0, lx, ly
            else:
                self.last_displacement = (dx_fallback, dy_fallback)
                self.is_still = False
                return dx_fallback, dy_fallback, lx, ly

        curr_arr = np.array(good_curr, dtype=np.float32)
        prev_arr = np.array(good_prev, dtype=np.float32)
        deltas = curr_arr - prev_arr

        # Robust spatial median displacement across feature points inside the fingertip ROI
        dx_flow = float(np.median(deltas[:, 0]))
        dy_flow = float(np.median(deltas[:, 1]))
        disp_mag = math.hypot(dx_flow, dy_flow)

        # Laser Mouse Stillness Deadband:
        # Micro-tremors below stillness_threshold produce identically (0.00, 0.00) px displacement.
        if disp_mag < self.stillness_threshold:
            dx_final = 0.0
            dy_final = 0.0
            self.is_still = True
        else:
            dx_final = dx_flow
            dy_final = dy_flow
            self.is_still = False

        # Inlier filtering: discard outliers that deviate from spatial median
        inlier_pts = []
        for i in range(len(curr_arr)):
            pt = curr_arr[i]
            d = deltas[i]
            if (abs(d[0] - dx_flow) <= 3.5) and (abs(d[1] - dy_flow) <= 3.5):
                inlier_pts.append(pt)

        # Integrate displacement with low-frequency drift anchoring
        prev_pos_x, prev_pos_y = self.accumulated_pos if self.accumulated_pos else (lx, ly)
        curr_pos_x = prev_pos_x + dx_final
        curr_pos_y = prev_pos_y + dy_final

        # Drift correction towards neural landmark anchor
        dist_to_anchor = math.hypot(curr_pos_x - lx, curr_pos_y - ly)
        if not self.is_still:
            # During motion, gently blend towards the neural anchor to prevent unbounded drift
            curr_pos_x += (lx - curr_pos_x) * self.drift_correction_gain
            curr_pos_y += (ly - curr_pos_y) * self.drift_correction_gain
        else:
            # If still for a long time but landmark drifted significantly (> 20 px), pull back slowly
            if dist_to_anchor > 20.0:
                curr_pos_x += (lx - curr_pos_x) * 0.05
                curr_pos_y += (ly - curr_pos_y) * 0.05

        self.accumulated_pos = (curr_pos_x, curr_pos_y)
        self.last_displacement = (dx_final, dy_final)
        self.last_timestamp = now
        self.frame_counter += 1
        self.active_features_count = len(inlier_pts) if inlier_pts else len(good_curr)

        # Re-anchor feature points periodically or if inlier count drops or drifts
        if (
            self.frame_counter % self.reanchor_interval == 0
            or len(inlier_pts) < 6
            or dist_to_anchor > 20.0
        ):
            # Ground-truth neural landmark re-anchoring
            self.accumulated_pos = (lx, ly)
            self.prev_pts = self._extract_features_in_roi(gray, (lx, ly))
        else:
            self.prev_pts = np.array(inlier_pts, dtype=np.float32).reshape(-1, 1, 2)

        self.prev_gray = gray.copy()

        return dx_final, dy_final, curr_pos_x, curr_pos_y
