from __future__ import annotations

import io
import ipaddress
import logging
import threading
import time
import wave
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from automation.models import ActionResult
from assistant.ambient_mode import AmbientMode
from core.aria_core import AriaCore
from core.cloud_model_client import CloudModelError
from document_generation.document_service import DocumentGenerationError
from document_generation.document_spec import DocumentFormat
from document_generation.file_manager import FileManagementError
from research.research_manager import ResearchError
from voice.speech_output_service import SpeechOutputService, is_speakable_response
from voice.voice_state import VoiceInteractionState, VoiceInteractionStateMachine
from voice.voice_input_service import VoiceInputCancelled, VoiceInputError, VoiceInputService
from vision.vision_service import VisionService, VisionServiceError


LOGGER = logging.getLogger(__name__)
MAX_CHAT_LENGTH = 4_000
MAX_AUDIO_BYTES = 2_000_044
MAX_AUDIO_SECONDS = 60
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHAT_LENGTH)
    source: Literal["text", "voice"] = "text"
    interaction_id: UUID | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a message before sending.")
        if any(ord(char) < 32 and char not in "\r\n\t" for char in value):
            raise ValueError("The message contains unsupported control characters.")
        return value


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("Enter a valid research query.")
        return value


class DocumentRequest(BaseModel):
    request: str = Field(min_length=1, max_length=4_000)
    format: DocumentFormat

    @field_validator("request")
    @classmethod
    def validate_request(cls, value: str) -> str:
        if not value.strip() or any(
            ord(char) < 32 and char not in "\r\n\t" for char in value
        ):
            raise ValueError("Enter a valid document request.")
        return value


class DocumentSummaryRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4_000)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("Enter a valid document path.")
        return value


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)
    voice_id: str | None = Field(default=None, max_length=500)
    interaction_id: UUID | None = None

    @field_validator("text")
    @classmethod
    def validate_speakable_text(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 and char not in "\r\n\t" for char in value):
            raise ValueError("Enter valid text to speak.")
        return value


class VoiceSelectionRequest(BaseModel):
    voice_id: str | None = Field(default=None, max_length=500)
    gender: Literal["female", "male"] | None = None


class VoicePersonaRequest(BaseModel):
    persona: Literal["aria", "jarvis"]


class VisionConsentRequest(BaseModel):
    consent: bool


class AmbientModeRequest(BaseModel):
    enabled: bool


class VoiceInteractionRequest(BaseModel):
    interaction_id: UUID
    state: Literal["listening", "thinking", "idle", "error"]
    error: str | None = Field(default=None, max_length=500)


