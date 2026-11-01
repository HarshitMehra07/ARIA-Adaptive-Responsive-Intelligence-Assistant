from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

from automation.windows_backend import WindowsDesktopBackend


@dataclass(frozen=True)
class ScreenObservation:
    window_title: str
    bounds: tuple[int, int, int, int]
    image_width: int
    image_height: int
    image_digest: str
    visible_elements: list[dict[str, str]]
    captured_at: float


class ScreenService:
    """Explicit, in-memory screen observation backed by Windows UI Automation."""

    def __init__(self, desktop: WindowsDesktopBackend | None = None):
        self.desktop = desktop if desktop is not None else WindowsDesktopBackend()

    def capture_screenshot(self) -> ScreenObservation:
        return self.observe()

    def observe(self) -> ScreenObservation:
        capture = self.desktop.capture_active_window()
        digest_source = capture.image.copy()
        digest_source.thumbnail((320, 320))
        image_digest = hashlib.sha256(digest_source.tobytes()).hexdigest()
        elements = self.desktop.visible_elements(maximum=100)
        return ScreenObservation(
            window_title=capture.window.title,
            bounds=capture.window.bounds or (0, 0, capture.width, capture.height),
            image_width=capture.width,
            image_height=capture.height,
            image_digest=image_digest,
            visible_elements=elements,
            captured_at=time.monotonic(),
        )

    @staticmethod
    def analyze_activity() -> dict[str, Any]:
        """Do not inspect the screen on the runtime's periodic background loop."""
        return {
            "status": "idle",
            "active_window": None,
            "activity_type": "not_observed",
            "confidence": 0.0,
            "message": "Screen observation requires an explicit user request.",
        }
