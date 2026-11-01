import array
import logging
import sys
import threading
import time
import types
from concurrent.futures import Future

import pytest

from automation.computer_use import ComputerUseService
from voice.speech_output_service import SpeechOutputService, _voice_gender
from voice.voice_demo_controller import VoiceDemoController, VoiceDemoState
from voice.voice_input_service import VoiceInputCancelled, VoiceInputService
from voice.voice_service import VoiceService


class ImmediateExecutor:
    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as error:
            future.set_exception(error)
        return future

    def shutdown(self, **_kwargs):
        return None


class PendingExecutor:
    def __init__(self):
        self.future = None

    def submit(self, function, *args):
        self.function = function
        self.args = args
        self.future = Future()
        return self.future

    def shutdown(self, **_kwargs):
        return None


class FakeInput:
    def __init__(self, result="recognized request"):
        self.result = result
        self.cancelled = False
        self.closed = False
        self.listen_calls = 0

    def listen_once(self, _cancel_event, _status_callback):
        self.listen_calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def cancel(self):
        self.cancelled = True

    def close(self):
        self.closed = True


class FakeSpeechOutput:
    def __init__(self):
        self.text = None
        self.callbacks = {}
        self.stopped = False
        self.closed = False

    def speak(self, text, **callbacks):
        self.text = text
        self.callbacks = callbacks
        return True

    def stop(self):
        self.stopped = True
        self.callbacks["on_finished"](True)
        return True

    def close(self):
        self.closed = True


class FakeAria:
    def __init__(self, response="ARIA's actual response"):
        self.response = response
        self.requests = []

    def process_input(self, text):
        self.requests.append(text)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def build_controller(*, input_result="recognized request", response="ARIA's actual response"):
    states = []
    transcripts = []
    responses = []
    errors = []
    activity = []
    voice_input = FakeInput(input_result)
    speech_output = FakeSpeechOutput()
    aria = FakeAria(response)
    controller = VoiceDemoController(
        aria,
        voice_input,
        speech_output,
        dispatch=lambda callback: callback(),
        on_state=states.append,
        on_transcript=transcripts.append,
        on_response=responses.append,
        on_error=errors.append,
        on_speech_activity=lambda: activity.append(True),
        executor=ImmediateExecutor(),
    )
    return controller, aria, voice_input, speech_output, states, transcripts, responses, errors, activity


def test_voice_request_has_idle_listening_thinking_speaking_idle_transitions():
    controller, aria, _, speech, states, transcripts, responses, _, activity = build_controller()

    assert controller.start_listening()
    assert aria.requests == ["recognized request"]
    assert transcripts == ["recognized request"]
    assert responses == ["ARIA's actual response"]
    assert speech.text == "ARIA's actual response"
    assert states == [
        VoiceDemoState.LISTENING,
        VoiceDemoState.THINKING,
    ]

    speech.callbacks["on_started"]()
    speech.callbacks["on_word"]()
    assert states[-1] is VoiceDemoState.SPEAKING
    assert activity == [True]
    speech.callbacks["on_finished"](False)
    assert states[-1] is VoiceDemoState.IDLE
    controller.close()


def test_text_request_runs_without_accessing_the_microphone():
    controller, aria, voice_input, speech, *_ = build_controller()

    assert controller.submit_text("typed request")
    assert aria.requests == ["typed request"]
    assert voice_input.listen_calls == 0
    assert speech.text == "ARIA's actual response"
    controller.close()


@pytest.mark.parametrize(
    ("input_result", "expected_error"),
    [
        (TimeoutError("secret=recognizer-token"), "Speech recognition failed."),
        ("", "No clear speech was recognized."),
    ],
)
def test_timeout_or_empty_speech_returns_idle_without_request(input_result, expected_error):
    controller, aria, _, _, states, _, _, errors, _ = build_controller(
        input_result=input_result
    )

    assert controller.start_listening()
    assert controller.state is VoiceDemoState.IDLE
    assert aria.requests == []
    assert states[-1] is VoiceDemoState.IDLE
    assert expected_error in errors[-1]
    assert "recognizer-token" not in errors[-1]
    controller.close()


def test_repeated_activation_and_overlapping_text_request_are_rejected():
    executor = PendingExecutor()
    voice_input = FakeInput()
    aria = FakeAria()
    speech = FakeSpeechOutput()
    controller = VoiceDemoController(
        aria,
        voice_input,
        speech,
        executor=executor,
        dispatch=lambda callback: callback(),
    )

    assert controller.start_listening()
    assert not controller.start_listening()
    assert not controller.submit_text("second request")
    assert voice_input.cancelled is False
    controller.cancel_listening()
    executor.future.set_result("late transcript after cancellation")
    assert aria.requests == []
    assert controller.state is VoiceDemoState.IDLE
    controller.close()


