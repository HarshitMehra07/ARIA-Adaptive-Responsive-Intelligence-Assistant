from __future__ import annotations

import array
import importlib.util
import logging
import threading
import time
from collections.abc import Callable


logger = logging.getLogger(__name__)


class VoiceInputError(Exception):
    """A safe, user-presentable microphone or speech-recognition error."""


class VoiceInputCancelled(VoiceInputError):
    """A user-cancelled microphone capture."""


class VoiceInputService:
    SAMPLE_RATE = 16_000
    SAMPLE_WIDTH = 2
    CHUNK_FRAMES = 4_000
    START_TIMEOUT_SECONDS = 8.0
    PHRASE_TIMEOUT_SECONDS = 15.0
    END_SILENCE_SECONDS = 1.0
    ENERGY_THRESHOLD = 500

    @staticmethod
    def dependencies_available() -> bool:
        return (
            VoiceInputService.transcription_available()
            and importlib.util.find_spec("sounddevice") is not None
        )

    @staticmethod
    def transcription_available() -> bool:
        return importlib.util.find_spec("speech_recognition") is not None

    def __init__(self):
        self._active_stream = None
        self._lock = threading.Lock()

    def listen_once(
        self,
        cancel_event: threading.Event,
        status_callback: Callable[[str], None] | None = None,
    ) -> str:
        logger.info("[ARIA VOICE] Speech recognition started.")
        try:
            import sounddevice as sd
            import speech_recognition as sr
        except ImportError as error:
            raise VoiceInputError(
                "Voice input is unavailable. Install the optional voice dependencies; text input remains available."
            ) from error

        if status_callback is not None:
            status_callback("Listening once. Audio is sent to Google's online speech-recognition service.")

        audio = bytearray()
        speech_started_at = None
        silence_seconds = 0.0
        start_deadline = time.monotonic() + self.START_TIMEOUT_SECONDS
        stream = None
        try:
            stream = sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.CHUNK_FRAMES,
                channels=1,
                dtype="int16",
            )
            with self._lock:
                self._active_stream = stream
            with stream:
                while True:
                    if cancel_event.is_set():
                        raise VoiceInputCancelled("Listening was cancelled.")
                    if speech_started_at is not None and (
                        time.monotonic() - speech_started_at >= self.PHRASE_TIMEOUT_SECONDS
                        or silence_seconds >= self.END_SILENCE_SECONDS
                    ):
                        break
                    if speech_started_at is None and time.monotonic() >= start_deadline:
                        raise VoiceInputError("No speech was detected before the listening timeout.")

                    chunk, _overflowed = stream.read(self.CHUNK_FRAMES)
                    if cancel_event.is_set():
                        raise VoiceInputCancelled("Listening was cancelled.")
                    level = _rms_level(chunk)
                    if speech_started_at is None:
                        if level < self.ENERGY_THRESHOLD:
                            continue
                        speech_started_at = time.monotonic()
                        if status_callback is not None:
                            status_callback("Speech detected. Transcribing with Google's online service.")
                    audio.extend(chunk)
                    if speech_started_at is not None:
                        silence_seconds = (
                            silence_seconds + self.CHUNK_FRAMES / self.SAMPLE_RATE
                            if level < self.ENERGY_THRESHOLD
                            else 0.0
                        )
        except (VoiceInputCancelled, VoiceInputError):
            raise
        except Exception as error:
            raise VoiceInputError(
                "The microphone is unavailable. Check Windows microphone permissions and the selected input device."
            ) from error
        finally:
            with self._lock:
                self._active_stream = None

        if cancel_event.is_set():
            raise VoiceInputCancelled("Listening was cancelled.")
        if not audio:
            return ""

        recognizer = sr.Recognizer()
        recognizer.operation_timeout = 10
        audio_data = sr.AudioData(bytes(audio), self.SAMPLE_RATE, self.SAMPLE_WIDTH)
        try:
            text = recognizer.recognize_google(audio_data, language="en-US").strip()
            if cancel_event.is_set():
                raise VoiceInputCancelled("Listening was cancelled.")
            return text
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as error:
            raise VoiceInputError(
                "Online speech recognition is unavailable. Check the network connection or use text input."
            ) from error

    def transcribe_audio(
        self,
        raw_audio: bytes,
        *,
        sample_rate: int = SAMPLE_RATE,
        sample_width: int = SAMPLE_WIDTH,
    ) -> str:
        if (
            not isinstance(raw_audio, bytes)
            or not raw_audio
            or len(raw_audio) > 2_000_000
            or sample_rate != self.SAMPLE_RATE
            or sample_width != self.SAMPLE_WIDTH
            or len(raw_audio) % sample_width
        ):
            raise VoiceInputError("The submitted microphone audio is invalid or exceeds the size limit.")
        try:
            import speech_recognition as sr
        except ImportError as error:
            raise VoiceInputError(
                "Voice input is unavailable. Install the optional voice dependencies; text input remains available."
            ) from error

        recognizer = sr.Recognizer()
        recognizer.operation_timeout = 10
        audio_data = sr.AudioData(raw_audio, sample_rate, sample_width)
        try:
            return recognizer.recognize_google(audio_data, language="en-US").strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as error:
            raise VoiceInputError(
                "Online speech recognition is unavailable. Check the network connection or use text input."
            ) from error
        except (TimeoutError, OSError) as error:
            raise VoiceInputError(
                "Online speech recognition timed out. Check the network connection or use text input."
            ) from error

    def cancel(self) -> None:
        with self._lock:
            stream = self._active_stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                # The capture thread also checks its cancellation event between short reads.
                pass

    def close(self) -> None:
        self.cancel()


def _rms_level(raw_audio: bytes) -> float:
    samples = array.array("h")
    samples.frombytes(raw_audio)
    if not samples:
        return 0.0
    return (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
