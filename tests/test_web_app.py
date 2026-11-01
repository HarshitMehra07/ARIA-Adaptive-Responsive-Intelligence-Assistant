from __future__ import annotations

import io
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from automation.models import ActionResult
from core.aria_core import AriaCore
from core.cloud_model_client import CloudModelResponse
from document_generation.document_spec import DocumentFormat
from voice.speech_output_service import SpeechVoice
from web.app import create_app


class FakeCore:
    def __init__(self, *, failure=None):
        self.failure = failure
        self.requests = []
        self.research_manager = SimpleNamespace(search_web=lambda query: [{"query": query}])
        self.document_service = FakeDocuments()

    def process_input(self, text):
        self.requests.append(text)
        if self.failure:
            raise self.failure
        return f"ARIA received: {text}"


class FakeDocuments:
    def __init__(self):
        self.files = []
        self.created = None
        self.summary = ("A local document summary.", False)

    def list_generated_files(self):
        return self.files

    def create_from_request(self, request, document_format):
        self.created = (request, document_format)
        return SimpleNamespace(
            path=Path("example.txt"),
            document_format=document_format,
            size_bytes=42,
        )

    def summarize_document(self, path):
        self.summarized_path = path
        return self.summary


class FakeVoiceInput:
    def __init__(self, transcript="recognized words"):
        self.transcript = transcript
        self.received = None

    def transcribe_audio(self, raw_audio, *, sample_rate, sample_width):
        self.received = (raw_audio, sample_rate, sample_width)
        return self.transcript


class FakeSpeechOutput:
    def __init__(self):
        self.is_ready = True
        self.voices = (
            SpeechVoice("voice-female", "Test Female Voice", "female"),
            SpeechVoice("voice-male", "Test Male Voice", "male"),
        )
        self.started = False
        self.selected = None
        self.selected_voice_id = None
        self.text = None
        self.callbacks = {}
        self.stopped = False
        self.voice_persona = "aria"

    def start(self, *, on_ready=None, on_error=None):
        self.started = True
        if on_ready:
            on_ready(self.voices)

    def select_voice(self, voice_id):
        if voice_id not in (None, "voice-female", "voice-male"):
            return False
        self.selected = voice_id
        self.selected_voice_id = voice_id
        return True

    def select_persona(self, persona):
        if persona not in {"aria", "jarvis"}:
            return False
        self.voice_persona = persona
        return True

    def speak(self, text, **callbacks):
        self.text = text
        self.callbacks = callbacks
        return True

    def stop(self):
        self.stopped = True
        if self.callbacks.get("on_finished"):
            self.callbacks["on_finished"](True)
        return True


class FakeVision:
    def __init__(self):
        self.is_active = False
        self.last_error = None
        self.started_with_consent = False
        self.stopped = False

    @staticmethod
    def dependencies_available():
        return True

    def start(self, *, consent=False):
        self.started_with_consent = consent
        self.is_active = consent
        return self.is_active

    def analyze_scene(self):
        return {
            "status": "analyzed",
            "face_count": 1,
            "user_identity": "not_recognized",
            "emotion": "unknown",
            "emotion_confidence": 0.0,
        }

    def stop(self):
        self.stopped = True
        self.is_active = False


def _client(core=None, voice_input=None, speech_output=None, vision_service=None):
    return TestClient(
        create_app(
            aria_core=core or FakeCore(),
            voice_input=voice_input or FakeVoiceInput(),
            speech_output=speech_output or FakeSpeechOutput(),
            vision_service=vision_service,
        ),
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 50_000),
    )


def _wav_audio(frames=b"\x00\x00" * 160):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(16_000)
        audio_file.writeframes(frames)
    return output.getvalue()


def test_health_and_browser_interface_are_served_locally():
    with _client() as client:
        health = client.get("/api/health")
        page = client.get("/")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "service": "ARIA",
        "voice_state_api": 1,
    }
    assert health.headers["cache-control"] == "no-store"
    assert page.status_code == 200
    assert "ARIA · ELECTRONIC CORE" in page.text
    assert "Stop &amp; transcribe" in page.text
    assert page.text.count("<animateMotion") == 3


