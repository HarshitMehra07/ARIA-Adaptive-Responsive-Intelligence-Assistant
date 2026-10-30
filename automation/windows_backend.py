from __future__ import annotations

import ctypes
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from automation.policy import (
    AutomationPolicyError,
    find_application_executable,
)


class AutomationBackendError(Exception):
    """A safe, user-presentable Windows automation error."""


class AutomationUnavailableError(AutomationBackendError):
    """A required Windows automation capability is unavailable."""


class AutomationTargetError(AutomationBackendError):
    """A target window or UI element could not be identified unambiguously."""


@dataclass(frozen=True)
class WindowInfo:
    title: str
    bounds: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class ScreenCapture:
    image: object
    window: WindowInfo
    width: int
    height: int


class WindowsDesktopBackend:
    MAX_CAPTURE_PIXELS = 25_000_000
    APP_WINDOW_PATTERNS = {
        "notepad": ("notepad",),
        "vscode": ("visual studio code",),
        "browser": ("microsoft edge", "google chrome", "chrome"),
    }

    def __init__(self, *, emergency_key: int = 0x1B):
        self.emergency_key = emergency_key

    @staticmethod
    def _require_windows() -> None:
        if os.name != "nt":
            raise AutomationUnavailableError("Desktop control is available only on Windows.")

    def emergency_stop_pressed(self) -> bool:
        self._require_windows()
        return bool(ctypes.windll.user32.GetAsyncKeyState(self.emergency_key) & 0x8000)

    def active_window(self) -> WindowInfo:
        self._require_windows()
        try:
            window = self._desktop().get_active()
        except Exception as error:
            raise AutomationTargetError("The active window could not be identified.") from error
        if window is None:
            raise AutomationTargetError("There is no active window to inspect.")
        return self._window_info(window)

    def list_windows(self) -> list[WindowInfo]:
        self._require_windows()
        try:
            windows = self._desktop().windows(visible_only=True)
        except Exception as error:
            raise AutomationBackendError("Windows UI Automation could not enumerate visible windows.") from error
        results = []
        for window in windows:
            info = self._window_info(window)
            if info.title.strip():
                results.append(info)
        return results[:100]

    def open_application(self, application: str) -> WindowInfo:
        self._require_windows()
        if application == "browser":
            raise AutomationUnavailableError(
                "Use the controlled browser session to open Edge; ARIA does not reuse an authenticated browser profile."
            )
        try:
            executable = find_application_executable(application)
        except AutomationPolicyError as error:
            raise AutomationUnavailableError(str(error)) from error
        try:
            subprocess.Popen(
                [str(executable)],
                shell=False,
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except OSError as error:
            raise AutomationBackendError("The approved application could not be launched.") from error
        return self._wait_for_window(application, timeout_seconds=8)

    def open_folder(self, path: Path) -> WindowInfo:
        self._require_windows()
        if not path.is_dir():
            raise AutomationTargetError("The ARIA output folder could not be opened.")
        try:
            os.startfile(str(path))
        except OSError as error:
            raise AutomationBackendError("Windows could not open the ARIA output folder.") from error
        return self._wait_for_window("folder", timeout_seconds=5, expected_title=path.name)

    def switch_application(self, application: str) -> WindowInfo:
        self._require_windows()
        patterns = self.APP_WINDOW_PATTERNS.get(application)
        if not patterns:
            raise AutomationUnavailableError("That application cannot be switched to.")
        candidates = [
            window
            for window in self._desktop().windows(visible_only=True)
            if any(pattern in window.window_text().casefold() for pattern in patterns)
        ]
        if len(candidates) != 1:
            if not candidates:
                raise AutomationTargetError("No matching application window is open.")
            raise AutomationTargetError("More than one matching application window is open; the target is ambiguous.")
        window = candidates[0]
        try:
            window.set_focus()
        except Exception as error:
            raise AutomationBackendError("Windows could not focus the selected application.") from error
        current = self.active_window()
        if current.title != window.window_text():
            raise AutomationBackendError("The requested application did not become the active window.")
        return current

    def capture_active_window(self) -> ScreenCapture:
        self._require_windows()
        window = self._active_wrapper()
        info = self._window_info(window)
        if info.bounds is None:
            raise AutomationBackendError("The active window bounds are unavailable.")
        left, top, right, bottom = info.bounds
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0 or width * height > self.MAX_CAPTURE_PIXELS:
            raise AutomationBackendError("The active window size is invalid or exceeds the capture limit.")
        try:
            from PIL import ImageGrab

            image = ImageGrab.grab(bbox=info.bounds, all_screens=True)
        except (OSError, RuntimeError) as error:
            raise AutomationUnavailableError("Windows could not capture the active window.") from error
        if image.width * image.height > self.MAX_CAPTURE_PIXELS:
            raise AutomationBackendError("The captured screen exceeds the image-size limit.")
        return ScreenCapture(image=image, window=info, width=image.width, height=image.height)

    def visible_elements(self, *, maximum: int = 100) -> list[dict[str, str]]:
        self._require_windows()
        window = self._active_wrapper()
        results = []
        try:
            descendants = window.descendants()
        except Exception as error:
            raise AutomationUnavailableError("The active application does not expose accessible UI elements.") from error
        for control in descendants:
            try:
                info = control.element_info
                if not info.is_visible() or info.is_password:
                    continue
                name = (info.name or "").strip()
                control_type = (info.control_type or "").strip()
                if not name or len(name) > 160 or control_type not in {
                    "Button",
                    "CheckBox",
                    "ComboBox",
                    "Edit",
                    "Hyperlink",
                    "ListItem",
                    "MenuItem",
                    "RadioButton",
                    "TabItem",
                    "Text",
                }:
                    continue
                results.append({"name": name, "control_type": control_type})
                if len(results) >= maximum:
                    break
            except (AttributeError, RuntimeError):
                continue
        return results

    def click_element(self, name: str, *, control_type: str | None = None) -> None:
        self._require_windows()
        controls = self._find_elements(name, control_type=control_type)
        if len(controls) != 1:
            self._raise_ambiguous_target(controls)
        control = controls[0]
        if control.element_info.is_password or not control.is_enabled():
            raise AutomationTargetError("The selected UI element is unavailable.")
        try:
            control.click_input()
        except Exception as error:
            raise AutomationBackendError("The selected UI element could not be clicked.") from error

    def fill_field(self, name: str, value: str, *, maximum_characters: int = 2_000) -> bool:
        self._require_windows()
        if not value or len(value) > maximum_characters:
            raise AutomationTargetError("The field text is empty or exceeds the input limit.")
        controls = self._find_elements(name, control_type="Edit")
        if len(controls) != 1:
            self._raise_ambiguous_target(controls)
        control = controls[0]
        if control.element_info.is_password or not control.is_enabled():
            raise AutomationTargetError("The selected text field is unavailable or sensitive.")
        try:
            control.set_edit_text(value)
            return control.get_value() == value
        except Exception as error:
            raise AutomationBackendError("ARIA could not safely fill and verify the selected field.") from error

    def move_pointer(self, x: int, y: int) -> None:
        self._require_windows()
        bounds = self.active_window().bounds
        if bounds is None or not (bounds[0] <= x < bounds[2] and bounds[1] <= y < bounds[3]):
            raise AutomationTargetError("The pointer coordinate is outside the active window.")
        try:
            from pywinauto import mouse

            mouse.move(coords=(x, y))
        except ImportError as error:
            raise AutomationUnavailableError("Mouse control requires pywinauto.") from error

    def click_coordinate(self, x: int, y: int) -> None:
        self._require_windows()
        bounds = self.active_window().bounds
        if bounds is None or not (bounds[0] <= x < bounds[2] and bounds[1] <= y < bounds[3]):
            raise AutomationTargetError("The click coordinate is outside the active window.")
        try:
            from pywinauto import mouse

            mouse.click(button="left", coords=(x, y))
        except ImportError as error:
            raise AutomationUnavailableError("Mouse control requires pywinauto.") from error

    def _find_elements(self, name: str, *, control_type: str | None = None):
        if not name or len(name) > 160:
            raise AutomationTargetError("Provide the exact accessible name of a UI element.")
        window = self._active_wrapper()
        try:
            candidates = window.descendants()
        except Exception as error:
            raise AutomationUnavailableError("The active application does not expose accessible UI elements.") from error
        return [
            control
            for control in candidates
            if control.element_info.is_visible()
            and control.element_info.name == name
            and not control.element_info.is_password
            and (control_type is None or control.element_info.control_type == control_type)
        ]

    @staticmethod
    def _raise_ambiguous_target(controls) -> None:
        if controls:
            raise AutomationTargetError("The requested UI target is ambiguous; use a more specific accessible name.")
        raise AutomationTargetError("No visible UI element matches that exact accessible name.")

    def _wait_for_window(
        self,
        application: str,
        *,
        timeout_seconds: float,
        expected_title: str | None = None,
    ) -> WindowInfo:
        deadline = time.monotonic() + timeout_seconds
        patterns = self.APP_WINDOW_PATTERNS.get(application, ())
        while time.monotonic() < deadline:
            matches = [
                window
                for window in self._desktop().windows(visible_only=True)
                if (
                    expected_title is not None
                    and expected_title.casefold() in window.window_text().casefold()
                )
                or any(pattern in window.window_text().casefold() for pattern in patterns)
            ]
            if matches:
                matches[0].set_focus()
                focused = self.active_window()
                if expected_title is None or expected_title.casefold() in focused.title.casefold():
                    return focused
            time.sleep(0.1)
        raise AutomationBackendError("The application launched but its expected window was not verified.")

    def _active_wrapper(self):
        try:
            window = self._desktop().get_active()
        except Exception as error:
            raise AutomationTargetError("The active application window could not be identified.") from error
        if window is None:
            raise AutomationTargetError("There is no active application window.")
        return window

    @staticmethod
    def _window_info(window) -> WindowInfo:
        try:
            title = (window.window_text() or "").strip()[:200]
            rect = window.rectangle()
            bounds = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            return WindowInfo(title=title, bounds=bounds)
        except Exception as error:
            raise AutomationBackendError("Window details could not be read.") from error

    @staticmethod
    def _desktop():
        if os.name != "nt":
            raise AutomationUnavailableError("Windows UI Automation is available only on Windows.")
        try:
            from pywinauto import Desktop
        except ImportError as error:
            raise AutomationUnavailableError(
                "Windows UI Automation requires pywinauto. Install project dependencies and restart ARIA."
            ) from error
        return Desktop(backend="uia")
