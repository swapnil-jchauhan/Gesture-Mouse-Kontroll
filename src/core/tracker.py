"""
Threaded Camera Capture & Dual-Engine Hand Tracking for Project Kontroll.
Combines:
- Engine A: MediaPipe HandLandmarker for 21 3D global anatomical landmarks.
- Engine B: Sub-Pixel Pyramidal Lucas-Kanade Optical Flow (Pillar 1) on full-resolution
  camera frames inside a 48x48 ROI around index fingertip.
"""

import threading
import time
from typing import Optional, Tuple, Any
import cv2
import numpy as np

from src.core.optical_flow import SubPixelOpticalFlowTracker

try:
    import mediapipe as mp
    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
except ImportError:
    mp = None
    mp_hands = None
    mp_draw = None


class HandTracker:
    """
    Dedicated worker thread capturing webcam frames and driving the Dual-Engine Tracking Pipeline.
    """

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        target_fps: int = 60,
        enhance_low_light: bool = True,
    ):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.target_fps = target_fps
        self.enhance_low_light = enhance_low_light

        # OpenCV CLAHE for low-light noise resilience
        self.clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))

        # MediaPipe Hands pipeline (Global Neural Engine)
        self.hands_detector = None
        if mp_hands:
            self.hands_detector = mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.60,
                min_tracking_confidence=0.60,
                model_complexity=0,
            )

        # Sub-Pixel Optical Flow Engine (Pillar 1)
        self.optical_flow = SubPixelOpticalFlowTracker(roi_size=48)

        # Threading & Shared State
        self._cap = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Output payload
        self.latest_landmarks = None
        self.latest_frame = None
        self.latest_timestamp = 0.0
        self.fps_metric = 0.0
        self.inference_time_ms = 0.0
        self.has_hand = False
        self.latest_optical_flow_delta: Tuple[float, float] = (0.0, 0.0)
        self.latest_fused_pt: Tuple[float, float] = (0.0, 0.0)

    def start(self):
        """Initializes camera and launches background worker thread."""
        if self._running:
            return

        # DirectShow backend on Windows (cv2.CAP_DSHOW) allows instant initialization
        self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            # Fallback to default backend
            self._cap = cv2.VideoCapture(self.camera_index)

        # Enable MJPG stream to unlock full hardware FPS without USB saturation
        try:
            self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        except Exception:
            pass

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        # Set buffer size to 1 to eliminate video queue latency
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops background tracking thread and releases camera."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        self.optical_flow.reset()

    def _enhance_frame(self, bgr_frame: np.ndarray) -> np.ndarray:
        """Applies CLAHE on luminance only if the scene is noticeably dark (< 75 mean brightness)."""
        if not self.enhance_low_light:
            return bgr_frame
        try:
            mean_b = np.mean(bgr_frame[::8, ::8, 0])
            if mean_b > 75.0:
                return bgr_frame

            lab = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = self.clahe.apply(l)
            enhanced_lab = cv2.merge((l, a, b))
            return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        except Exception:
            return bgr_frame

    def _worker_loop(self):
        """Continuously pulls frames, extracts landmarks, runs optical flow, and updates state."""
        frame_count = 0
        fps_timer = time.perf_counter()

        while self._running:
            if not self._cap or not self._cap.isOpened():
                time.sleep(0.05)
                continue

            success, frame = self._cap.read()
            if not success or frame is None:
                time.sleep(0.005)
                continue

            now = time.perf_counter()
            frame_count += 1
            if now - fps_timer >= 0.5:
                self.fps_metric = frame_count / (now - fps_timer)
                frame_count = 0
                fps_timer = now

            # Enhance low-light contrast if needed
            enhanced = self._enhance_frame(frame)

            # MediaPipe expects RGB
            rgb = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False

            landmarks = None
            hand_detected = False

            t_inf_start = time.perf_counter()
            if self.hands_detector:
                results = self.hands_detector.process(rgb)
                if results.multi_hand_landmarks:
                    hand_detected = True
                    landmarks = results.multi_hand_landmarks[0].landmark
            self.inference_time_ms = (time.perf_counter() - t_inf_start) * 1000.0

            # Dual-Engine: Optical Flow Refinement
            flow_dx, flow_dy = 0.0, 0.0
            fused_x, fused_y = 0.0, 0.0
            if hand_detected and landmarks:
                fh, fw = frame.shape[:2]
                idx_px = (landmarks[8].x * fw, landmarks[8].y * fh)
                flow_dx, flow_dy, fused_x, fused_y = self.optical_flow.update(
                    frame, idx_px, has_hand=True, timestamp=now
                )
            else:
                self.optical_flow.reset()

            # Thread-safe state update
            with self._lock:
                self.latest_landmarks = landmarks
                self.latest_frame = frame
                self.latest_timestamp = now
                self.has_hand = hand_detected
                self.latest_optical_flow_delta = (flow_dx, flow_dy)
                self.latest_fused_pt = (fused_x, fused_y)

            time.sleep(0.001)

    def get_latest_data(self) -> Tuple[Optional[Any], Optional[np.ndarray], float, bool, float]:
        """
        Thread-safe fetch of latest hand landmarks and raw frame.
        :return: (landmarks, frame, timestamp, has_hand, fps)
        """
        with self._lock:
            return (
                self.latest_landmarks,
                self.latest_frame,
                self.latest_timestamp,
                self.has_hand,
                self.fps_metric,
            )

    def get_optical_flow_delta(self) -> Tuple[float, float]:
        """Returns the latest sub-pixel optical flow displacement delta (dx, dy)."""
        with self._lock:
            return self.latest_optical_flow_delta