def test_browser_neuron_supports_reduced_motion_and_orbit_state_animation():
    with _client() as client:
        stylesheet = client.get("/static/styles.css")
        script = client.get("/static/app.js")

    assert stylesheet.status_code == script.status_code == 200
    assert 'api("/api/chat"' in script.text
    assert 'method: "POST"' in script.text
    assert "prefers-reduced-motion: reduce" in stylesheet.text
    assert "speech-word" in stylesheet.text
    assert 'pauseAnimations()' in script.text
    assert "dataset.state" in script.text
    assert "interaction_event_id" in script.text
    assert "processUserInput" in script.text
    assert "interaction_session_id" in script.text


def test_chat_uses_existing_aria_core_and_conversation_history():
    class FakeCloud:
        def __init__(self):
            self.messages = None

        def complete(self, messages):
            self.messages = messages
            return CloudModelResponse(text="A real core response.", model="test-model", raw={})

    cloud = FakeCloud()
    core = AriaCore(cloud_client=cloud)
    with _client(core=core) as client:
        response = client.post("/api/chat", json={"text": "What is 2 + 2?"})
        history = client.get("/api/history")

    assert response.status_code == 200
    assert response.json()["response"] == "A real core response."
    assert [item["role"] for item in response.json()["messages"]] == ["user", "assistant"]
    assert [item["role"] for item in history.json()["messages"]] == ["user", "assistant"]
    assert cloud.messages


def test_consecutive_text_and_voice_chat_requests_share_aria_history():
    from core.conversation_manager import ConversationManager

    class SequencedCloud:
        def __init__(self):
            self.calls = []

        def complete(self, messages):
            self.calls.append(messages)
            return CloudModelResponse(
                text=f"Response {len(self.calls)}.",
                model="test-model",
                raw={},
            )

    class SequencedVoiceInput:
        def __init__(self):
            self.transcripts = iter(("Message three.", "Message five."))

        def transcribe_audio(self, _raw_audio, *, sample_rate, sample_width):
            assert sample_rate == 16_000
            assert sample_width == 2
            return next(self.transcripts)

    ConversationManager.clear()
    cloud = SequencedCloud()
    core = AriaCore(cloud_client=cloud)
    voice_input = SequencedVoiceInput()
    requests = [
        ("text", "Message one."),
        ("text", "Message two."),
        ("voice", "Message three."),
        ("text", "Message four."),
        ("voice", "Message five."),
    ]
    try:
        with _client(core=core, voice_input=voice_input) as client:
            responses = []
            for source, text in requests:
                request_text = text
                if source == "voice":
                    transcript = client.post(
                        "/api/voice/transcribe",
                        content=_wav_audio(),
                        headers={"Content-Type": "audio/wav"},
                    )
                    assert transcript.status_code == 200
                    request_text = transcript.json()["text"]
                responses.append(
                    client.post(
                        "/api/chat",
                        json={"source": source, "text": request_text},
                    )
                )
            history = client.get("/api/history").json()["messages"]

        assert all(response.status_code == 200 for response in responses)
        assert [response.json()["response"] for response in responses] == [
            f"Response {index}." for index in range(1, 6)
        ]
        assert [turn["content"] for turn in history if turn["role"] == "user"] == [
            text for _source, text in requests
        ]
        assert [turn["content"] for turn in history if turn["role"] == "assistant"] == [
            f"Response {index}." for index in range(1, 6)
        ]
        assert len(cloud.calls) == 5
        assert len(cloud.calls[-1]) > len(cloud.calls[0])
    finally:
        ConversationManager.clear()


def test_voice_status_exposes_active_interaction_for_abandoned_session_recovery():
    from uuid import uuid4

    speech = FakeSpeechOutput()
    with _client(speech_output=speech) as client:
        interaction_id = str(uuid4())
        started = client.post(
            "/api/voice/interaction",
            json={"interaction_id": interaction_id, "state": "listening"},
        )
        status = client.get("/api/voice/status")
        recovered = client.post(
            "/api/voice/interaction",
            json={"interaction_id": status.json()["interaction_session_id"], "state": "idle"},
        )

    assert started.status_code == 200
    assert status.json()["interaction_session_id"] == interaction_id
    assert recovered.json()["state"] == "idle"


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "   "},
        {"text": "message\x00with control"},
        {"text": "x" * 4_001},
    ],
)
def test_chat_rejects_invalid_input(payload):
    with _client() as client:
        response = client.post("/api/chat", json=payload)

    assert response.status_code == 422