def _is_loopback_request(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    try:
        if not ipaddress.ip_address(client.host).is_loopback:
            return False
    except ValueError:
        return False

    host_header = request.headers.get("host", "")
    try:
        host = urlsplit(f"//{host_header}").hostname
    except ValueError:
        return False
    if host not in LOCAL_HOSTS:
        return False

    origin = request.headers.get("origin")
    if origin:
        try:
            origin_parts = urlsplit(origin)
        except ValueError:
            return False
        if (
            origin_parts.scheme != "http"
            or origin_parts.hostname not in LOCAL_HOSTS
            or origin_parts.netloc.casefold() != host_header.casefold()
        ):
            return False
    return request.headers.get("sec-fetch-site", "").casefold() != "cross-site"


def _read_wave_audio(payload: bytes) -> tuple[bytes, int]:
    try:
        with wave.open(io.BytesIO(payload), "rb") as audio_file:
            sample_rate = audio_file.getframerate()
            frame_count = audio_file.getnframes()
            if (
                audio_file.getcomptype() != "NONE"
                or audio_file.getnchannels() != 1
                or audio_file.getsampwidth() != 2
                or sample_rate != VoiceInputService.SAMPLE_RATE
                or frame_count <= 0
                or frame_count > VoiceInputService.SAMPLE_RATE * MAX_AUDIO_SECONDS
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Audio must be mono 16 kHz PCM and no longer than 60 seconds.",
                )
            raw_audio = audio_file.readframes(frame_count)
            if len(raw_audio) != frame_count * 2:
                raise HTTPException(status_code=422, detail="The submitted WAV audio is incomplete.")
            return raw_audio, sample_rate
    except (wave.Error, EOFError) as error:
        raise HTTPException(status_code=422, detail="The submitted WAV audio is invalid.") from error


def create_app(
    *,
    aria_core: AriaCore | None = None,
    voice_input: VoiceInputService | None = None,
    speech_output: SpeechOutputService | None = None,
    vision_service: VisionService | None = None,
    ambient_mode: AmbientMode | None = None,
) -> FastAPI:
    aria = aria_core or AriaCore()
    microphone = voice_input or VoiceInputService()
    speaker = speech_output or SpeechOutputService()
    vision = vision_service or VisionService()
    ambient = ambient_mode or AmbientMode()
    ambient_state = {"started_at": None}
    ambient_state_lock = threading.Lock()
    request_lock = threading.RLock()
    state_lock = threading.Lock()
    voice_state = {
        "speech": "idle",
        "speech_error": None,
        "speech_event_id": 0,
        "start_attempted": False,
    }
    interaction = VoiceInteractionStateMachine()

    app = FastAPI(
        title="ARIA Local Interface",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.aria_core = aria
    app.state.voice_input = microphone
    app.state.speech_output = speaker
    app.state.vision_service = vision
    app.state.ambient_mode = ambient

    def cleanup_sensors() -> None:
        vision.stop()
        ambient.disable()

    app.router.add_event_handler("shutdown", cleanup_sensors)

    @app.middleware("http")
    async def restrict_to_local_browser(request: Request, call_next):
        if not _is_loopback_request(request):
            return JSONResponse(
                status_code=403,
                content={"detail": "ARIA is available only from its local browser interface."},
            )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'"
        )
        return response

    def set_speech_state(
        state: str,
        *,
        event: bool = False,
        error: str | None = None,
    ) -> None:
        with state_lock:
            voice_state["speech"] = state
            if event:
                voice_state["speech_event_id"] += 1
            voice_state["speech_error"] = error

    def ensure_interaction_thinking(interaction_id: str) -> bool:
        snapshot = interaction.snapshot()
        if snapshot["session_id"] == interaction_id:
            if snapshot["state"] == "thinking":
                return True
            if snapshot["state"] == "listening":
                return interaction.transition(
                    interaction_id,
                    VoiceInteractionState.THINKING,
                )
            return False

        if snapshot["state"] not in {"idle", "error"}:
            return False
        if interaction.start(interaction_id, VoiceInteractionState.THINKING):
            LOGGER.info(
                "[ARIA VOICE] Resumed interaction %s after its state expired.",
                interaction_id,
            )
            return True

        current = interaction.snapshot()
        return (
            current["session_id"] == interaction_id
            and current["state"] == "thinking"
        )

    def start_speech_service() -> None:
        with state_lock:
            if voice_state["start_attempted"]:
                return
            voice_state["start_attempted"] = True

        def speech_error(message: str) -> None:
            set_speech_state("idle", event=True, error=message)

        speaker.start(
            on_ready=lambda _voices: None,
            on_error=speech_error,
        )

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "service": "ARIA",
            "voice_state_api": 1,
        }

    @app.get("/api/history")
    async def history():
        from core.conversation_manager import ConversationManager

        return {"messages": ConversationManager.get_history()}

    @app.post("/api/chat")
    async def chat(body: ChatRequest):
        interaction_id = str(body.interaction_id) if body.interaction_id else None
        if interaction_id:
            if not ensure_interaction_thinking(interaction_id):
                raise HTTPException(status_code=409, detail="This ARIA interaction is no longer active.")
        try:
            LOGGER.info(
                "[ARIA INPUT] User message received (source=%s, characters=%d).",
                body.source,
                len(body.text.strip()),
            )
            with request_lock:
                LOGGER.info("[ARIA BRAIN] Processing request.")
                response = await run_in_threadpool(aria.process_input, body.text)
            if not isinstance(response, str) or not response.strip():
                raise TypeError("The ARIA request pipeline returned an empty or non-text response.")
            LOGGER.info("[ARIA RESPONSE] Response generated (characters=%d).", len(response.strip()))
            from core.conversation_manager import ConversationManager

            return {
                "response": response,
                "messages": ConversationManager.get_history(),
            }
        except Exception as error:
            LOGGER.exception("The web chat request failed.")
            if interaction_id:
                interaction.fail(interaction_id, "ARIA couldn't process this request.")
            raise HTTPException(
                status_code=500,
                detail="ARIA couldn't process this request. Check the local server output.",
            ) from error

    @app.post("/api/voice/interaction")
    async def update_interaction(body: VoiceInteractionRequest):
        interaction_id = str(body.interaction_id)
        snapshot = interaction.snapshot()
        if snapshot["session_id"] == interaction_id:
            changed = interaction.transition(
                interaction_id,
                body.state,
                error=body.error,
            )
        elif body.state in {"listening", "thinking"}:
            changed = interaction.start(interaction_id, body.state)
        elif body.state == "error":
            changed = interaction.fail(
                interaction_id,
                body.error or "The voice interaction needs attention.",
            )
        else:
            changed = interaction.transition(interaction_id, body.state)
        if not changed:
            raise HTTPException(
                status_code=409,
                detail="The ARIA interaction state changed or is no longer active. Start a new interaction.",
            )
        return interaction.snapshot()

    @app.post("/api/research")
    async def research(body: ResearchRequest):
        try:
            results = await run_in_threadpool(aria.research_manager.search_web, body.query)
            return {"results": results}
        except ResearchError as error:
            status = 503 if error.error_type == "not_configured" else 502
            raise HTTPException(status_code=status, detail=str(error)) from error
        except Exception as error:
            LOGGER.exception("The web research request failed.")
            raise HTTPException(
                status_code=500,
                detail="ARIA couldn't complete this research request.",
            ) from error

    @app.get("/api/documents")
    async def documents():
        try:
            files = await run_in_threadpool(aria.document_service.list_generated_files)
            return {
                "documents": [
                    {"name": file["name"], "size_bytes": file["size_bytes"]}
                    for file in files
                ]
            }
        except FileManagementError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post("/api/documents")
    async def create_document(body: DocumentRequest):
        try:
            result = await run_in_threadpool(
                aria.document_service.create_from_request,
                body.request,
                body.format,
            )
            return {
                "name": result.path.name,
                "format": result.document_format.value,
                "size_bytes": result.size_bytes,
            }
        except (DocumentGenerationError, FileManagementError, ResearchError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except CloudModelError as error:
            raise HTTPException(
                status_code=503,
                detail="The configured cloud model couldn't create this document.",
            ) from error
        except Exception as error:
            LOGGER.exception("Document generation through the web interface failed.")
            raise HTTPException(
                status_code=500,
                detail="ARIA couldn't create this document.",
            ) from error

    @app.post("/api/documents/summarize")
    async def summarize_document(body: DocumentSummaryRequest):
        try:
            summary, partial = await run_in_threadpool(
                aria.document_service.summarize_document,
                body.path,
            )
            return {"summary": summary, "partial": partial}
        except FileManagementError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/documents/{filename}")
    async def download_document(filename: str):
        if (
            not filename
            or Path(filename).name != filename
            or any(separator in filename for separator in ("/", "\\", "\0"))
        ):
            raise HTTPException(status_code=404, detail="Generated document not found.")
        try:
            files = await run_in_threadpool(aria.document_service.list_generated_files)
        except FileManagementError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        file = next((item for item in files if item["name"] == filename), None)
        if file is None:
            raise HTTPException(status_code=404, detail="Generated document not found.")
        return FileResponse(Path(str(file["path"])), filename=filename)

    @app.get("/api/voice/status")
    async def voice_status():
        start_speech_service()
        with state_lock:
            state = voice_state.copy()
        interaction_status = interaction.snapshot()
        return {
            "microphone_capture": "browser",
            "transcription_available": VoiceInputService.transcription_available(),
            "transcription_disclosure": (
                "When you finish recording, the clip is sent to Google's online speech-recognition service."
            ),
            "speech_output_ready": speaker.is_ready,
            "speech_state": state["speech"],
            "speech_error": state["speech_error"],
            "speech_event_id": state["speech_event_id"],
            "speech_sync": "local speech engine start, word-boundary, finish, and stop events",
            "interaction_state": interaction_status["state"],
            "interaction_session_id": interaction_status["session_id"],
            "interaction_event_id": interaction_status["event_id"],
            "interaction_error": interaction_status["error"],
            "voices": [
                {"id": voice.voice_id, "name": voice.name, "gender": voice.gender}
                for voice in speaker.voices
            ],
            "selected_voice_id": speaker.selected_voice_id,
            "voice_persona": getattr(speaker, "voice_persona", "aria"),
        }

    @app.get("/api/vision/status")
    async def vision_status():
        return {
            "active": vision.is_active,
            "available": vision.dependencies_available(),
            "last_error": vision.last_error,
            "analysis": (
                "Local face count only; identity and emotion are not recognized."
            ),
        }

    @app.post("/api/vision/start")
    async def start_vision(body: VisionConsentRequest):
        if not body.consent:
            raise HTTPException(status_code=403, detail="Camera access requires your consent.")
        try:
            active = await run_in_threadpool(vision.start, consent=True)
        except VisionServiceError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if not active:
            raise HTTPException(
                status_code=503,
                detail=vision.last_error or "The camera could not be started.",
            )
        return {"active": True}

    @app.get("/api/vision/analyze")
    async def analyze_vision():
        if not vision.is_active:
            raise HTTPException(status_code=409, detail="Camera analysis is not enabled.")
        try:
            return await run_in_threadpool(vision.analyze_scene)
        except VisionServiceError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post("/api/vision/stop")
    async def stop_vision():
        await run_in_threadpool(vision.stop)
        return {"active": False}

    @app.get("/api/ambient/status")
    async def ambient_status():
        return {
            "enabled": ambient.enabled,
            "permissions": sorted(ambient.permissions),
        }

    @app.put("/api/ambient")
    async def set_ambient_mode(body: AmbientModeRequest):
        if body.enabled:
            ambient.enable(permissions={"focused_work_timer"})
            with ambient_state_lock:
                ambient_state["started_at"] = time.monotonic()
        else:
            ambient.disable()
            with ambient_state_lock:
                ambient_state["started_at"] = None
        return {
            "enabled": ambient.enabled,
            "permissions": sorted(ambient.permissions),
        }

    @app.post("/api/ambient/evaluate")
    async def evaluate_ambient():
        with ambient_state_lock:
            started_at = ambient_state["started_at"]
        if started_at is None:
            decision = ambient.evaluate({})
        else:
            interaction_status = interaction.snapshot()
            focused_minutes = int((time.monotonic() - started_at) / 60)
            decision = ambient.evaluate(
                {
                    "focused_minutes": focused_minutes,
                    "interrupting": interaction_status["state"] != "idle",
                }
            )
        return {
            "action": decision.action,
            "message": decision.message,
            "reason": decision.reason,
        }

    @app.post("/api/voice/transcribe")
    async def transcribe(request: Request):
        interaction_header = request.headers.get("x-aria-interaction-id")
        interaction_id = None
        if interaction_header:
            try:
                interaction_id = str(UUID(interaction_header))
            except ValueError as error:
                raise HTTPException(status_code=422, detail="The ARIA interaction ID is invalid.") from error
            if not ensure_interaction_thinking(interaction_id):
                raise HTTPException(status_code=409, detail="This ARIA interaction is no longer active.")
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "audio/wav":
            raise HTTPException(status_code=415, detail="Send microphone audio as a WAV file.")
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_AUDIO_BYTES:
                    raise HTTPException(status_code=413, detail="The audio clip exceeds the 60-second limit.")
            except ValueError as error:
                raise HTTPException(status_code=400, detail="The audio size is invalid.") from error
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > MAX_AUDIO_BYTES:
                raise HTTPException(status_code=413, detail="The audio clip exceeds the 60-second limit.")
        raw_audio, sample_rate = _read_wave_audio(bytes(chunks))
        try:
            transcript = await run_in_threadpool(
                microphone.transcribe_audio,
                raw_audio,
                sample_rate=sample_rate,
                sample_width=2,
            )
            return {"text": transcript}
        except VoiceInputCancelled as error:
            if interaction_id:
                interaction.transition(interaction_id, VoiceInteractionState.IDLE)
            raise HTTPException(status_code=409, detail="Transcription was cancelled.") from error
        except VoiceInputError as error:
            if interaction_id:
                interaction.fail(interaction_id, str(error))
            raise HTTPException(status_code=503, detail=str(error)) from error
        except Exception as error:
            LOGGER.exception("Browser audio transcription failed.")
            if interaction_id:
                interaction.fail(interaction_id, "Speech transcription failed. Text input remains available.")
            raise HTTPException(
                status_code=503,
                detail="Speech transcription failed. Text input remains available.",
            ) from error

    @app.post("/api/voice/speak")
    async def speak(body: SpeakRequest):
        start_speech_service()
        if not is_speakable_response(body.text):
            raise HTTPException(
                status_code=422,
                detail="This response cannot be spoken because it may contain a secret or internal error.",
            )
        if not speaker.is_ready:
            raise HTTPException(
                status_code=503,
                detail="Local speech output is not ready. Check the voice status and try again.",
            )
        interaction_id = str(body.interaction_id) if body.interaction_id else str(uuid4())
        if body.interaction_id:
            if not ensure_interaction_thinking(interaction_id):
                raise HTTPException(status_code=409, detail="This ARIA interaction is no longer active.")
        elif not interaction.start(interaction_id, VoiceInteractionState.THINKING):
            raise HTTPException(status_code=409, detail="Another ARIA interaction is already active.")
        if body.voice_id and not speaker.select_voice(body.voice_id):
            interaction.fail(interaction_id, "That speech voice is not available.")
            raise HTTPException(status_code=422, detail="That speech voice is not available.")
        set_speech_state("starting", event=True)
        started = speaker.speak(
            body.text,
            voice_id=body.voice_id,
            on_started=lambda: (
                set_speech_state("speaking", event=True),
                interaction.transition(interaction_id, VoiceInteractionState.SPEAKING),
            ),
            on_word=lambda: (
                set_speech_state("speaking", event=True),
                interaction.transition(interaction_id, VoiceInteractionState.SPEAKING),
            ),
            on_finished=lambda _cancelled: (
                set_speech_state("idle", event=True),
                interaction.transition(interaction_id, VoiceInteractionState.IDLE),
            ),
            on_error=lambda message: (
                set_speech_state("idle", event=True, error=message),
                interaction.fail(interaction_id, message),
            ),
        )
        if not started:
            set_speech_state(
                "idle",
                event=True,
                error="Local speech output is busy or unavailable.",
            )
            interaction.fail(interaction_id, "Local speech output is busy or unavailable.")
            raise HTTPException(status_code=409, detail="Speech is already active or unavailable.")
        return {"accepted": True, "interaction_id": interaction_id}

    @app.post("/api/voice/stop")
    async def stop_speaking():
        stopped = speaker.stop()
        if stopped:
            set_speech_state("idle", event=True, error=None)
            snapshot = interaction.snapshot()
            if snapshot["session_id"]:
                interaction.transition(snapshot["session_id"], VoiceInteractionState.IDLE)
        return {"stopped": stopped}

    @app.put("/api/voice/voice")
    async def select_voice(body: VoiceSelectionRequest):
        start_speech_service()
        if not speaker.is_ready:
            raise HTTPException(status_code=503, detail="Local speech output is not ready.")
        voice_id = body.voice_id
        if body.gender:
            candidates = [voice for voice in speaker.voices if voice.gender == body.gender]
            if not candidates:
                raise HTTPException(
                    status_code=422,
                    detail=f"No {body.gender} local speech voices are available on this device.",
                )
            voice_id = candidates[0].voice_id
        if not speaker.select_voice(voice_id):
            raise HTTPException(status_code=422, detail="That speech voice is not available.")
        return {"selected": voice_id}

    @app.put("/api/voice/persona")
    async def select_voice_persona(body: VoicePersonaRequest):
        start_speech_service()
        if not speaker.is_ready:
            raise HTTPException(status_code=503, detail="Local speech output is not ready.")
        selector = getattr(speaker, "select_persona", None)
        if selector is None or not selector(body.persona):
            raise HTTPException(
                status_code=503,
                detail="Voice identity selection is unavailable on this device.",
            )
        return {"selected": body.persona}

    return app


app = create_app()
