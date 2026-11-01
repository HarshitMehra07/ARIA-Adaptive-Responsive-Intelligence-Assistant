import pytest

from voice.voice_state import VoiceInteractionState, VoiceInteractionStateMachine


def test_voice_state_machine_tracks_the_full_voice_request_lifecycle():
    state = VoiceInteractionStateMachine()

    assert state.snapshot()["state"] == "idle"
    assert state.start("voice-1", VoiceInteractionState.LISTENING)
    assert state.snapshot()["state"] == "listening"
    assert state.transition("voice-1", VoiceInteractionState.THINKING)
    assert state.snapshot()["state"] == "thinking"
    assert state.transition("voice-1", VoiceInteractionState.SPEAKING)
    assert state.snapshot()["state"] == "speaking"
    assert state.transition("voice-1", VoiceInteractionState.SPEAKING)
    assert state.snapshot()["event_id"] == 4
    assert state.transition("voice-1", VoiceInteractionState.IDLE)
    assert state.snapshot() == {
        "state": "idle",
        "session_id": None,
        "event_id": 5,
        "error": None,
    }


def test_voice_state_machine_rejects_overlapping_or_out_of_order_sessions():
    state = VoiceInteractionStateMachine()

    assert state.start("voice-1", "listening")
    assert not state.start("voice-2", "listening")
    assert not state.transition("voice-2", "thinking")
    assert not state.transition("voice-1", "speaking")
    assert state.snapshot()["state"] == "listening"


def test_voice_state_machine_recovers_after_errors_and_cancellation_returns_idle():
    state = VoiceInteractionStateMachine()

    assert state.fail("failed-session", "Microphone unavailable.")
    assert state.snapshot()["state"] == "error"
    assert state.snapshot()["error"] == "Microphone unavailable."
    assert state.start("retry-session", "listening")
    assert state.snapshot()["error"] is None
    assert state.transition("retry-session", "idle")
    assert state.snapshot()["state"] == "idle"


@pytest.mark.parametrize("invalid", ["permission", "starting", "finished"])
def test_voice_state_machine_rejects_noncanonical_states(invalid):
    state = VoiceInteractionStateMachine()

    assert not state.start("voice-1", invalid)
    assert not state.transition("voice-1", invalid)