def test_unknown_chat_routes_and_methods_return_explicit_http_errors():
    with _client() as client:
        wrong_path = client.post("/api/chats", json={"text": "hello"})
        wrong_method = client.get("/api/chat")

    assert wrong_path.status_code == 404
    assert wrong_path.json() == {"detail": "Not Found"}
    assert wrong_method.status_code == 405
    assert wrong_method.json() == {"detail": "Method Not Allowed"}


def test_browser_requests_reject_cross_site_origins_and_nonlocal_hosts():
    with _client() as client:
        cross_site = client.post(
            "/api/chat",
            json={"text": "hello"},
            headers={"Origin": "https://example.com"},
        )
        foreign_host = client.get("/api/health", headers={"Host": "example.com"})

    assert cross_site.status_code == 403
    assert foreign_host.status_code == 403


def test_chat_errors_are_logged_and_return_a_safe_message(caplog):
    with _client(core=FakeCore(failure=RuntimeError("private diagnostic"))) as client:
        response = client.post("/api/chat", json={"text": "hello"})

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "ARIA couldn't process this request. Check the local server output."
    )
    assert "private diagnostic" not in response.text
    assert "web chat request failed" in caplog.text


def test_research_and_document_routes_reuse_existing_services(tmp_path):
    core = FakeCore()
    document = tmp_path / "report.txt"
    document.write_text("A generated report.", encoding="utf-8")
    core.document_service.files = [
        {"name": document.name, "path": str(document), "size_bytes": document.stat().st_size}
    ]

    with _client(core=core) as client:
        research = client.post("/api/research", json={"query": "local research"})
        listing = client.get("/api/documents")
        download = client.get("/api/documents/report.txt")
        created = client.post(
            "/api/documents",
            json={"request": "Create a report", "format": "txt"},
        )
        summary = client.post(
            "/api/documents/summarize",
            json={"path": str(document)},
        )

    assert research.json() == {"results": [{"query": "local research"}]}
    assert listing.json() == {
        "documents": [{"name": "report.txt", "size_bytes": document.stat().st_size}]
    }
    assert download.content == b"A generated report."
    assert created.json() == {"name": "example.txt", "format": "txt", "size_bytes": 42}
    assert core.document_service.created == ("Create a report", DocumentFormat.TEXT)
    assert summary.json() == {"summary": "A local document summary.", "partial": False}


def test_document_download_rejects_paths_outside_the_generated_file_list():
    with _client() as client:
        response = client.get("/api/documents/../../.env")

    assert response.status_code == 404


def test_voice_transcription_checks_wav_and_uses_existing_voice_service(monkeypatch):
    monkeypatch.setattr(
        "web.app.VoiceInputService.transcription_available",
        staticmethod(lambda: True),
    )
    voice = FakeVoiceInput()
    speech = FakeSpeechOutput()
    with _client(voice_input=voice, speech_output=speech) as client:
        status = client.get("/api/voice/status")
        transcript = client.post(
            "/api/voice/transcribe",
            content=_wav_audio(),
            headers={"Content-Type": "audio/wav"},
        )
        unsupported = client.post(
            "/api/voice/transcribe",
            content=b"audio",
            headers={"Content-Type": "audio/webm"},
        )
        invalid = client.post(
            "/api/voice/transcribe",
            content=b"not a wav",
            headers={"Content-Type": "audio/wav"},
        )

    assert status.json()["transcription_disclosure"].startswith("When you finish recording")
    assert status.json()["microphone_capture"] == "browser"
    assert transcript.json() == {"text": "recognized words"}
    assert voice.received == (b"\x00\x00" * 160, 16_000, 2)
    assert unsupported.status_code == 415
    assert invalid.status_code == 422


