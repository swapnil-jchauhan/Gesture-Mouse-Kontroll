"""
Threaded Camera Capture & MediaPipe Hand Tracking Engine.
Optimized for low-latency, high FPS, and noisy/low-light webcam robustness via CLAHE pre-processing.
"""

import threading
import time
from typing import Optional, Tuple, Any
import cv2
import numpy as np

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
    Dedicated worker thread capturing webcam frames and extracting 21 3D hand landmarks.
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
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        # MediaPipe Hands pipeline
        self.hands_detector = None
        if mp_hands:
            self.hands_detector = mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.65,
                min_tracking_confidence=0.65,
                model_complexity=1,
            )

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
        self.has_hand = False

    def start(self):
        """Initializes camera and launches background worker thread."""
        if self._running:
            return

        # DirectShow backend on Windows (cv2.CAP_DSHOW) allows instant initialization
        self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            # Fallback to default backend
            self._cap = cv2.VideoCapture(self.camera_index)

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        # Set buffer size to 1 to eliminate video queue lag
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

    def _enhance_frame(self, bgr_frame: np.ndarray) -> np.ndarray:
        """Applies CLAHE on luminance channel to rescue hand landmarks in dark rooms."""
        if not self.enhance_low_light:
            return bgr_frame
        try:
            lab = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = self.clahe.apply(l)
            enhanced_lab = cv2.merge((l, a, b))
            return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        except Exception:
            return bgr_frame

    def _worker_loop(self):
        """Continuously pulls frames, extracts landmarks, and updates state."""
        prev_time = time.perf_counter()
        frame_count = 0
        fps_timer = prev_time

        while self._running:
            if not self._cap or not self._cap.isOpened():
                time.sleep(0.05)
                continue

            success, frame = self._cap.read()
            if not success or frame is None:
                time.sleep(0.01)
                continue

            now = time.perf_counter()
            frame_count += 1
            if now - fps_timer >= 1.0:
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

            if self.hands_detector:
                results = self.hands_detector.process(rgb)
                if results.multi_hand_landmarks:
                    hand_detected = True
                    # Grab primary tracked hand
                    landmarks = results.multi_hand_landmarks[0].landmark

            # Thread-safe state update
            with self._lock:
                self.latest_landmarks = landmarks
                self.latest_frame = frame
                self.latest_timestamp = now
                self.has_hand = hand_detected

            # Slight sleep if no hand in frame to save CPU
            if not hand_detected:
                time.sleep(0.005)

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
