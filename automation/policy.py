from __future__ import annotations

import ipaddress
import re
import socket
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from config.settings import PROJECT_ROOT
from document_generation.file_manager import FileManagementError, GeneratedFileManager


class AutomationPolicyError(Exception):
    """A safe, user-presentable policy or target validation error."""


APPLICATIONS = {
    "notepad": "notepad",
    "vscode": "vscode",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "code": "vscode",
    "edge": "browser",
    "microsoft edge": "browser",
    "chrome": "browser",
    "browser": "browser",
}

_PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home")
DNS_TIMEOUT_SECONDS = 3.0
_DNS_HOST_PATTERN = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)


def resolve_public_host(hostname: str, port: int = 443) -> list[str]:
    result: Future[list[str]] = Future()

    def resolve() -> None:
        try:
            result.set_result(
                sorted(
                    {
                        entry[4][0]
                        for entry in socket.getaddrinfo(
                            hostname,
                            port,
                            type=socket.SOCK_STREAM,
                        )
                    }
                )
            )
        except OSError as error:
            result.set_exception(error)

    threading.Thread(target=resolve, daemon=True).start()
    try:
        return result.result(timeout=DNS_TIMEOUT_SECONDS)
    except FutureTimeoutError as error:
        raise AutomationPolicyError("The website host did not resolve within the safety timeout.") from error
    except OSError as error:
        raise AutomationPolicyError("The website host could not be resolved.") from error


def resolve_public_url(
    value: str,
    *,
    resolver=resolve_public_host,
) -> tuple[str, str | None]:
    if not isinstance(value, str) or not value.strip() or len(value) > 2_000:
        raise AutomationPolicyError("Provide a complete public HTTPS URL.")
    try:
        parts = urlsplit(value.strip())
        hostname = (parts.hostname or "").rstrip(".").lower()
        port = parts.port
    except ValueError as error:
        raise AutomationPolicyError("The URL is invalid.") from error
    if (
        parts.scheme.lower() != "https"
        or not hostname
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or any(ord(char) < 32 or char.isspace() for char in value)
        or hostname == "localhost"
        or hostname.endswith(_PRIVATE_SUFFIXES)
        or "." not in hostname
    ):
        raise AutomationPolicyError(
            "Only public HTTPS websites on the standard port are allowed."
        )

    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        addresses = []
    if not addresses:
        try:
            dns_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise AutomationPolicyError("The website host name is invalid.") from error
        if not _DNS_HOST_PATTERN.fullmatch(dns_hostname):
            raise AutomationPolicyError("The website host name is invalid.")
        addresses = []
        for resolved in resolver(dns_hostname, 443):
            try:
                addresses.append(ipaddress.ip_address(resolved))
            except ValueError as error:
                raise AutomationPolicyError("The website resolved to an invalid network address.") from error
    if not addresses or any(not address.is_global for address in addresses):
        raise AutomationPolicyError(
            "Websites that resolve to private, local, or reserved network addresses are blocked."
        )
    path = parts.path or "/"
    pinned_address = None
    if not _is_ip_address(hostname):
        pinned_address = str(
            sorted(addresses, key=lambda address: (address.version != 4, str(address)))[0]
        )
        hostname = hostname.encode("idna").decode("ascii")
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    return urlunsplit(("https", netloc, path, parts.query, parts.fragment)), pinned_address


def validate_public_url(
    value: str,
    *,
    resolver=resolve_public_host,
) -> str:
    return resolve_public_url(value, resolver=resolver)[0]


def _is_ip_address(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def resolve_application_name(value: str) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip().lower())
    application = APPLICATIONS.get(normalized)
    if application is None:
        raise AutomationPolicyError(
            "That application is not allowlisted. ARIA supports Notepad, VS Code, and the browser."
        )
    return application


def validate_output_folder(path: str | Path | None = None) -> Path:
    manager = GeneratedFileManager()
    try:
        output_root = manager.ensure_output_dir()
    except FileManagementError as error:
        raise AutomationPolicyError(str(error)) from error
    if path is not None:
        requested = Path(path).expanduser()
        try:
            resolved = requested.resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise AutomationPolicyError("The requested folder path is invalid.") from error
        if resolved != output_root:
            raise AutomationPolicyError("Only ARIA's configured output folder may be opened.")
    return output_root


def classify_action(kind: str, target: str | None = None) -> str:
    if kind in {
        "open_application",
        "switch_application",
        "open_output_folder",
        "open_url",
        "search_web",
        "summarize_page",
        "find_page_text",
        "capture_screen",
    }:
        return "low"
    if kind in {"delete_file", "send_message", "purchase_item"}:
        return "high"
    lowered = (target or "").lower()
    if kind in {"click_browser_button", "click_desktop_element"} and re.search(
        r"\b(send|submit|publish|delete|remove|buy|purchase|pay|confirm|transfer|install)\b",
        lowered,
    ):
        return "high"
    if kind in {
        "fill_browser_field",
        "fill_desktop_field",
        "click_browser_button",
        "click_desktop_element",
    }:
        return "medium"
    return "high"


def is_sensitive_field(label: str) -> bool:
    return bool(
        re.search(
            r"\b(password|passcode|secret|token|api key|credit card|card number|"
            r"security code|cvv|one.time code|verification code)\b",
            label,
            re.IGNORECASE,
        )
    )


def find_application_executable(application: str) -> Path:
    import os

    if application == "notepad":
        executable = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "notepad.exe"
        if executable.is_file():
            return executable
    elif application == "vscode":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft VS Code" / "Code.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft VS Code" / "Code.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
    raise AutomationPolicyError(
        "The approved application is not installed at a known, safe location."
    )
