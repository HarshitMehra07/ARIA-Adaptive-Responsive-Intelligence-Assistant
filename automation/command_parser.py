from __future__ import annotations

import re
from dataclasses import dataclass
from automation.models import ActionRisk, AutomationAction, AutomationPlan
from automation.policy import (
    APPLICATIONS,
    AutomationPolicyError,
    classify_action,
    is_sensitive_field,
    resolve_application_name,
    validate_public_url,
)
from automation.audit_log import new_task_id
from memory.memory_manager import contains_secret


@dataclass(frozen=True)
class ComputerCommand:
    action: str
    plan: AutomationPlan | None = None
    message: str | None = None
    confirmation_code: str | None = None


_URL = re.compile(r"https://[^\s<>\"']+", re.IGNORECASE)
_URL_TRAILING = ".,!?;:)"
_UNSUPPORTED_LEADS = re.compile(
    r"^(?:please\s+)?(?:open|launch|start|switch to|bring|take a screenshot|"
    r"capture|click|double.click|right.click|move the mouse|type|fill|send|submit|"
    r"purchase|buy|delete|install|change settings)\b",
    re.IGNORECASE,
)
_SHELL_EXECUTION_REQUEST = re.compile(
    r"^(?:please\s+)?(?:run|execute)\s+(?:(?:the|this|a)\s+)?"
    r"(?:shell(?:\s+command)?|powershell(?:\.exe)?|command prompt|terminal|"
    r"cmd(?:\.exe)?|command)\b",
    re.IGNORECASE,
)


