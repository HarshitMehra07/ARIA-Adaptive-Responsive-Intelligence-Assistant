from __future__ import annotations

import threading

from voice.speech_output_service import SpeechOutputService
from voice.voice_input_service import VoiceInputService


class VoiceService:
    """Compatibility facade that never opens the microphone during construction."""

    def __init__(
        self,
        *,
        input_service: VoiceInputService | None = None,
        output_service: SpeechOutputService | None = None,
    ):
        self.input_service = input_service or VoiceInputService()
        self.output_service = output_service or SpeechOutputService()
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._cancel_event: threading.Event | None = None
        self._error = None

    def speak(self, text: str):
        if not self.output_service.is_ready:
            self.output_service.start(
                on_ready=lambda _voices: self._ready.set(),
                on_error=self._set_error,
            )
            self._ready.wait(timeout=5)
        if self._error:
            raise RuntimeError(self._error)
        if not self.output_service.is_ready:
            raise RuntimeError("Local speech output is not available.")
        if not self.output_service.speak(text):
            raise RuntimeError("Local speech output is busy or could not start.")

    def listen(self) -> str:
        """Capture one user-requested utterance; no listening continues in the background."""
        cancel_event = threading.Event()
        with self._lock:
            if self._cancel_event is not None:
                raise RuntimeError("Voice input is already active.")
            self._cancel_event = cancel_event
        try:
            return self.input_service.listen_once(cancel_event)
        finally:
            with self._lock:
                self._cancel_event = None

    def close(self):
        with self._lock:
            if self._cancel_event is not None:
                self._cancel_event.set()
        self.output_service.close()

    def _set_error(self, message: str):
        self._error = message
        self._ready.set()
