from __future__ import annotations

import threading
from enum import StrEnum


class VoiceInteractionState(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


class VoiceInteractionStateMachine:
    _TRANSITIONS = {
        VoiceInteractionState.IDLE: {VoiceInteractionState.IDLE},
        VoiceInteractionState.LISTENING: {
            VoiceInteractionState.THINKING,
            VoiceInteractionState.IDLE,
            VoiceInteractionState.ERROR,
        },
        VoiceInteractionState.THINKING: {
            VoiceInteractionState.SPEAKING,
            VoiceInteractionState.IDLE,
            VoiceInteractionState.ERROR,
        },
        VoiceInteractionState.SPEAKING: {
            VoiceInteractionState.SPEAKING,
            VoiceInteractionState.IDLE,
            VoiceInteractionState.ERROR,
        },
        VoiceInteractionState.ERROR: {VoiceInteractionState.IDLE},
    }

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = VoiceInteractionState.IDLE
        self._session_id: str | None = None
        self._event_id = 0
        self._error: str | None = None

    @staticmethod
    def _as_state(state: VoiceInteractionState | str) -> VoiceInteractionState:
        if isinstance(state, VoiceInteractionState):
            return state
        return VoiceInteractionState[state.strip().upper()]

    def start(self, session_id: str, initial_state: VoiceInteractionState | str) -> bool:
        try:
            target = self._as_state(initial_state)
        except (KeyError, AttributeError):
            return False
        if target not in {VoiceInteractionState.LISTENING, VoiceInteractionState.THINKING}:
            return False
        with self._lock:
            if self._state not in {VoiceInteractionState.IDLE, VoiceInteractionState.ERROR} or not session_id:
                return False
            self._session_id = session_id
            self._state = target
            self._error = None
            self._event_id += 1
            return True

    def transition(
        self,
        session_id: str,
        state: VoiceInteractionState | str,
        *,
        error: str | None = None,
    ) -> bool:
        try:
            target = self._as_state(state)
        except (KeyError, AttributeError):
            return False
        with self._lock:
            if not session_id or session_id != self._session_id:
                return False
            if target not in self._TRANSITIONS[self._state]:
                return False
            self._state = target
            self._error = error if target is VoiceInteractionState.ERROR else None
            if target in {VoiceInteractionState.IDLE, VoiceInteractionState.ERROR}:
                self._session_id = None
            self._event_id += 1
            return True

    def fail(self, session_id: str, message: str) -> bool:
        with self._lock:
            if not session_id:
                return False
            if self._session_id is not None and session_id != self._session_id:
                return False
            self._state = VoiceInteractionState.ERROR
            self._session_id = None
            self._error = message
            self._event_id += 1
            return True

    def snapshot(self) -> dict[str, str | int | None]:
        with self._lock:
            return {
                "state": self._state.name.casefold(),
                "session_id": self._session_id,
                "event_id": self._event_id,
                "error": self._error,
            }