def detect_computer_command(text: str) -> ComputerCommand | None:
    original = (text or "").strip()
    lowered = original.casefold()
    if not lowered:
        return None

    if _SHELL_EXECUTION_REQUEST.match(original):
        return ComputerCommand(
            "unsupported",
            message="ARIA does not run shell or terminal commands from browser chat.",
        )

    if lowered in {
        "stop automation",
        "emergency stop",
        "cancel automation",
        "cancel current automation",
        "stop computer control",
    }:
        return ComputerCommand("stop")
    if lowered in {"resume automation", "resume computer control"}:
        return ComputerCommand("resume")
    confirm_match = re.fullmatch(r"confirm\s+([0-9a-f]{8})", lowered)
    if confirm_match:
        return ComputerCommand("confirm", confirmation_code=confirm_match.group(1))
    if re.fullmatch(r"(?:cancel|no|decline)", lowered):
        return ComputerCommand("cancel")

    delete_match = re.fullmatch(
        r"(?:please\s+)?delete\s+(?:the\s+)?file\s+([\"'])(.{1,260}?)\1[.!]?",
        original,
        re.IGNORECASE | re.DOTALL,
    )
    if delete_match:
        return _plan(
            "delete_file",
            [_action("delete_file", target=delete_match.group(2))],
        )

    message_match = re.fullmatch(
        r"(?:please\s+)?send\s+(?:a\s+)?message\s+to\s+(.{1,120}?)"
        r"(?:\s+saying\s+|\s+with\s+(?:the\s+)?message\s+|:\s*)"
        r"([\"'])(.{1,1000}?)\2[.!]?",
        original,
        re.IGNORECASE | re.DOTALL,
    )
    if message_match:
        recipient = message_match.group(1).strip()
        message = message_match.group(3)
        if not recipient or contains_secret(message):
            return ComputerCommand(
                "unsupported",
                message="ARIA will not handle or disclose credentials in a message request.",
            )
        return _plan(
            "send_message",
            [_action("send_message", target=recipient, value=message)],
        )

    purchase_match = re.fullmatch(
        r"(?:please\s+)?(?:buy|purchase)\s+(?:the\s+)?([\"'])(.{1,160}?)\1"
        r"\s+for\s+\$(\d{1,7}(?:\.\d{2})?)[.!]?",
        original,
        re.IGNORECASE,
    )
    if purchase_match:
        return _plan(
            "purchase_item",
            [
                _action(
                    "purchase_item",
                    target=purchase_match.group(2),
                    value=f"${purchase_match.group(3)}",
                )
            ],
        )

    search_summary = re.search(
        r"^(?:please\s+)?(?:open\s+(?:my\s+)?browser[,]?\s*)?"
        r"(?:search|look\s+up)\s+for\s+(.+?)\s*(?:,?\s+(?:and\s+)?then?\s+|,\s*)"
        r"(?:summari[sz]e|read)\b.*$",
        original,
        re.IGNORECASE,
    )
    if search_summary:
        query = search_summary.group(1).strip(" .,!?:;\"'")
        if not query:
            return ComputerCommand("ambiguous", message="Tell me what topic to search for.")
        return _plan(
            "search_and_summarize",
            [
                _action("search_web", target=query),
                _action("summarize_page"),
            ],
        )

    open_docs_summary = re.search(
        r"^(?:please\s+)?open\b.*\b(?:official\s+)?python(?:\s+3\.13)?\s+documentation\b"
        r".*\b(?:and\s+)?summari[sz]e\b",
        original,
        re.IGNORECASE,
    )
    if open_docs_summary:
        return _plan(
            "open_and_summarize",
            [
                _action("open_url", target="https://docs.python.org/3/"),
                _action("summarize_page"),
            ],
        )

    if re.search(r"^(?:please\s+)?(?:take|capture)\s+(?:a\s+)?screenshot\b", lowered):
        return _plan("capture_screen", [_action("capture_screen")])

    if re.search(
        r"^(?:please\s+)?(?:read|summari[sz]e)\s+(?:the\s+)?(?:visible\s+)?page\b",
        lowered,
    ):
        return _plan("summarize_page", [_action("summarize_page")])

    find_match = re.search(
        r"^(?:please\s+)?search\s+(?:this|the\s+current)\s+page\s+for\s+(?:the\s+word\s+)?[\"']?(.+?)[\"']?[.!]?$",
        original,
        re.IGNORECASE,
    )
    if find_match:
        term = find_match.group(1).strip(" \t\r\n\"'.,!?")
        if not term or len(term) > 160:
            return ComputerCommand("ambiguous", message="Provide one search term of at most 160 characters.")
        return _plan("find_page_text", [_action("find_page_text", target=term)])

    fill_match = re.search(
        r"^(?:please\s+)?fill(?:\s+in)?\s+(?:the\s+)?(?:form\s+)?"
        r"(?:field\s+)?[\"']?(.+?)[\"']?\s+(?:field\s+)?with\s+[\"'](.+)[\"']"
        r"(?:\s*,?\s*but\s+do\s+not\s+submit(?:\s+it)?)?[.!]?$",
        original,
        re.IGNORECASE,
    )
    if fill_match:
        label, value = fill_match.group(1).strip(), fill_match.group(2)
        if label and is_sensitive_field(label):
            return ComputerCommand(
                "unsupported",
                message="ARIA will not enter passwords, tokens, or payment details.",
            )
        if label and value:
            return _plan(
                "fill_browser_field",
                [
                    _action(
                        "fill_browser_field",
                        target=label,
                        value=value,
                    )
                ],
            )
    if re.match(r"^(?:please\s+)?fill\b", lowered):
        return ComputerCommand(
            "ambiguous",
            message="Name the exact visible form-field label and put the value in quotes. ARIA will not submit it.",
        )

    button_match = re.search(
        r"^(?:please\s+)?click\s+(?:the\s+)?(?:button|link)\s+[\"'](.+?)[\"']\s*[.!]?$",
        original,
        re.IGNORECASE,
    )
    if button_match:
        label = button_match.group(1).strip()
        if label:
            return _plan(
                "click_browser_button",
                [_action("click_browser_button", target=label)],
            )

    coordinate_match = re.search(
        r"^(?:please\s+)?(move(?:\s+the)?\s+mouse|click)\s+"
        r"(?:at\s+)?(?:\(|x\s*=\s*)?(\d{1,5})\s*[, ]\s*(?:y\s*=\s*)?(\d{1,5})\)?[.!]?$",
        original,
        re.IGNORECASE,
    )
    if coordinate_match:
        kind = "move_pointer" if coordinate_match.group(1).casefold().startswith("move") else "click_coordinate"
        if kind == "move_pointer":
            return ComputerCommand(
                "ambiguous",
                message="Move the pointer only after taking a fresh screenshot; coordinate movement is not exposed without target verification.",
            )
        return _plan(
            "click_coordinate",
            [_action("click_coordinate", target=f"{coordinate_match.group(2)},{coordinate_match.group(3)}")],
        )

    url_match = _URL.search(original)
    if url_match and re.search(r"^(?:please\s+)?(?:open|navigate to|go to|visit)\b", lowered):
        url = url_match.group(0).rstrip(_URL_TRAILING)
        try:
            safe_url = validate_public_url(url)
        except AutomationPolicyError as error:
            return ComputerCommand("invalid", message=str(error))
        return _plan("open_url", [_action("open_url", target=safe_url)])

    if re.search(r"^(?:please\s+)?(?:open|launch|start)\b", lowered) and re.search(
        r"\b(?:aria\s+output\s+folder|output\s+folder)\b", lowered
    ):
        return _plan("open_output_folder", [_action("open_output_folder")])

    if re.search(r"^(?:please\s+)?(?:open|launch|start)\b", lowered) and re.search(
        r"\b(?:official\s+)?python(?:\s+3\.13)?\s+documentation\b", lowered
    ):
        return _plan(
            "open_url",
            [_action("open_url", target="https://docs.python.org/3/")],
        )

    if re.search(r"^(?:please\s+)?(?:open|launch|start)\b.*\b(?:browser|edge|chrome)\b", lowered):
        return _plan("open_application", [_action("open_application", target="browser")])

    for alias in sorted(APPLICATIONS, key=len, reverse=True):
        if alias == "browser":
            continue
        if re.search(
            rf"^(?:please\s+)?(?:open|launch|start)\s+(?:the\s+)?{re.escape(alias)}\b",
            lowered,
        ):
            return _plan(
                "open_application",
                [_action("open_application", target=resolve_application_name(alias))],
            )
        if re.search(
            rf"^(?:please\s+)?(?:switch to|bring up|focus)\s+(?:the\s+)?{re.escape(alias)}\b",
            lowered,
        ):
            return _plan(
                "switch_application",
                [_action("switch_application", target=resolve_application_name(alias))],
            )

    if re.search(
        r"^(?:please\s+)?(?:switch to|bring up|focus)\b.*\b(?:browser|edge|chrome)\b",
        lowered,
    ):
        return _plan("switch_application", [_action("switch_application", target="browser")])

    if re.search(
        r"^(?:please\s+)?(?:submit|send|publish|buy|purchase|pay|delete|install)\b",
        lowered,
    ):
        return ComputerCommand(
            "unsupported",
            message=(
                "That request is missing the exact details needed for a confirmation. "
                "ARIA will not submit forms, send messages, publish, purchase, delete, "
                "or install software without a specific confirmed target and action."
            ),
        )

    if _UNSUPPORTED_LEADS.search(original):
        return ComputerCommand(
            "unsupported",
            message=(
                "I could not identify a supported, unambiguous computer action. "
                "Supported applications are Notepad, VS Code, and the controlled Edge browser."
            ),
        )
    return None


def _action(kind: str, *, target: str | None = None, value: str | None = None) -> AutomationAction:
    risk_name = classify_action(kind, target)
    return AutomationAction(
        kind=kind,
        target=target,
        value=value,
        risk=ActionRisk(risk_name),
    )


def _plan(description: str, actions: list[AutomationAction]) -> ComputerCommand:
    plan = AutomationPlan(
        task_id=new_task_id(),
        actions=tuple(actions),
        description=description,
    )
    try:
        plan.validate()
    except ValueError as error:
        return ComputerCommand("unsupported", message=str(error))
    return ComputerCommand("execute", plan=plan)