def test_failed_aria_action_never_produces_a_response_or_speech_success():
    failure = RuntimeError("sensitive provider diagnostic secret=abc123")
    controller, aria, _, speech, _, _, responses, errors, _ = build_controller(
        response=failure
    )

    assert controller.submit_text("do a safe test")
    assert aria.requests == ["do a safe test"]
    assert responses == []
    assert speech.text is None
    assert controller.state is VoiceDemoState.IDLE
    assert errors == ["ARIA could not complete the request. Please try again."]
    assert "abc123" not in str(errors)
    controller.close()


def test_voice_request_uses_existing_aria_pipeline_for_confirmation():
    request = "delete file C:\\Users\\Demo\\notes.txt"
    confirmation_required = "This exact action requires your confirmation."
    controller, aria, _, speech, _, _, responses, _, _ = build_controller(
        input_result=request,
        response=confirmation_required,
    )

    assert controller.start_listening()
    assert aria.requests == [request]
    assert responses == [confirmation_required]
    assert speech.text == confirmation_required
    controller.close()


@pytest.mark.parametrize(
    "spoken_text",
    [
        'Delete file "C:\\ARIA\\output\\draft.txt"',
        'Send a message to Alice saying "The meeting is at 3 PM."',
        'Purchase "Desk lamp" for $49.99',
    ],
)
def test_voice_originated_sensitive_actions_retain_real_confirmation_gate(spoken_text):
    class MockDesktop:
        def __init__(self):
            self.deleted = []

        def emergency_stop_pressed(self):
            return False

        def delete_file(self, path):
            self.deleted.append(path)

    class MockBrowser:
        def __init__(self):
            self.current_host = None
            self.current_url = None
            self.sent = []
            self.purchased = []

        def close(self):
            return None

    class MockAudit:
        def record(self, **_kwargs):
            return {"operation": "confirmation_required"}

    desktop, browser = MockDesktop(), MockBrowser()
    computer_use = ComputerUseService(
        desktop=desktop,
        browser=browser,
        screen=object(),
        audit_log=MockAudit(),
    )

    class RoutedAria:
        result = None

        def process_input(self, recognized_text):
            self.result = computer_use.handle(recognized_text)
            return self.result.details["message"]

    aria = RoutedAria()
    controller = VoiceDemoController(
        aria,
        FakeInput(spoken_text),
        FakeSpeechOutput(),
        dispatch=lambda callback: callback(),
        executor=ImmediateExecutor(),
    )

    assert controller.start_listening()
    assert aria.result is not None
    assert aria.result.requires_confirmation
    assert not aria.result.attempted
    assert desktop.deleted == []
    assert browser.sent == []
    assert browser.purchased == []
    controller.close()


def test_stop_speaking_interrupts_playback_and_returns_to_idle():
    controller, _, _, speech, states, _, _, _, _ = build_controller()
    assert controller.submit_text("say something")
    speech.callbacks["on_started"]()

    assert controller.stop_speaking()
    assert speech.stopped
    assert states[-1] is VoiceDemoState.IDLE
    controller.close()


def test_continuous_voice_mode_rearms_after_each_completed_response():
    controller, _, voice_input, speech, *_ = build_controller()

    assert controller.set_continuous(True)
    assert voice_input.listen_calls == 1
    speech.callbacks["on_started"]()
    assert controller.state is VoiceDemoState.SPEAKING
    speech.callbacks["on_finished"](False)
    assert voice_input.listen_calls == 2
    speech.callbacks["on_started"]()
    assert controller.state is VoiceDemoState.SPEAKING
    assert controller.set_continuous(False)
    speech.callbacks["on_finished"](False)
    assert controller.state is VoiceDemoState.IDLE
    controller.close()


def test_user_can_interrupt_speech_and_explicitly_start_listening():
    controller, _, voice_input, speech, *_ = build_controller()
    assert controller.submit_text("say something")
    speech.callbacks["on_started"]()

    assert controller.start_listening()
    assert speech.stopped
    assert voice_input.listen_calls == 1
    speech.callbacks["on_started"]()
    assert controller.state is VoiceDemoState.SPEAKING
    controller.close()


def test_voice_service_construction_is_hardware_free_and_input_is_one_shot():
    class Input:
        calls = 0

        def listen_once(self, cancel_event):
            self.calls += 1
            assert not cancel_event.is_set()
            return "recognized once"

    class Output:
        def __init__(self):
            self.is_ready = False
            self.start_calls = 0
            self.spoken = []
            self.closed = False

        def start(self, *, on_ready, on_error):
            self.start_calls += 1
            self.is_ready = True
            on_ready(())

        def speak(self, text):
            self.spoken.append(text)
            return True

        def close(self):
            self.closed = True

    voice_input, speech_output = Input(), Output()
    service = VoiceService(input_service=voice_input, output_service=speech_output)
    assert voice_input.calls == speech_output.start_calls == 0
    assert service.listen() == "recognized once"
    service.speak("A local response.")
    service.close()

    assert voice_input.calls == 1
    assert speech_output.start_calls == 1
    assert speech_output.spoken == ["A local response."]
    assert speech_output.closed


