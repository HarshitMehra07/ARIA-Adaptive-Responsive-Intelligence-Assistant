from __future__ import annotations

import time
import threading
from typing import Any


class VisionServiceError(Exception):
    """A safe, user-presentable camera or local face-detection error."""


class VisionService:
    """Consent-gated local face detection; frames are never retained or uploaded."""

    def __init__(self, *, capture_factory=None, classifier_factory=None):
        self.cap = None
        self.is_active = False
        self.last_error = None
        self._capture_factory = capture_factory
        self._classifier_factory = classifier_factory
        self._classifier = None
        self._lock = threading.RLock()

    @staticmethod
    def dependencies_available() -> bool:
        import importlib.util

        return importlib.util.find_spec("cv2") is not None

    def start(self, *, consent: bool = False, camera_index: int = 0) -> bool:
        if not consent:
            raise PermissionError("Camera access requires explicit user consent.")
        with self._lock:
            return self._start(camera_index)

    def _start(self, camera_index: int) -> bool:
        if self.is_active:
            return True
        try:
            import cv2

            capture_factory = self._capture_factory or cv2.VideoCapture
            classifier_factory = self._classifier_factory or cv2.CascadeClassifier
            capture = capture_factory(camera_index)
            if not capture.isOpened():
                capture.release()
                self.last_error = "The selected camera could not be opened."
                return False
            classifier = classifier_factory(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            if hasattr(classifier, "empty") and classifier.empty():
                capture.release()
                self.last_error = "The local face-detection model is unavailable."
                return False
            self.cap = capture
            self._classifier = classifier
            self.is_active = True
            self.last_error = None
            return True
        except ImportError as error:
            self.last_error = "Local camera analysis requires the optional OpenCV package."
            raise VisionServiceError(self.last_error) from error
        except VisionServiceError:
            raise
        except Exception as error:
            self.last_error = "The camera could not be started. Check camera permissions and device availability."
            raise VisionServiceError(self.last_error) from error

    def capture_frame(self):
        """Return one transient frame to a local caller; the service never stores it."""
        with self._lock:
            if not self.is_active or self.cap is None:
                return None
            success, frame = self.cap.read()
            return frame if success else None

    def analyze_scene(self) -> dict[str, Any]:
        with self._lock:
            return self._analyze_scene()

    def _analyze_scene(self) -> dict[str, Any]:
        if not self.is_active:
            return {
                "status": "disabled",
                "face_count": 0,
                "user_identity": "not_recognized",
                "emotion": "unknown",
                "emotion_confidence": 0.0,
                "timestamp": time.time(),
            }
        frame = self.capture_frame()
        if frame is None:
            self.last_error = "A camera frame could not be read."
            return {
                "status": "unavailable",
                "face_count": 0,
                "user_identity": "not_recognized",
                "emotion": "unknown",
                "emotion_confidence": 0.0,
                "timestamp": time.time(),
            }

        try:
            import cv2

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._classifier.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(40, 40),
            )
            return {
                "status": "analyzed",
                "face_count": len(faces),
                "user_identity": "not_recognized",
                "emotion": "unknown",
                "emotion_confidence": 0.0,
                "timestamp": time.time(),
            }
        except Exception as error:
            self.last_error = "Local face detection failed."
            raise VisionServiceError(self.last_error) from error
        finally:
            del frame

    def stop(self) -> None:
        with self._lock:
            capture, self.cap = self.cap, None
            self._classifier = None
            self.is_active = False
            if capture is not None:
                capture.release()