def test_voice_gender_selection_discovers_local_voices_and_persists_the_choice(monkeypatch):
    monkeypatch.setattr(
        "web.app.VoiceInputService.transcription_available",
        staticmethod(lambda: True),
    )
    speech = FakeSpeechOutput()
    with _client(speech_output=speech) as client:
        initial = client.get("/api/voice/status")
        female = client.put("/api/voice/voice", json={"gender": "female"})
        after_female = client.get("/api/voice/status")
        male = client.put("/api/voice/voice", json={"gender": "male"})
        after_male = client.get("/api/voice/status")
        explicit = client.put("/api/voice/voice", json={"voice_id": "voice-female"})
        invalid = client.put("/api/voice/voice", json={"voice_id": "not-installed"})
        unavailable_gender = client.put("/api/voice/voice", json={"gender": "unknown"})
        after_invalid = client.get("/api/voice/status")

    assert initial.json()["voices"] == [
        {"id": "voice-female", "name": "Test Female Voice", "gender": "female"},
        {"id": "voice-male", "name": "Test Male Voice", "gender": "male"},
    ]
    assert female.json() == {"selected": "voice-female"}
    assert after_female.json()["selected_voice_id"] == "voice-female"
    assert male.json() == {"selected": "voice-male"}
    assert after_male.json()["selected_voice_id"] == "voice-male"
    assert explicit.json() == {"selected": "voice-female"}
    assert invalid.status_code == unavailable_gender.status_code == 422
    assert after_invalid.json()["selected_voice_id"] == "voice-female"


def test_voice_persona_is_distinct_from_the_assistant_brain():
    speech = FakeSpeechOutput()
    with _client(speech_output=speech) as client:
        selected = client.put("/api/voice/persona", json={"persona": "jarvis"})
        status = client.get("/api/voice/status")
        invalid = client.put("/api/voice/persona", json={"persona": "other"})

    assert selected.json() == {"selected": "jarvis"}
    assert status.json()["voice_persona"] == "jarvis"
    assert invalid.status_code == 422


def test_camera_requires_explicit_consent_and_exposes_only_aggregate_local_analysis():
    vision = FakeVision()
    with _client(vision_service=vision) as client:
        initial = client.get("/api/vision/status")
        denied = client.post("/api/vision/start", json={"consent": False})
        started = client.post("/api/vision/start", json={"consent": True})
        scene = client.get("/api/vision/analyze")
        stopped = client.post("/api/vision/stop")

    assert initial.json()["active"] is False
    assert denied.status_code == 403
    assert started.json() == {"active": True}
    assert vision.started_with_consent is True
    assert scene.json()["face_count"] == 1
    assert scene.json()["user_identity"] == "not_recognized"
    assert scene.json()["emotion"] == "unknown"
    assert stopped.json() == {"active": False}
    assert vision.stopped


def test_ambient_mode_is_opt_in_and_only_uses_the_focused_work_timer():
    with _client() as client:
        initial = client.get("/api/ambient/status")
        disabled = client.post("/api/ambient/evaluate")
        enabled = client.put("/api/ambient", json={"enabled": True})
        active = client.get("/api/ambient/status")
        evaluation = client.post("/api/ambient/evaluate")
        turned_off = client.put("/api/ambient", json={"enabled": False})

    assert initial.json() == {"enabled": False, "permissions": []}
    assert disabled.json()["reason"] == "ambient_mode_disabled"
    assert enabled.json() == {
        "enabled": True,
        "permissions": ["focused_work_timer"],
    }
    assert active.json()["enabled"] is True
    assert evaluation.json() == {
        "action": "no_action",
        "message": None,
        "reason": "not_relevant",
    }
    assert turned_off.json()["enabled"] is False


def test_backend_voice_state_drives_transcription_chat_and_real_speech_callbacks(monkeypatch):
    from uuid import uuid4

    monkeypatch.setattr(
        "web.app.VoiceInputService.transcription_available",
        staticmethod(lambda: True),
    )
    speech = FakeSpeechOutput()
    with _client(speech_output=speech) as client:
        interaction_id = str(uuid4())
        listening = client.post(
            "/api/voice/interaction",
            json={"interaction_id": interaction_id, "state": "listening"},
        )
        overlapping = client.post(
            "/api/voice/interaction",
            json={"interaction_id": str(uuid4()), "state": "listening"},
        )
        thinking = client.post(
            "/api/voice/interaction",
            json={"interaction_id": interaction_id, "state": "thinking"},
        )
        transcript = client.post(
            "/api/voice/transcribe",
            content=_wav_audio(),
            headers={
                "Content-Type": "audio/wav",
                "X-ARIA-Interaction-ID": interaction_id,
            },
        )
        response = client.post(
            "/api/chat",
            json={"text": transcript.json()["text"], "interaction_id": interaction_id},
        )
        speaking = client.post(
            "/api/voice/speak",
            json={"text": response.json()["response"], "interaction_id": interaction_id},
        )
        speech.callbacks["on_started"]()
        speaking_status = client.get("/api/voice/status")
        speech.callbacks["on_word"]()
        word_status = client.get("/api/voice/status")
        speech.callbacks["on_finished"](False)
        idle = client.get("/api/voice/status")

    assert listening.json()["state"] == "listening"
    assert overlapping.status_code == 409
    assert thinking.json()["state"] == "thinking"
    assert transcript.json()["text"] == "recognized words"
    assert response.status_code == 200
    assert speaking.json()["accepted"] is True
    assert speaking_status.json()["interaction_state"] == "speaking"
    assert word_status.json()["interaction_event_id"] > speaking_status.json()["interaction_event_id"]
    assert idle.json()["interaction_state"] == "idle"


