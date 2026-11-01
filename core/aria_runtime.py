from __future__ import annotations

import threading
import time

from assistant.ambient_mode import AmbientDecision, AmbientMode
from core.aria_core import AriaCore
from vision.vision_service import VisionService
from voice.voice_service import VoiceService


class AriaRuntime:
    """Orchestrate ARIA services without activating sensors during startup."""

    def __init__(self):
        self.aria = AriaCore()
        self.vision = VisionService()
        self.voice = VoiceService()
        self.ambient = AmbientMode()
        self.is_running = False
        self._ambient_started_at: float | None = None

    def start(self):
        self.is_running = True
        print("ARIA Unified Runtime: Started. Sensors and ambient mode are off.")
        try:
            while self.is_running:
                time.sleep(0.25)
        except KeyboardInterrupt:
            self.stop()

    def enable_vision(self, *, consent: bool = False) -> bool:
        return self.vision.start(consent=consent)

    def disable_vision(self) -> None:
        self.vision.stop()

    def enable_ambient(self, *, permissions: set[str]) -> None:
        self.ambient.enable(permissions=permissions)
        self._ambient_started_at = time.monotonic()

    def disable_ambient(self) -> None:
        self.ambient.disable()
        self._ambient_started_at = None

    def evaluate_ambient(self) -> AmbientDecision:
        if self._ambient_started_at is None:
            return self.ambient.evaluate({})
        focused_minutes = int((time.monotonic() - self._ambient_started_at) / 60)
        return self.ambient.evaluate({"focused_minutes": focused_minutes})

    def process_voice_once(self) -> str:
        """Capture one explicitly requested utterance and route it through ARIA."""
        request = self.voice.listen()
        if not request.strip():
            return ""
        response = self.aria.process_input(request)
        self.voice.speak(response)
        return response

    def stop(self):
        self.is_running = False
        self.disable_vision()
        self.disable_ambient()
        self.voice.close()
        print("ARIA Unified Runtime: Stopped.")


if __name__ == "__main__":
    AriaRuntime().start()
