from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class AmbientDecision:
    action: str
    message: str | None = None
    reason: str = ""


class AmbientMode:
    """Permission-gated, rate-limited decisions from minimal approved signals."""

    COOLDOWN_SECONDS = 20 * 60
    MAX_INTERVENTIONS_PER_HOUR = 3
    BREAK_REMINDER_MINUTES = 90

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._lock = Lock()
        self._enabled = False
        self._permissions: frozenset[str] = frozenset()
        self._last_intervention = None
        self._interventions: list[float] = []
        self._last_signal = None

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @property
    def permissions(self) -> frozenset[str]:
        with self._lock:
            return self._permissions

    def enable(self, *, permissions) -> None:
        granted = frozenset(str(item).strip() for item in permissions if str(item).strip())
        if not granted:
            raise ValueError("Ambient mode requires at least one explicitly approved signal.")
        if not granted <= {"focused_work_timer"}:
            raise ValueError("Ambient mode received an unsupported or unapproved signal.")
        with self._lock:
            self._enabled = True
            self._permissions = granted

    def disable(self) -> None:
        with self._lock:
            self._enabled = False
            self._permissions = frozenset()
            self._last_signal = None

    def evaluate(self, context: dict[str, Any]) -> AmbientDecision:
        with self._lock:
            if not self._enabled or "focused_work_timer" not in self._permissions:
                return AmbientDecision("no_action", reason="ambient_mode_disabled")
            if context.get("interrupting") or context.get("user_is_speaking"):
                return AmbientDecision("no_action", reason="interruption_or_speech")

            try:
                active_minutes = max(0, min(int(context.get("focused_minutes", 0)), 24 * 60))
            except (TypeError, ValueError):
                return AmbientDecision("no_action", reason="invalid_context")

            if active_minutes < self.BREAK_REMINDER_MINUTES:
                self._last_signal = None
                return AmbientDecision("no_action", reason="not_relevant")

            now = self._clock()
            self._interventions = [
                timestamp for timestamp in self._interventions if now - timestamp < 3600
            ]
            signal = "focused_work_break"
            if self._last_signal == signal:
                return AmbientDecision("no_action", reason="signal_already_handled")
            if (
                self._last_intervention is not None
                and now - self._last_intervention < self.COOLDOWN_SECONDS
            ):
                return AmbientDecision("no_action", reason="cooldown")
            if len(self._interventions) >= self.MAX_INTERVENTIONS_PER_HOUR:
                return AmbientDecision("no_action", reason="hourly_limit")

            self._last_signal = signal
            self._last_intervention = now
            self._interventions.append(now)
            return AmbientDecision(
                "proactive_response",
                "You've been working for a while. Would a short break be helpful?",
                reason="focused_work_break_reminder",
            )
