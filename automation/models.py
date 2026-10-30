from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from automation.policy import classify_action, is_sensitive_field


class ActionRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class AutomationAction:
    kind: str
    target: str | None = None
    value: str | None = field(default=None, repr=False)
    risk: ActionRisk = ActionRisk.LOW


@dataclass(frozen=True)
class AutomationPlan:
    task_id: str
    actions: tuple[AutomationAction, ...]
    description: str

    def validate(self) -> None:
        if (
            not isinstance(self.task_id, str)
            or not self.task_id
            or len(self.task_id) > 64
            or not isinstance(self.description, str)
            or not self.description.strip()
            or len(self.description) > 200
        ):
            raise ValueError("An automation task must have a valid ID and a short description.")
        if not self.actions or len(self.actions) > 8:
            raise ValueError("An automation task must contain between 1 and 8 actions.")
        if any(not isinstance(action, AutomationAction) for action in self.actions):
            raise ValueError("An automation task contains a malformed action.")
        allowed = {
            "open_application",
            "switch_application",
            "open_output_folder",
            "open_url",
            "search_web",
            "summarize_page",
            "find_page_text",
            "capture_screen",
            "fill_browser_field",
            "click_browser_button",
            "click_desktop_element",
            "fill_desktop_field",
            "click_coordinate",
            "delete_file",
            "send_message",
            "purchase_item",
        }
        for action in self.actions:
            if not isinstance(action.kind, str) or action.kind not in allowed:
                raise ValueError("The automation task contains an unsupported action.")
            if (
                action.target is not None
                and (
                    not isinstance(action.target, str)
                    or len(action.target) > 2_000
                    or any(ord(char) < 32 for char in action.target)
                )
            ):
                raise ValueError("An automation action has an invalid target.")
            if (
                action.value is not None
                and (
                    not isinstance(action.value, str)
                    or len(action.value) > 2_000
                    or any(ord(char) < 32 and char not in "\r\n\t" for char in action.value)
                )
            ):
                raise ValueError("An automation action has invalid input text.")
            if not isinstance(action.risk, ActionRisk):
                raise ValueError("An automation action has an invalid risk classification.")
            if action.risk is not ActionRisk(classify_action(action.kind, action.target)):
                raise ValueError("An automation action has an invalid risk classification.")
            if action.kind in {"fill_browser_field", "fill_desktop_field"} and is_sensitive_field(
                action.target or ""
            ):
                raise ValueError("Sensitive fields are not supported.")
            if action.kind in {
                "open_application",
                "switch_application",
                "open_url",
                "search_web",
                "find_page_text",
                "fill_browser_field",
                "fill_desktop_field",
                "click_browser_button",
                "click_desktop_element",
                "click_coordinate",
                "delete_file",
                "send_message",
                "purchase_item",
            } and not action.target:
                raise ValueError(f"The {action.kind} action requires an explicit target.")
            if action.kind in {"fill_browser_field", "fill_desktop_field"} and not action.value:
                raise ValueError(f"The {action.kind} action requires explicit input text.")
            if action.kind in {"send_message", "purchase_item"} and not action.value:
                raise ValueError(f"The {action.kind} action requires explicit details.")
            if action.kind == "click_coordinate" and not re.fullmatch(
                r"\d{1,5},\d{1,5}",
                action.target or "",
            ):
                raise ValueError("A coordinate click requires two valid integer coordinates.")
        if len({(action.kind, action.target) for action in self.actions}) != len(self.actions):
            raise ValueError("An automation task cannot repeat the same action and target.")


@dataclass(frozen=True)
class ActionResult:
    operation: str
    attempted: bool
    verified: bool
    details: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_code: str | None = None
