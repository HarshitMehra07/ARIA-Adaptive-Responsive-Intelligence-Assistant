from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from automation.audit_log import AutomationAuditLog
from automation.browser_service import BrowserAutomation, BrowserAutomationError
from automation.command_parser import ComputerCommand, detect_computer_command
from automation.models import ActionRisk, ActionResult, AutomationAction, AutomationPlan
from automation.policy import (
    AutomationPolicyError,
    is_sensitive_field,
    resolve_application_name,
    validate_output_folder,
    validate_public_url,
)
from automation.windows_backend import (
    AutomationBackendError,
    AutomationTargetError,
    WindowsDesktopBackend,
)
from memory.memory_manager import redact_secrets
from screen.screen_service import ScreenObservation, ScreenService


class AutomationStopped(Exception):
    """Raised when the user requests or triggers an emergency stop."""


@dataclass(frozen=True)
class PendingAutomation:
    plan: AutomationPlan
    action_index: int
    completed: tuple[ActionResult, ...]
    confirmation_code: str
    expires_at: float
    deadline_at: float
    target_context: str | None = None


class ComputerUseService:
    MAX_TASK_SECONDS = 30.0
    CONFIRMATION_SECONDS = 60.0
    MAX_ACTIONS = 8

    def __init__(
        self,
        *,
        desktop: WindowsDesktopBackend | None = None,
        browser: BrowserAutomation | None = None,
        screen: ScreenService | None = None,
        audit_log: AutomationAuditLog | None = None,
        stop_event: threading.Event | None = None,
    ):
        self.desktop = desktop if desktop is not None else WindowsDesktopBackend()
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.browser = (
            browser
            if browser is not None
            else BrowserAutomation(emergency_check=self._emergency_stop_requested)
        )
        self.screen = screen if screen is not None else ScreenService(self.desktop)
        self.audit_log = audit_log if audit_log is not None else AutomationAuditLog()
        self._pending: PendingAutomation | None = None
        self._last_screen: ScreenObservation | None = None

    @property
    def has_pending_confirmation(self) -> bool:
        return (
            self._pending is not None
            and time.monotonic() <= self._pending.expires_at
            and time.monotonic() <= self._pending.deadline_at
        )

    def handle(self, text: str) -> ActionResult | None:
        return self.handle_command(detect_computer_command(text))

    def handle_command(self, command: ComputerCommand | None) -> ActionResult | None:
        if command is None:
            return None
        if command.action == "stop":
            return self.emergency_stop()
        if command.action == "resume":
            self.stop_event.clear()
            self._pending = None
            return ActionResult(
                operation="resume_automation",
                attempted=False,
                verified=True,
                details={"message": "Automation is ready for a new user-requested task."},
            )
        if command.action == "cancel":
            self._pending = None
            return ActionResult(
                operation="cancel_automation",
                attempted=False,
                verified=True,
                details={"message": "The pending action was cancelled."},
            )
        if command.action == "confirm":
            return self._confirm(command.confirmation_code or "")
        self._pending = None
        if command.action in {"invalid", "unsupported", "ambiguous"}:
            return ActionResult(
                operation=command.action,
                attempted=False,
                verified=False,
                details={"message": command.message or "The computer action could not be completed."},
            )
        if command.plan is None:
            return ActionResult(
                operation="invalid_plan",
                attempted=False,
                verified=False,
                details={"message": "The automation request did not produce a valid plan."},
            )
        return self._run_plan(command.plan)

    def emergency_stop(self) -> ActionResult:
        self.stop_event.set()
        self._pending = None
        close_error = self._close_browser()
        event = self.audit_log.record(
            task_id="emergency-stop",
            operation="stop",
            category="emergency",
            attempted=True,
            verified=close_error is None,
            error_category="BrowserAutomationError" if close_error else None,
        )
        return ActionResult(
            operation="stop",
            attempted=True,
            verified=close_error is None,
            details={
                "message": (
                    "Automation stopped. Any queued actions were cancelled."
                    if close_error is None
                    else "Automation stopped and queued actions were cancelled, but the controlled browser may remain open."
                ),
                "audit_event": event,
            },
        )

    def close(self) -> None:
        self._pending = None
        self.browser.close()

    def _confirm(self, code: str) -> ActionResult:
        pending = self._pending
        if (
            pending is None
            or time.monotonic() > pending.expires_at
            or time.monotonic() > pending.deadline_at
        ):
            self._pending = None
            return ActionResult(
                operation="confirmation_expired",
                attempted=False,
                verified=False,
                details={"message": "There is no current action awaiting confirmation."},
            )
        if not code or code.casefold() != pending.confirmation_code.casefold():
            return ActionResult(
                operation="confirmation_mismatch",
                attempted=False,
                verified=False,
                details={
                    "message": "That confirmation code does not match the pending action. Nothing was executed."
                },
            )
        self._pending = None
        action = pending.plan.actions[pending.action_index]
        try:
            self._raise_if_stopped()
            if (
                action.kind == "click_browser_button"
                and pending.target_context is not None
                and self.browser.confirmation_context() != pending.target_context
            ):
                return ActionResult(
                    operation="confirmation_target_changed",
                    attempted=False,
                    verified=False,
                    details={
                        "message": "The browser page changed after approval was requested. Nothing was clicked; request the action again."
                    },
                )
            result = self._execute_action(action)
        except AutomationStopped:
            return self._stopped_result(pending.plan.task_id, len(pending.completed))
        except (
            AutomationPolicyError,
            AutomationBackendError,
            BrowserAutomationError,
            OSError,
            TimeoutError,
        ) as error:
            if self.stop_event.is_set():
                return self._stopped_result(pending.plan.task_id, len(pending.completed))
            self.audit_log.record(
                task_id=pending.plan.task_id,
                operation=action.kind,
                category=action.risk.value,
                confirmation_required=True,
                confirmation_obtained=True,
                attempted=True,
                verified=False,
                error_category=type(error).__name__,
            )
            return ActionResult(
                operation=action.kind,
                attempted=True,
                verified=False,
                details={"message": str(error)},
            )

        self.audit_log.record(
            task_id=pending.plan.task_id,
            operation=action.kind,
            category=action.risk.value,
            confirmation_required=True,
            confirmation_obtained=True,
            attempted=result.attempted,
            verified=result.verified,
        )
        if not result.attempted:
            return ActionResult(
                operation=action.kind,
                attempted=False,
                verified=False,
                details=result.details,
            )
        remaining_index = pending.action_index + 1
        completed = [*pending.completed, result]
        if remaining_index < len(pending.plan.actions):
            return self._continue_plan(
                pending.plan,
                remaining_index,
                completed,
                deadline=pending.deadline_at,
            )
        return ActionResult(
            operation=pending.plan.description,
            attempted=True,
            verified=all(item.verified for item in completed),
            details={
                "steps": [item.details for item in completed],
                "completed_steps": len(completed),
            },
        )

    def _run_plan(self, plan: AutomationPlan) -> ActionResult:
        try:
            plan.validate()
        except ValueError as error:
            return ActionResult(
                operation="invalid_plan",
                attempted=False,
                verified=False,
                details={"message": str(error)},
            )
        if len(plan.actions) > self.MAX_ACTIONS:
            return ActionResult(
                operation="action_limit",
                attempted=False,
                verified=False,
                details={"message": "The task exceeds the eight-action limit."},
            )
        return self._continue_plan(
            plan,
            0,
            [],
            deadline=time.monotonic() + self.MAX_TASK_SECONDS,
        )

    def _continue_plan(
        self,
        plan: AutomationPlan,
        start_index: int,
        completed: list[ActionResult],
        *,
        deadline: float,
    ) -> ActionResult:
        for index in range(start_index, len(plan.actions)):
            try:
                self._raise_if_stopped()
            except AutomationStopped:
                return self._stopped_result(plan.task_id, len(completed))
            except AutomationBackendError as error:
                return ActionResult(
                    operation="automation_unavailable",
                    attempted=bool(completed),
                    verified=False,
                    details={
                        "message": str(error),
                        "completed_steps": len(completed),
                    },
                )
            if time.monotonic() > deadline:
                return ActionResult(
                    operation="task_timeout",
                    attempted=bool(completed),
                    verified=False,
                    details={
                        "message": "The automation task reached its 30-second limit; remaining steps were cancelled.",
                        "completed_steps": len(completed),
                        "steps": [item.details for item in completed],
                    },
                )
            action = plan.actions[index]
            if action.risk is not ActionRisk.LOW:
                return self._request_confirmation(plan, index, completed, deadline)
            try:
                result = self._execute_action(action)
            except AutomationStopped:
                return self._stopped_result(plan.task_id, len(completed))
            except (
                AutomationPolicyError,
                AutomationBackendError,
                BrowserAutomationError,
                OSError,
                TimeoutError,
            ) as error:
                if self.stop_event.is_set():
                    return self._stopped_result(plan.task_id, len(completed))
                self.audit_log.record(
                    task_id=plan.task_id,
                    operation=action.kind,
                    category=action.risk.value,
                    attempted=True,
                    verified=False,
                    error_category=type(error).__name__,
                )
                return ActionResult(
                    operation=action.kind,
                    attempted=True,
                    verified=False,
                    details={
                        "message": str(error),
                        "completed_steps": len(completed),
                    },
                )
            completed.append(result)
            self.audit_log.record(
                task_id=plan.task_id,
                operation=action.kind,
                category=action.risk.value,
                attempted=True,
                verified=result.verified,
            )
            if time.monotonic() > deadline:
                return ActionResult(
                    operation="task_timeout",
                    attempted=True,
                    verified=False,
                    details={
                        "message": "The automation task exceeded its 30-second limit; remaining steps were cancelled.",
                        "completed_steps": len(completed),
                        "steps": [item.details for item in completed],
                    },
                )
        return ActionResult(
            operation=plan.description,
            attempted=bool(completed),
            verified=all(item.verified for item in completed),
            details={
                "steps": [item.details for item in completed],
                "completed_steps": len(completed),
            },
        )

    def _request_confirmation(
        self,
        plan: AutomationPlan,
        index: int,
        completed: list[ActionResult],
        deadline: float,
    ) -> ActionResult:
        action = plan.actions[index]
        try:
            target_context = (
                self.browser.confirmation_context()
                if action.kind == "click_browser_button"
                else None
            )
        except BrowserAutomationError as error:
            return ActionResult(
                operation="confirmation_target_unavailable",
                attempted=bool(completed),
                verified=False,
                details={
                    "message": str(error),
                    "completed_steps": len(completed),
                },
            )
        if action.risk is ActionRisk.HIGH and action.kind in {
            "click_browser_button",
            "click_desktop_element",
        }:
            target = (
                f"click the '{action.target}' button on the current browser page"
                if action.kind == "click_browser_button"
                else f"click the '{action.target}' control in the active application"
            )
            warning = " This may send, submit, delete, publish, purchase, or otherwise commit an action."
        elif action.kind == "fill_browser_field":
            host = self.browser.current_host or "the current browser page"
            target = f"fill the '{action.target}' field on {host} with the text from your request"
            warning = " The form will not be submitted."
        elif action.kind == "fill_desktop_field":
            target = f"fill the '{action.target}' field in the active application"
            warning = " The entered text will not be logged."
        elif action.kind == "click_coordinate":
            target = f"click screen coordinate {action.target} in the active window"
            warning = " The coordinate will be checked against a fresh screen observation."
        elif action.kind == "click_browser_button":
            page_url = self.browser.current_url or "the current browser page"
            target = f"click the '{action.target}' button on {page_url}"
            warning = " The page must remain unchanged after approval."
        elif action.kind == "delete_file":
            target = f"delete file {_confirmation_value(action.target or '')}"
            warning = " File deletion is disabled; confirming will not delete the file."
        elif action.kind == "send_message":
            target = (
                f"send a message to {_confirmation_value(action.target or '')} "
                f"with the exact contents: \"{_confirmation_value(action.value or '')}\""
            )
            warning = " Message sending is disabled; confirming will not send it."
        elif action.kind == "purchase_item":
            target = (
                f"purchase {_confirmation_value(action.target or '')} "
                f"for {_confirmation_value(action.value or '')}"
            )
            warning = " Purchases are disabled; confirming will not place an order."
        else:
            target = f"perform {action.kind} on {action.target or 'the active target'}"
            warning = ""
        code = uuid4().hex[:8].upper()
        now = time.monotonic()
        expires_at = min(now + self.CONFIRMATION_SECONDS, deadline)
        valid_seconds = max(0, int(expires_at - now))
        self._pending = PendingAutomation(
            plan=plan,
            action_index=index,
            completed=tuple(completed),
            confirmation_code=code,
            expires_at=expires_at,
            deadline_at=deadline,
            target_context=target_context,
        )
        self.audit_log.record(
            task_id=plan.task_id,
            operation=action.kind,
            category=action.risk.value,
            confirmation_required=True,
            attempted=False,
        )
        return ActionResult(
            operation=action.kind,
            attempted=bool(completed),
            verified=all(item.verified for item in completed) if completed else False,
            requires_confirmation=True,
            confirmation_code=code,
            details={
                "message": f"Confirmation required: {target}.{warning} "
                f"Reply exactly CONFIRM {code} to continue, or CANCEL. "
                f"This confirmation is valid for at most {valid_seconds} seconds.",
                "completed_steps": len(completed),
            },
        )

    def _execute_action(self, action: AutomationAction) -> ActionResult:
        self._raise_if_stopped()
        if action.kind == "delete_file":
            return ActionResult(
                operation=action.kind,
                attempted=False,
                verified=False,
                details={
                    "message": "Confirmation received, but file deletion is disabled. No file was deleted."
                },
            )
        if action.kind == "send_message":
            return ActionResult(
                operation=action.kind,
                attempted=False,
                verified=False,
                details={
                    "message": "Confirmation received, but message sending is disabled. No message was sent."
                },
            )
        if action.kind == "purchase_item":
            return ActionResult(
                operation=action.kind,
                attempted=False,
                verified=False,
                details={
                    "message": "Confirmation received, but purchases are disabled. No order was placed."
                },
            )
        if action.kind == "open_application":
            application = resolve_application_name(action.target or "")
            if application == "browser":
                result = self.browser.open_blank()
                verified = bool(result.verified)
                details = {"application": "Microsoft Edge", "title": result.title}
            else:
                window = self.desktop.open_application(application)
                verified = bool(window.title)
                details = {"application": application, "window_title": window.title}
        elif action.kind == "switch_application":
            application = resolve_application_name(action.target or "")
            if application == "browser":
                result = self.browser.bring_to_front()
                verified = result
                details = {"application": "Microsoft Edge"}
            else:
                window = self.desktop.switch_application(application)
                verified = bool(window.title)
                details = {"application": application, "window_title": window.title}
        elif action.kind == "open_output_folder":
            folder = validate_output_folder()
            window = self.desktop.open_folder(folder)
            verified = bool(window.title)
            details = {"folder": str(folder), "window_title": window.title}
        elif action.kind == "open_url":
            safe_url = validate_public_url(action.target or "")
            page = self.browser.open(safe_url)
            verified = page.verified and bool(page.url)
            details = {"url": _display_url(page.url), "title": page.title}
        elif action.kind == "search_web":
            page = self.browser.search(action.target or "")
            verified = page.verified and bool(page.url)
            details = {"url": _display_url(page.url), "title": page.title}
        elif action.kind == "summarize_page":
            page = self.browser.read_visible_page()
            verified = page.verified and bool(page.summary)
            details = {
                "url": _display_url(page.url),
                "title": page.title,
                "summary": page.summary,
            }
        elif action.kind == "find_page_text":
            result = self.browser.find_text(action.target or "")
            verified = True
            details = result
        elif action.kind == "capture_screen":
            observation = self.screen.observe()
            self._last_screen = observation
            verified = observation.image_width > 0 and observation.image_height > 0
            details = {
                "window_title": observation.window_title,
                "width": observation.image_width,
                "height": observation.image_height,
                "visible_elements": observation.visible_elements[:20],
                "capture": "in-memory only; not saved",
            }
        elif action.kind == "fill_browser_field":
            verified = self.browser.fill_field(action.target or "", action.value or "")
            details = {
                "field": action.target,
                "verified": verified,
                "value": "[entered; not logged]",
            }
        elif action.kind == "click_browser_button":
            verified = self.browser.click_button(action.target or "")
            details = {
                "button": action.target,
                "verified": verified,
                "message": (
                    "The visible page state changed after the click."
                    if verified
                    else "The click was sent, but ARIA could not verify a page-state change."
                ),
            }
        elif action.kind == "click_desktop_element":
            self.desktop.click_element(action.target or "", control_type="Button")
            verified = False
            details = {
                "button": action.target,
                "message": "The click was sent; the resulting application state could not be verified.",
            }
        elif action.kind == "fill_desktop_field":
            if is_sensitive_field(action.target or ""):
                raise AutomationPolicyError(
                    "ARIA will not enter passwords, tokens, or payment details."
                )
            verified = self.desktop.fill_field(action.target or "", action.value or "")
            details = {
                "field": action.target,
                "verified": verified,
                "value": "[entered; not logged]",
            }
        elif action.kind == "click_coordinate":
            self._verify_screen_unchanged()
            coordinates = (action.target or "").split(",")
            self.desktop.click_coordinate(int(coordinates[0]), int(coordinates[1]))
            verified = False
            details = {
                "coordinate": action.target,
                "message": "The click was sent to the requested point; the resulting state could not be verified.",
            }
        else:
            raise AutomationPolicyError("That automation operation is not implemented.")
        return ActionResult(
            operation=action.kind,
            attempted=True,
            verified=verified,
            details=details,
        )

    def _verify_screen_unchanged(self) -> None:
        previous = self._last_screen
        if previous is None or time.monotonic() - previous.captured_at > 60:
            raise AutomationTargetError(
                "Take a fresh screenshot immediately before requesting a coordinate click."
            )
        current = self.screen.observe()
        self._last_screen = current
        if (
            current.window_title != previous.window_title
            or current.bounds != previous.bounds
            or current.image_digest != previous.image_digest
        ):
            raise AutomationTargetError(
                "The screen changed after the screenshot; no coordinate action was performed."
            )

    def _raise_if_stopped(self) -> None:
        if self.stop_event.is_set():
            raise AutomationStopped("Automation has been stopped.")
        if self._emergency_stop_requested():
            raise AutomationStopped("The Escape emergency-stop key was pressed.")

    def _emergency_stop_requested(self) -> bool:
        if self.stop_event.is_set():
            return True
        if self.desktop.emergency_stop_pressed():
            self.stop_event.set()
            self._pending = None
            return True
        return False

    def _stopped_result(self, task_id: str, completed_steps: int = 0) -> ActionResult:
        self.stop_event.set()
        self._pending = None
        close_error = self._close_browser()
        self.audit_log.record(
            task_id=task_id,
            operation="stop",
            category="emergency",
            attempted=True,
            verified=close_error is None,
            error_category="BrowserAutomationError" if close_error else None,
        )
        return ActionResult(
            operation="stop",
            attempted=True,
            verified=close_error is None,
            details={
                "message": (
                    "Automation stopped. Remaining actions were cancelled."
                    if close_error is None
                    else "Automation stopped and remaining actions were cancelled, but the controlled browser may remain open."
                ),
                "completed_steps": completed_steps,
            },
        )

    def _close_browser(self) -> str | None:
        try:
            self.browser.close()
        except BrowserAutomationError as error:
            return str(error)
        return None


def _display_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _confirmation_value(value: str) -> str:
    redacted = redact_secrets(value)
    return (
        redacted.replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
