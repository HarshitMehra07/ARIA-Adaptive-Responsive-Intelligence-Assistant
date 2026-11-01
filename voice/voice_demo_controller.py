from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from voice.speech_output_service import SpeechOutputError
from voice.voice_input_service import VoiceInputCancelled
from voice.voice_state import VoiceInteractionState


logger = logging.getLogger(__name__)


VoiceDemoState = VoiceInteractionState


class VoiceDemoController:
    """Serializes text/voice requests and dispatches UI callbacks to its owner thread."""

    def __init__(
        self,
        aria,
        voice_input,
        speech_output,
        *,
        dispatch: Callable[[Callable[[], None]], None] | None = None,
        on_state: Callable[[VoiceDemoState], None] | None = None,
        on_transcript: Callable[[str], None] | None = None,
        on_response: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_speech_activity: Callable[[], None] | None = None,
        executor=None,
    ):
        self.aria = aria
        self.voice_input = voice_input
        self.speech_output = speech_output
        self._dispatch = dispatch or (lambda callback: callback())
        self._on_state = on_state or (lambda _state: None)
        self._on_transcript = on_transcript or (lambda _text: None)
        self._on_response = on_response or (lambda _text: None)
        self._on_status = on_status or (lambda _message: None)
        self._on_error = on_error or (lambda _message: None)
        self._on_speech_activity = on_speech_activity or (lambda: None)
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="aria-demo-request",
        )
        self._owns_executor = executor is None
        self._state = VoiceDemoState.IDLE
        self._lock = threading.RLock()
        self._cancel_event: threading.Event | None = None
        self._closed = False
        self._continuous = False
        self._listen_after_speech = False

    @property
    def state(self) -> VoiceDemoState:
        with self._lock:
            return self._state

    def start_listening(self) -> bool:
        with self._lock:
            if self._closed:
                return False
            if self._state is VoiceDemoState.SPEAKING:
                self._listen_after_speech = True
                should_stop_speaking = True
            elif self._state is VoiceDemoState.IDLE:
                should_stop_speaking = False
            else:
                return False
            if should_stop_speaking:
                cancel_event = None
            else:
                cancel_event = threading.Event()
                self._cancel_event = cancel_event
                self._set_state_locked(VoiceDemoState.LISTENING)
        if should_stop_speaking:
            try:
                return bool(self.speech_output.stop())
            except Exception:
                with self._lock:
                    self._listen_after_speech = False
                return False
        if cancel_event is None:
            return False
        try:
            future = self._executor.submit(
                self.voice_input.listen_once,
                cancel_event,
                self._recognition_status,
            )
        except RuntimeError:
            self._finish_with_error("Voice input could not be started. You can still type a request.")
            return False
        future.add_done_callback(
            lambda completed: self._dispatch(lambda: self._finish_listening(completed))
        )
        return True

    def set_continuous(self, enabled: bool) -> bool:
        with self._lock:
            if self._closed:
                return False
            if enabled and self._state not in {
                VoiceDemoState.IDLE,
                VoiceDemoState.LISTENING,
            }:
                return False
            self._continuous = bool(enabled)
            should_start = enabled and self._state is VoiceDemoState.IDLE
            should_cancel = not enabled and self._state is VoiceDemoState.LISTENING
        if should_cancel:
            self.cancel_listening()
        if should_start:
            return self.start_listening()
        return True

    def set_voice_persona(self, persona: str) -> bool:
        selector = getattr(self.speech_output, "select_persona", None)
        if selector is None:
            return persona in {"aria", "jarvis"}
        try:
            return bool(selector(persona))
        except Exception:
            return False

    def cancel_listening(self) -> bool:
        with self._lock:
            if self._state is not VoiceDemoState.LISTENING or self._cancel_event is None:
                return False
            self._continuous = False
            self._cancel_event.set()
        try:
            self.voice_input.cancel()
        except Exception:
            self._dispatch(
                lambda: self._on_error(
                    "Listening is stopping. If the microphone remains busy, close the demo window."
                )
            )
        return True

    def submit_text(self, text: str) -> bool:
        cleaned = (text or "").strip()
        if not cleaned:
            self._dispatch(lambda: self._on_error("Enter or speak a request first."))
            return False
        with self._lock:
            if self._closed or self._state is not VoiceDemoState.IDLE:
                return False
        self._begin_request(cleaned)
        return True

    def stop_speaking(self) -> bool:
        with self._lock:
            if self._state is not VoiceDemoState.SPEAKING:
                return False
        try:
            stopped = bool(self.speech_output.stop())
            if not stopped:
                with self._lock:
                    self._listen_after_speech = False
            return stopped
        except Exception:
            self._finish_with_error("Speech playback could not be stopped cleanly.")
            return False

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._continuous = False
            cancel_event = self._cancel_event
            if cancel_event is not None:
                cancel_event.set()
        try:
            self.voice_input.close()
        except Exception:
            pass
        try:
            self.speech_output.close()
        except Exception:
            pass
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _recognition_status(self, message: str) -> None:
        self._dispatch(lambda: self._on_status(message))

    def _finish_listening(self, future: Future) -> None:
        with self._lock:
            if self._closed or self._state is not VoiceDemoState.LISTENING:
                return
            was_cancelled = (
                self._cancel_event is not None and self._cancel_event.is_set()
            )
            self._cancel_event = None
            if was_cancelled:
                self._set_state_locked(VoiceDemoState.IDLE)
                return
        try:
            text = future.result()
        except VoiceInputCancelled:
            self._set_state(VoiceDemoState.IDLE)
            return
        except Exception:
            if self._continuous:
                with self._lock:
                    self._continuous = False
            logger.warning("[ARIA ERROR] Speech recognition failed.")
            self._finish_with_error(
                "Speech recognition failed. Check microphone permissions and network access, or type your request."
            )
            return
        if not isinstance(text, str) or not text.strip():
            with self._lock:
                repeat = self._continuous and not self._closed
            if repeat:
                self._set_state(VoiceDemoState.IDLE)
                self._on_status("No speech detected. Continuous listening is still on.")
                self.start_listening()
                return
            self._finish_with_error("No clear speech was recognized. Try again or type your request.")
            return
        logger.info("[ARIA INPUT] User speech received (%d characters).", len(text.strip()))
        self._begin_request(text.strip(), expected_state=VoiceDemoState.LISTENING)

    def _begin_request(
        self,
        text: str,
        *,
        expected_state: VoiceDemoState = VoiceDemoState.IDLE,
    ) -> None:
        with self._lock:
            if self._closed or self._state is not expected_state:
                return
            self._on_transcript(text)
            self._set_state_locked(VoiceDemoState.THINKING)
        logger.info("[ARIA BRAIN] Processing request.")
        try:
            future = self._executor.submit(self.aria.process_input, text)
        except RuntimeError:
            self._finish_with_error("ARIA could not start processing. Please try again.")
            return
        future.add_done_callback(
            lambda completed: self._dispatch(lambda: self._finish_processing(completed))
        )

    def _finish_processing(self, future: Future) -> None:
        with self._lock:
            if self._closed or self._state is not VoiceDemoState.THINKING:
                return
        try:
            response = future.result()
        except Exception as error:
            logger.warning("[ARIA ERROR] ARIA request failed (%s).", type(error).__name__)
            self._finish_with_error("ARIA could not complete the request. Please try again.")
            return
        if not isinstance(response, str) or not response.strip():
            logger.warning("[ARIA ERROR] ARIA returned an empty response.")
            self._finish_with_error("ARIA returned an empty response.")
            return
        logger.info("[ARIA RESPONSE] Response received (%d characters).", len(response.strip()))
        self._on_response(response)
        try:
            accepted = self.speech_output.speak(
                response,
                on_started=lambda: self._dispatch(self._speech_started),
                on_word=lambda: self._dispatch(self._speech_word),
                on_finished=lambda cancelled: self._dispatch(
                    lambda: self._speech_finished(cancelled)
                ),
                on_error=lambda message: self._dispatch(
                    lambda: self._finish_with_error(message)
                ),
            )
        except SpeechOutputError as error:
            self._finish_with_error(str(error))
            return
        except Exception as error:
            logger.error("[ARIA ERROR] TTS request failed (%s).", type(error).__name__)
            accepted = False
        if not accepted:
            self._finish_with_error(
                "Speech output is unavailable. ARIA's response is visible; check the local TTS installation and audio device."
            )

    def _speech_started(self) -> None:
        with self._lock:
            if not self._closed and self._state is VoiceDemoState.THINKING:
                self._set_state_locked(VoiceDemoState.SPEAKING)

    def _speech_word(self) -> None:
        self._on_speech_activity()

    def _speech_finished(self, _cancelled: bool) -> None:
        with self._lock:
            listen_again = (
                not self._closed
                and (
                    self._listen_after_speech
                    or self._continuous
                )
            )
            self._listen_after_speech = False
            if self._state is VoiceDemoState.SPEAKING:
                self._set_state_locked(VoiceDemoState.IDLE)
            elif self._state is VoiceDemoState.THINKING:
                self._set_state_locked(VoiceDemoState.IDLE)
        if listen_again:
            self.start_listening()

    def _finish_with_error(self, message: str) -> None:
        with self._lock:
            if self._closed:
                return
            logger.warning("[ARIA ERROR] Voice interaction returned to idle after an error.")
            self._continuous = False
            self._on_error(message)
            if self._state is not VoiceDemoState.IDLE:
                self._set_state_locked(VoiceDemoState.IDLE)
            self._cancel_event = None

    def _set_state(self, state: VoiceDemoState) -> None:
        with self._lock:
            if not self._closed:
                self._set_state_locked(state)

    def _set_state_locked(self, state: VoiceDemoState) -> None:
        self._state = state
        self._on_state(state)