def test_controller_close_releases_microphone_playback_and_executor():
    controller, _, voice_input, speech, *_ = build_controller()

    controller.close()

    assert voice_input.closed
    assert speech.closed
    assert controller.submit_text("request after close") is False


def test_speech_output_uses_actual_response_and_supports_interrupt():
    ready = threading.Event()
    started = threading.Event()
    word = threading.Event()
    finished = threading.Event()
    output = SpeechOutputService(engine_factory=FakeSpeechEngine, frame_interval=0.005)
    spoken = []
    cancellations = []
    try:
        output.start(on_ready=lambda _voices: ready.set())
        assert ready.wait(1)
        response = "This is the actual response."
        assert output.speak(
            response,
            on_started=started.set,
            on_word=word.set,
            on_finished=lambda cancelled: (
                cancellations.append(cancelled),
                finished.set(),
            ),
        )
        assert started.wait(1)
        assert word.wait(1)
        assert output.stop()
        assert finished.wait(1)
        spoken.extend(FakeSpeechEngine.last_instance.spoken)
        assert spoken == [response]
        assert cancellations == [True]
    finally:
        output.close()


def test_sensitive_response_is_not_spoken_or_logged(caplog):
    with caplog.at_level(logging.DEBUG):
        assert not SpeechOutputService(engine_factory=FakeSpeechEngine).speak(
            "The password is: test-password-123"
        )
    assert "test-password-123" not in caplog.text


@pytest.mark.parametrize("response", [None, "", "   ", 42, object()])
def test_empty_or_invalid_responses_are_not_sent_to_speech(response):
    output = SpeechOutputService(engine_factory=FakeSpeechEngine)

    assert not output.speak(response)