def test_voice_pipeline_resumes_its_session_if_it_expires_between_stages():
    from uuid import uuid4

    speech = FakeSpeechOutput()
    interaction_id = str(uuid4())
    with _client(speech_output=speech) as client:
        client.post(
            "/api/voice/interaction",
            json={"interaction_id": interaction_id, "state": "listening"},
        )
        expired = client.post(
            "/api/voice/interaction",
            json={"interaction_id": interaction_id, "state": "idle"},
        )
        transcript = client.post(
            "/api/voice/transcribe",
            content=_wav_audio(),
            headers={
                "Content-Type": "audio/wav",
                "X-ARIA-Interaction-ID": interaction_id,
            },
        )
        response = client.post(
            "/api/chat",
            json={
                "source": "voice",
                "text": transcript.json()["text"],
                "interaction_id": interaction_id,
            },
        )
        speech_request = client.post(
            "/api/voice/speak",
            json={
                "text": response.json()["response"],
                "interaction_id": interaction_id,
            },
        )

    assert expired.json()["state"] == "idle"
    assert transcript.status_code == 200
    assert transcript.json()["text"] == "recognized words"
    assert response.status_code == 200
    assert speech_request.status_code == 200
    assert speech_request.json()["accepted"] is True


def test_voice_interaction_errors_recover_and_cancel_returns_to_idle():
    from uuid import uuid4

    with _client() as client:
        failed_id = str(uuid4())
        started = client.post(
            "/api/voice/interaction",
            json={"interaction_id": failed_id, "state": "listening"},
        )
        failed = client.post(
            "/api/voice/interaction",
            json={
                "interaction_id": failed_id,
                "state": "error",
                "error": "Microphone permission was denied.",
            },
        )
        recovered_id = str(uuid4())
        recovered = client.post(
            "/api/voice/interaction",
            json={"interaction_id": recovered_id, "state": "thinking"},
        )
        cancelled = client.post(
            "/api/voice/interaction",
            json={"interaction_id": recovered_id, "state": "idle"},
        )
        final = client.get("/api/voice/status")

    assert started.json()["state"] == "listening"
    assert failed.json()["state"] == "error"
    assert failed.json()["error"] == "Microphone permission was denied."
    assert recovered.json()["state"] == "thinking"
    assert cancelled.json()["state"] == "idle"
    assert final.json()["interaction_state"] == "idle"


def test_transcribed_audio_can_continue_through_the_existing_aria_core(monkeypatch):
    class FakeCloud:
        def __init__(self):
            self.messages = None

        def complete(self, messages):
            self.messages = messages
            return CloudModelResponse(text="A real core response.", model="test-model", raw={})

    monkeypatch.setattr(
        "web.app.VoiceInputService.transcription_available",
        staticmethod(lambda: True),
    )
    cloud = FakeCloud()
    voice = FakeVoiceInput("What is 2 + 2?")
    core = AriaCore(cloud_client=cloud)
    with _client(core=core, voice_input=voice) as client:
        transcript = client.post(
            "/api/voice/transcribe",
            content=_wav_audio(),
            headers={"Content-Type": "audio/wav"},
        )
        response = client.post("/api/chat", json={"text": transcript.json()["text"]})

    assert response.status_code == 200
    assert response.json()["response"] == "A real core response."
    assert cloud.messages


