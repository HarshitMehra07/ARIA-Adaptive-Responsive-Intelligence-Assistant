from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class AutomationAuditEvent:
    task_id: str
    operation: str
    category: str
    timestamp: str
    confirmation_required: bool
    confirmation_obtained: bool
    attempted: bool
    verified: bool
    error_category: str | None = None


class AutomationAuditLog:
    """Bounded in-memory metadata-only audit log; no user text or screenshots."""

    def __init__(self, maximum_events: int = 200):
        self._events: deque[AutomationAuditEvent] = deque(maxlen=maximum_events)

    def record(
        self,
        *,
        task_id: str,
        operation: str,
        category: str,
        confirmation_required: bool = False,
        confirmation_obtained: bool = False,
        attempted: bool = False,
        verified: bool = False,
        error_category: str | None = None,
    ) -> AutomationAuditEvent:
        event = AutomationAuditEvent(
            task_id=task_id,
            operation=operation,
            category=category,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confirmation_required=confirmation_required,
            confirmation_obtained=confirmation_obtained,
            attempted=attempted,
            verified=verified,
            error_category=error_category,
        )
        self._events.append(event)
        return event

    def recent(self) -> tuple[AutomationAuditEvent, ...]:
        return tuple(self._events)


def new_task_id() -> str:
    return uuid4().hex[:12]