def test_microphone_audio_is_transcribed_in_memory_and_cancelled_transcription_is_discarded(
    monkeypatch,
):
    cancel_event = threading.Event()
    audio_chunks = [
        array.array("h", [2000] * VoiceInputService.CHUNK_FRAMES).tobytes(),
        *[
            bytes(VoiceInputService.CHUNK_FRAMES * VoiceInputService.SAMPLE_WIDTH)
            for _ in range(4)
        ],
    ]

    class FakeStream:
        def __init__(self, **_kwargs):
            self.chunks = iter(audio_chunks)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _frames):
            return next(self.chunks), False

        def abort(self):
            return None

    class FakeAudioData:
        def __init__(self, data, sample_rate, sample_width):
            self.data = data
            self.sample_rate = sample_rate
            self.sample_width = sample_width

    class FakeRecognizer:
        operation_timeout = None

        def recognize_google(self, audio_data, language):
            assert audio_data.data
            assert language == "en-US"
            cancel_event.set()
            return "must not be submitted"

    fake_sd = types.SimpleNamespace(RawInputStream=FakeStream)
    fake_sr = types.SimpleNamespace(
        Recognizer=FakeRecognizer,
        AudioData=FakeAudioData,
        UnknownValueError=type("UnknownValueError", (Exception,), {}),
        RequestError=type("RequestError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "speech_recognition", fake_sr)

    with pytest.raises(VoiceInputCancelled):
        VoiceInputService().listen_once(cancel_event)


class FakeSpeechEngine:
    last_instance = None

    def __init__(self):
        self.callbacks = {}
        self.spoken = []
        self._active = False
        self._started = False
        self.stopped = False
        self.properties = {}
        FakeSpeechEngine.last_instance = self

    def getProperty(self, _name):
        return [types.SimpleNamespace(id="fake-voice", name="Fake Voice")]

    def connect(self, event, callback):
        self.callbacks[event] = callback

    def startLoop(self, _use_driver_loop):
        return None

    def say(self, text):
        self.spoken.append(text)
        self._active = True
        self._started = False

    def iterate(self):
        if self._active and not self._started:
            self._started = True
            self.callbacks["started-utterance"](name="aria")
            self.callbacks["started-word"](
                name="response",
                location=0,
                length=8,
            )
            time.sleep(0.03)

    def stop(self):
        self.stopped = True
        self._active = False

    def endLoop(self):
        return None

    def setProperty(self, _name, _value):
        self.properties[_name] = _value


def test_speech_output_processes_five_utterances_on_one_engine():
    class CompletingSpeechEngine(FakeSpeechEngine):
        def iterate(self):
            if not self._active:
                return
            if self._started:
                self._active = False
                self.callbacks["finished-utterance"](
                    name="aria",
                    completed=True,
                )
            else:
                self._started = True
                self.callbacks["started-utterance"](name="aria")

    engines = []

    def create_engine():
        engine = CompletingSpeechEngine()
        engines.append(engine)
        return engine

    ready = threading.Event()
    responses = [f"Response {index}." for index in range(1, 6)]
    finished = [threading.Event() for _response in responses]
    completed = []
    output = SpeechOutputService(engine_factory=create_engine, frame_interval=0.005)
    try:
        output.start(on_ready=lambda _voices: ready.set())
        assert ready.wait(1)

        for index, response in enumerate(responses):
            assert output.speak(
                response,
                on_finished=lambda cancelled, index=index: (
                    completed.append((index, cancelled)),
                    finished[index].set(),
                ),
            )
            assert finished[index].wait(1)

        assert output.is_ready
        assert len(engines) == 1
        assert engines[0].spoken == responses
        assert completed == [(index, False) for index in range(len(responses))]
    finally:
        output.close()


def test_speech_output_recovers_after_a_playback_error():
    class RecoveringSpeechEngine(FakeSpeechEngine):
        def __init__(self):
            super().__init__()
            self.fail_next = True
            self.pending_error = None

        def say(self, text):
            if self.fail_next:
                self.fail_next = False
                self.pending_error = RuntimeError("simulated playback failure")
                return
            super().say(text)

        def iterate(self):
            if self.pending_error:
                error = self.pending_error
                self.pending_error = None
                self.callbacks["error"](name="aria", exception=error)
                return
            if not self._active:
                return
            if self._started:
                self._active = False
                self.callbacks["finished-utterance"](
                    name="aria",
                    completed=True,
                )
            else:
                self._started = True
                self.callbacks["started-utterance"](name="aria")

    failed = threading.Event()
    finished = threading.Event()
    output = SpeechOutputService(
        engine_factory=RecoveringSpeechEngine,
        frame_interval=0.005,
    )
    try:
        output.start(on_ready=lambda _voices: None)
        for _ in range(100):
            if output.is_ready:
                break
            time.sleep(0.005)
        assert output.is_ready

        assert output.speak(
            "This attempt fails.",
            on_error=lambda _message: failed.set(),
        )
        assert failed.wait(1)
        assert output.is_ready
        assert output.speak(
            "This retry succeeds.",
            on_finished=lambda _cancelled: finished.set(),
        )
        assert finished.wait(1)
        assert RecoveringSpeechEngine.last_instance.spoken == ["This retry succeeds."]
    finally:
        output.close()


@pytest.mark.parametrize(
    ("voice", "expected"),
    [
        (types.SimpleNamespace(name="Microsoft Zira Desktop", id="zira"), "female"),
        (types.SimpleNamespace(name="Microsoft David Desktop", id="david"), "male"),
        (types.SimpleNamespace(name="Local voice", id="custom", gender="Female"), "female"),
        (types.SimpleNamespace(name="Local voice", id="custom", gender="Male"), "male"),
        (types.SimpleNamespace(name="Local voice", id="custom"), "unknown"),
    ],
)
def test_local_voice_gender_discovery_uses_metadata_or_voice_names(voice, expected):
    assert _voice_gender(voice) == expected


def test_voice_persona_selects_an_installed_local_voice_and_presentation():
    class PersonaSpeechEngine(FakeSpeechEngine):
        def getProperty(self, name):
            if name == "voices":
                return [
                    types.SimpleNamespace(id="zira", name="Microsoft Zira Desktop"),
                    types.SimpleNamespace(id="david", name="Microsoft David Desktop"),
                ]
            return None

    ready = threading.Event()
    output = SpeechOutputService(engine_factory=PersonaSpeechEngine, frame_interval=0.005)
    try:
        output.start(on_ready=lambda _voices: ready.set())
        assert ready.wait(1)
        assert output.select_persona("jarvis")
        assert output.selected_voice_id == "david"
        assert not output.select_persona("unrecognized")
        assert output.speak("Ready.")
        for _ in range(100):
            if (
                PersonaSpeechEngine.last_instance.properties.get("rate") == 145
                and PersonaSpeechEngine.last_instance.properties.get("voice") == "david"
            ):
                break
            time.sleep(0.005)
        assert PersonaSpeechEngine.last_instance.properties["rate"] == 145
        assert PersonaSpeechEngine.last_instance.properties["voice"] == "david"
    finally:
        output.close()


def test_explicit_voice_gender_metadata_takes_precedence_over_name():
    voice = types.SimpleNamespace(name="Microsoft David", id="david", gender="Female")

    assert _voice_gender(voice) == "female"