def test_voice_speech_uses_local_speech_service_and_can_be_stopped():
    speech = FakeSpeechOutput()
    with _client(speech_output=speech) as client:
        selected = client.put("/api/voice/voice", json={"voice_id": "voice-female"})
        spoken = client.post(
            "/api/voice/speak",
            json={"text": "ARIA response", "voice_id": "voice-female"},
        )
        speech.callbacks["on_started"]()
        speaking = client.get("/api/voice/status")
        stopped = client.post("/api/voice/stop")
        after_stop = client.get("/api/voice/status")

    assert selected.status_code == 200
    assert spoken.json()["accepted"] is True
    assert spoken.json()["interaction_id"]
    assert speech.text == "ARIA response"
    assert speaking.json()["speech_state"] == "speaking"
    assert stopped.json() == {"stopped": True}
    assert speech.stopped
    assert after_stop.json()["speech_error"] is None


def test_voice_speech_state_tracks_actual_start_word_finish_and_error_events():
    speech = FakeSpeechOutput()
    with _client(speech_output=speech) as client:
        started = client.post("/api/voice/speak", json={"text": "ARIA response"})
        preparing = client.get("/api/voice/status")
        speech.callbacks["on_started"]()
        speaking = client.get("/api/voice/status")
        speech.callbacks["on_word"]()
        word_event = client.get("/api/voice/status")
        speech.callbacks["on_finished"](False)
        finished = client.get("/api/voice/status")

        failed = client.post("/api/voice/speak", json={"text": "Try local speech"})
        speech.callbacks["on_error"]("Local speech device is unavailable.")
        error = client.get("/api/voice/status")

    assert started.status_code == failed.status_code == 200
    assert preparing.json()["speech_state"] == "starting"
    assert speaking.json()["speech_state"] == "speaking"
    assert word_event.json()["speech_event_id"] > speaking.json()["speech_event_id"]
    assert finished.json()["speech_state"] == "idle"
    assert finished.json()["speech_error"] is None
    assert error.json()["speech_state"] == "idle"
    assert error.json()["speech_error"] == "Local speech device is unavailable."


def test_sensitive_speech_is_rejected_and_automation_has_no_direct_http_route():
    with _client() as client:
        speech = client.post(
            "/api/voice/speak",
            json={"text": "My api_key is abc123"},
        )
        automation = client.post(
            "/api/automation/execute",
            json={"command": "run arbitrary shell"},
        )

    assert speech.status_code == 422
    assert automation.status_code == 404


def test_aria_confirmation_stays_in_the_existing_chat_pipeline():
    class ConfirmationService:
        pending = False
        executed = False

        @property
        def has_pending_confirmation(self):
            return self.pending

        def handle_command(self, command):
            if command.action == "execute":
                self.pending = True
                return ActionResult(
                    operation="click_browser_button",
                    attempted=False,
                    verified=False,
                    details={"message": "This exact action requires your confirmation."},
                    requires_confirmation=True,
                    confirmation_code="abcdef12",
                )
            if command.action == "confirm" and command.confirmation_code == "abcdef12":
                self.pending = False
                self.executed = True
                return ActionResult(
                    operation="click_browser_button",
                    attempted=True,
                    verified=True,
                    details={"message": "The approved action completed."},
                )
            raise AssertionError("Unexpected automation command.")

    computer = ConfirmationService()
    core = AriaCore(computer_use_service=computer)
    with _client(core=core) as client:
        approval = client.post("/api/chat", json={"text": "Click button 'Submit'"})
        assert approval.status_code == 200
        assert "requires your confirmation" in approval.json()["response"]
        assert not computer.executed
        completed = client.post("/api/chat", json={"text": "CONFIRM abcdef12"})

    assert completed.status_code == 200
    assert computer.executed


def test_browser_chat_blocks_shell_requests_through_existing_automation_policy():
    from automation.computer_use import ComputerUseService

    class NoCloudCalls:
        def complete(self, _messages):
            raise AssertionError("A blocked shell request must not be sent to a cloud model.")

    core = AriaCore(
        cloud_client=NoCloudCalls(),
        computer_use_service=ComputerUseService(),
    )
    with _client(core=core) as client:
        response = client.post(
            "/api/chat",
            json={"text": "Run a PowerShell command to delete a file"},
        )

    assert response.status_code == 200
    assert response.json()["response"] == (
        "ARIA does not run shell or terminal commands from browser chat."
    )
    assert core.state.metadata["computer_command"].action == "unsupported"
