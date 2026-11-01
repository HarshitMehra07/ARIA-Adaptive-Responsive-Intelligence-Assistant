from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from memory.memory_manager import contains_secret


logger = logging.getLogger(__name__)


class SpeechOutputError(Exception):
    """A safe, user-presentable local speech-output error."""


@dataclass(frozen=True)
class SpeechVoice:
    voice_id: str
    name: str
    gender: str = "unknown"


_INTERNAL_RESPONSE = re.compile(
    r"\b(?:api[_ -]?key|tavily_api_key|authentication failed|cloud model request timed out|"
    r"provider is unavailable|rate limit|configured cloud model)\b",
    re.IGNORECASE,
)


def is_speakable_response(text: object) -> bool:
    return (
        isinstance(text, str)
        and bool(text.strip())
        and not contains_secret(text)
        and not _INTERNAL_RESPONSE.search(text)
    )


class SpeechOutputService:
    """Local pyttsx3 output, confined to a worker thread with an interruptible loop."""

    def __init__(
        self,
        *,
        engine_factory=None,
        frame_interval: float = 0.01,
    ):
        self._engine_factory = engine_factory or _create_engine
        self._frame_interval = max(0.005, min(frame_interval, 0.05))
        self._commands: queue.Queue[tuple] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._ready = False
        self._closed = False
        self._pending = False
        self._on_started = None
        self._on_word = None
        self._on_finished = None
        self._on_error = None
        self._voices: tuple[SpeechVoice, ...] = ()
        self._selected_voice: str | None = None
        self._voice_persona = "aria"

    @property
    def voices(self) -> tuple[SpeechVoice, ...]:
        with self._lock:
            return self._voices

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._ready and not self._closed

    @property
    def selected_voice_id(self) -> str | None:
        with self._lock:
            return self._selected_voice

    @property
    def voice_persona(self) -> str:
        with self._lock:
            return self._voice_persona

    def start(
        self,
        *,
        on_ready: Callable[[tuple[SpeechVoice, ...]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        with self._lock:
            if self._closed:
                if on_error:
                    on_error("Speech output has been closed.")
                return
            if self._thread is not None:
                return
            self._startup_error_callback = on_error
            self._ready_callback = on_ready
            self._thread = threading.Thread(
                target=self._worker,
                name="aria-local-speech",
                daemon=True,
            )
            self._thread.start()

    def speak(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        on_started: Callable[[], None] | None = None,
        on_word: Callable[[], None] | None = None,
        on_finished: Callable[[bool], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> bool:
        if not is_speakable_response(text):
            logger.warning("[ARIA TTS] Request skipped because the response is empty or unsafe.")
            if on_error:
                on_error(
                    "Speech was skipped because the response is empty, contains a secret, or reports an internal service error."
                )
            return False
        with self._lock:
            if not self._ready or self._closed or self._pending:
                reason = (
                    "not ready"
                    if not self._ready
                    else "closed"
                    if self._closed
                    else "already speaking"
                )
                logger.warning("[ARIA TTS] Request rejected: speech service is %s.", reason)
                return False
            self._pending = True
            self._on_started = on_started
            self._on_word = on_word
            self._on_finished = on_finished
            self._on_error = on_error
            self._commands.put(
                ("speak", text, voice_id or self._selected_voice, self._voice_persona)
            )
        logger.debug("[ARIA TTS] Response queued.")
        return True

    def select_voice(self, voice_id: str | None) -> bool:
        with self._lock:
            if not self._ready or self._closed:
                return False
            if voice_id is not None and voice_id not in {voice.voice_id for voice in self._voices}:
                return False
            self._selected_voice = voice_id
            return True

    def select_persona(self, persona: str) -> bool:
        persona = str(persona or "").strip().casefold()
        if persona not in {"aria", "jarvis"}:
            return False
        with self._lock:
            if not self._ready or self._closed:
                return False
            desired_gender = "female" if persona == "aria" else "male"
            voice = next(
                (item for item in self._voices if item.gender == desired_gender),
                None,
            )
            self._voice_persona = persona
            self._selected_voice = voice.voice_id if voice else None
            return True

    def stop(self) -> bool:
        with self._lock:
            if not self._pending or self._closed:
                return False
            self._commands.put(("stop",))
            return True

    def close(self, *, timeout: float = 2.0) -> None:
        with self._lock:
            if self._closed:
                thread = self._thread
            else:
                self._closed = True
                thread = self._thread
                if thread is not None:
                    self._commands.put(("close",))
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))

    def _worker(self) -> None:
        engine = None
        active = False

        def finish_active(completed: bool) -> None:
            nonlocal active
            if not active:
                return
            active = False
            self._finished(completed)

        def fail_active(error) -> None:
            nonlocal active
            if not active:
                return
            active = False
            logger.error(
                "[ARIA ERROR] TTS engine error (%s): %s",
                type(error).__name__,
                error,
            )
            self._failed("The local speech engine failed during playback.")

        def finish_from_engine(*args, **kwargs) -> None:
            completed = kwargs.get("completed")
            if completed is None and len(args) > 1:
                completed = args[1]
            finish_active(bool(completed))

        def fail_from_engine(*args, **kwargs) -> None:
            error = kwargs.get("exception")
            if error is None and args:
                error = args[-1]
            if error is None:
                error = RuntimeError("The speech engine reported an unspecified playback error.")
            fail_active(error)

        try:
            engine = self._engine_factory()
            voices = tuple(
                SpeechVoice(
                    str(voice.id),
                    str(voice.name),
                    _voice_gender(voice),
                )
                for voice in engine.getProperty("voices")
                if getattr(voice, "id", None)
            )
            engine.connect("started-utterance", lambda **_event: self._started())
            engine.connect("started-word", lambda **_event: self._word())
            engine.connect("finished-utterance", finish_from_engine)
            engine.connect("error", fail_from_engine)
            engine.startLoop(False)
            with self._lock:
                self._voices = voices
                if self._voice_persona == "aria":
                    aria_voice = next(
                        (voice for voice in voices if voice.gender == "female"),
                        None,
                    )
                    self._selected_voice = aria_voice.voice_id if aria_voice else None
                self._ready = True
                ready_callback = self._ready_callback
            if ready_callback:
                ready_callback(voices)

            closing = False
            while not closing:
                try:
                    command = self._commands.get(timeout=self._frame_interval)
                except queue.Empty:
                    command = None

                if command:
                    if command[0] == "close":
                        closing = True
                    elif command[0] == "stop" and active:
                        engine.stop()
                        finish_active(False)
                    elif command[0] == "speak" and not active:
                        _, text, voice_id, persona = command
                        try:
                            engine.setProperty("rate", 175 if persona == "aria" else 145)
                            if voice_id:
                                engine.setProperty("voice", voice_id)
                            active = True
                            engine.say(text)
                        except Exception as error:
                            active = False
                            logger.error(
                                "[ARIA ERROR] TTS could not start playback (%s).",
                                type(error).__name__,
                            )
                            self._failed("The local speech engine could not start playback.")
                if closing:
                    break
                engine.iterate()
                time.sleep(self._frame_interval)
        except Exception as error:
            logger.error("[ARIA ERROR] TTS worker failed (%s).", type(error).__name__)
            self._startup_failed()
        finally:
            with self._lock:
                self._ready = False
            if engine is not None:
                try:
                    engine.stop()
                    engine.endLoop()
                except Exception:
                    pass
            with self._lock:
                had_pending = self._pending
            if had_pending:
                self._finished(False)

    def _started(self) -> None:
        logger.info("[ARIA TTS] Starting speech.")
        with self._lock:
            callback = self._on_started
        if callback:
            callback()

    def _word(self) -> None:
        with self._lock:
            callback = self._on_word
        if callback:
            callback()

    def _finished(self, completed: bool) -> None:
        logger.info(
            "[ARIA TTS] Speech %s.",
            "completed" if completed else "stopped before completion",
        )
        with self._lock:
            callback = self._on_finished
            self._pending = False
            self._on_started = None
            self._on_word = None
            self._on_finished = None
            self._on_error = None
        if callback:
            callback(not completed)

    def _failed(self, message: str) -> None:
        logger.error("[ARIA ERROR] TTS error: %s", message)
        with self._lock:
            callback = self._on_error
            self._pending = False
            self._on_started = None
            self._on_word = None
            self._on_finished = None
            self._on_error = None
        if callback:
            callback(message)

    def _startup_failed(self) -> None:
        with self._lock:
            self._ready = False
            startup_callback = getattr(self, "_startup_error_callback", None)
            pending_callback = self._on_error
            self._pending = False
            self._on_error = None
            self._on_finished = None
        message = "Local speech output is unavailable. Check that Windows has an installed voice and audio output device."
        logger.error("[ARIA ERROR] TTS initialization failed.")
        if startup_callback:
            startup_callback(message)
        if pending_callback:
            pending_callback(message)


def _create_engine():
    try:
        import pyttsx3
    except ImportError as error:
        raise SpeechOutputError(
            "Speech output is unavailable. Install the optional local TTS dependency; the response remains visible."
        ) from error
    return pyttsx3.init()


def _voice_gender(voice) -> str:
    metadata = str(getattr(voice, "gender", "") or "").casefold()
    if "female" in metadata:
        return "female"
    if "male" in metadata:
        return "male"

    identity = f"{getattr(voice, 'name', '')} {getattr(voice, 'id', '')}".casefold()
    tokens = set(re.findall(r"[a-z]+", identity))
    if tokens & {"female", "zira", "hazel", "susan", "helen", "jenny", "samantha", "eva", "sara"}:
        return "female"
    if tokens & {"male", "david", "mark", "guy", "james", "george", "ryan", "richard", "tony", "eric"}:
        return "male"
    return "unknown"
