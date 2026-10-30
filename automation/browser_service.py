from __future__ import annotations

import re
import hashlib
import time
from dataclasses import dataclass
from urllib.parse import quote_plus, urlsplit

from automation.policy import (
    AutomationPolicyError,
    is_sensitive_field,
    resolve_public_url,
    validate_public_url,
)
from memory.memory_manager import redact_secrets


class BrowserAutomationError(Exception):
    """A safe, user-presentable controlled-browser error."""


@dataclass(frozen=True)
class BrowserPageResult:
    url: str
    title: str
    text: str
    summary: str | None = None
    verified: bool = True


class BrowserAutomation:
    NAVIGATION_TIMEOUT_MS = 15_000
    PAGE_TEXT_LIMIT = 40_000
    SEARCH_TEXT_LIMIT = 300

    def __init__(
        self,
        *,
        resolver=None,
        browser_channel: str = "msedge",
        emergency_check=None,
    ):
        self._resolver = resolver
        self._browser_channel = browser_channel
        self._emergency_check = emergency_check
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._approved_host: str | None = None
        self._pinned_host: str | None = None
        self._pinned_address: str | None = None

    def open(self, url: str) -> BrowserPageResult:
        try:
            if self._resolver is None:
                normalized, pinned_address = resolve_public_url(url)
            else:
                normalized, pinned_address = resolve_public_url(
                    url,
                    resolver=self._resolver,
                )
        except AutomationPolicyError as error:
            raise BrowserAutomationError(str(error)) from error
        approved_host = urlsplit(normalized).hostname
        self._ensure_browser(approved_host, pinned_address)
        try:
            self._approved_host = approved_host
            response = self._page.goto(
                normalized,
                wait_until="domcontentloaded",
                timeout=self.NAVIGATION_TIMEOUT_MS,
            )
            if response is not None and response.status >= 400:
                raise BrowserAutomationError(
                    f"The website returned HTTP {response.status}; it was not treated as a successful page load."
                )
            final_url = self._validate_url(self._page.url)
            if urlsplit(final_url).hostname != self._approved_host:
                raise BrowserAutomationError(
                    "The website redirected to a different host; navigation stopped for safety."
                )
            title = (self._page.title() or "")[:200]
            return BrowserPageResult(final_url, title, "", verified=True)
        except BrowserAutomationError:
            raise
        except AutomationPolicyError as error:
            raise BrowserAutomationError(str(error)) from error
        except (TimeoutError, OSError) as error:
            raise BrowserAutomationError("The browser could not load the requested website in time.") from error
        except Exception as error:
            raise BrowserAutomationError("The controlled browser failed to open the requested page.") from error

    def open_blank(self) -> BrowserPageResult:
        self._ensure_browser()
        try:
            self._page.bring_to_front()
            return BrowserPageResult(
                url="about:blank",
                title=(self._page.title() or "Microsoft Edge")[:200],
                text="",
                verified=True,
            )
        except Exception as error:
            raise BrowserAutomationError("The controlled browser could not be brought to the foreground.") from error

    def bring_to_front(self) -> bool:
        if self._page is None:
            self.open_blank()
        try:
            self._page.bring_to_front()
            return bool(self._page.is_visible())
        except Exception as error:
            raise BrowserAutomationError("The controlled browser could not be brought to the foreground.") from error

    @property
    def current_host(self) -> str | None:
        if self._page is None:
            return None
        return urlsplit(self._page.url).hostname

    @property
    def current_url(self) -> str | None:
        if self._page is None:
            return None
        parts = urlsplit(self._page.url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def confirmation_context(self) -> str:
        page = self._require_page()
        try:
            url = self._validate_url(page.url)
            title = (page.title() or "")[:200]
            body = page.locator("body").inner_text(timeout=3_000)[: self.PAGE_TEXT_LIMIT]
        except Exception as error:
            raise BrowserAutomationError(
                "The browser page changed or could not be verified; the pending click was cancelled."
            ) from error
        fingerprint = "\0".join((url, title, body))
        return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()

    def search(self, query: str) -> BrowserPageResult:
        cleaned = (query or "").strip()
        if not cleaned or len(cleaned) > self.SEARCH_TEXT_LIMIT:
            raise BrowserAutomationError("Provide a search topic of at most 300 characters.")
        return self.open(f"https://www.bing.com/search?q={quote_plus(cleaned)}")

    def read_visible_page(self) -> BrowserPageResult:
        page = self._require_page()
        try:
            text = page.locator("body").inner_text(timeout=3_000)
        except Exception as error:
            raise BrowserAutomationError("The visible page text could not be read.") from error
        if not text.strip():
            raise BrowserAutomationError("The visible page contains no readable text.")
        partial = len(text) > self.PAGE_TEXT_LIMIT
        text = text[: self.PAGE_TEXT_LIMIT]
        from document_generation.document_reader import extractive_summary

        summary = extractive_summary(redact_secrets(text), max_sentences=6)
        return BrowserPageResult(
            url=self._validate_url(page.url),
            title=(page.title() or "")[:200],
            text=text,
            summary=summary + ("\n[Page text was truncated at the safety limit.]" if partial else ""),
            verified=True,
        )

    def find_text(self, value: str) -> dict[str, str | int]:
        target = (value or "").strip()
        if not target or len(target) > 160:
            raise BrowserAutomationError("Provide a search term of at most 160 characters.")
        page = self._require_page()
        try:
            body_text = page.locator("body").inner_text(timeout=3_000)[: self.PAGE_TEXT_LIMIT]
        except Exception as error:
            raise BrowserAutomationError("The visible page text could not be searched.") from error
        matches = list(re.finditer(re.escape(target), body_text, flags=re.IGNORECASE))
        if not matches:
            return {"term": target, "match_count": 0, "excerpt": ""}
        first = matches[0]
        excerpt = body_text[max(0, first.start() - 100) : first.end() + 180].replace("\n", " ")
        return {
            "term": target,
            "match_count": len(matches),
            "excerpt": excerpt[:300],
        }

    def fill_field(self, label: str, value: str) -> bool:
        if not label or len(label) > 160 or not value or len(value) > 2_000:
            raise BrowserAutomationError("A field label and text of at most 2,000 characters are required.")
        if is_sensitive_field(label):
            raise BrowserAutomationError("ARIA will not enter or handle passwords, tokens, or payment details.")
        page = self._require_page()
        try:
            field = page.get_by_label(label, exact=True)
            if field.count() != 1 or not field.is_visible() or not field.is_enabled():
                raise BrowserAutomationError("The form field is missing, hidden, disabled, or ambiguous.")
            field_type = (field.get_attribute("type") or "text").casefold()
            if field_type in {"password", "file", "hidden"}:
                raise BrowserAutomationError("That field type is not supported.")
            field.fill(value, timeout=3_000)
            return field.input_value(timeout=3_000) == value
        except BrowserAutomationError:
            raise
        except Exception as error:
            raise BrowserAutomationError("ARIA could not fill and verify the selected form field.") from error

    def click_button(self, label: str) -> bool:
        if not label or len(label) > 120:
            raise BrowserAutomationError("Provide the exact accessible name of the button.")
        page = self._require_page()
        try:
            button = page.get_by_role("button", name=label, exact=True)
            if button.count() != 1 or not button.is_visible() or not button.is_enabled():
                raise BrowserAutomationError("The requested button is missing, disabled, or ambiguous.")
            before = (page.url, page.title())
            button.click(timeout=3_000)
            page.wait_for_timeout(250)
            after = (page.url, page.title())
            return before != after
        except BrowserAutomationError:
            raise
        except Exception as error:
            raise BrowserAutomationError("The browser could not click and verify the requested button.") from error

    def close(self) -> None:
        errors = []
        for resource, method_name in (
            (self._context, "close"),
            (self._browser, "close"),
            (self._playwright, "stop"),
        ):
            if resource is not None:
                try:
                    getattr(resource, method_name)()
                except Exception as error:
                    errors.append(error)
        self._context = None
        self._browser = None
        self._playwright = None
        self._page = None
        self._approved_host = None
        self._pinned_host = None
        self._pinned_address = None
        if errors:
            raise BrowserAutomationError(
                "The controlled browser session could not be shut down cleanly."
            ) from errors[0]

    def _ensure_browser(
        self,
        host: str | None = None,
        pinned_address: str | None = None,
    ) -> None:
        if (
            self._page is not None
            and self._pinned_host == host
            and self._pinned_address == pinned_address
        ):
            return
        if self._page is not None or self._playwright is not None:
            self.close()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserAutomationError(
                "Browser automation requires Playwright. Install the project dependencies and restart ARIA."
            ) from error
        try:
            self._playwright = sync_playwright().start()
            launch_options = {
                "channel": self._browser_channel,
                "headless": False,
                "timeout": self.NAVIGATION_TIMEOUT_MS,
                "args": [
                    "--disable-quic",
                    "--disable-features=UseDnsHttpsSvcbAlpn",
                    "--no-proxy-server",
                ],
            }
            if host and pinned_address:
                launch_options["args"].append(
                    f"--host-resolver-rules=MAP {host} {pinned_address}"
                )
            self._browser = self._playwright.chromium.launch(
                **launch_options,
            )
            self._context = self._browser.new_context(
                accept_downloads=False,
                java_script_enabled=False,
                service_workers="block",
            )
            self._context.route("**/*", self._guard_request)
            self._page = self._context.new_page()
            self._pinned_host = host
            self._pinned_address = pinned_address
        except Exception as error:
            self.close()
            raise BrowserAutomationError(
                "Microsoft Edge could not be started through the controlled browser. "
                "Install or repair Edge, then try again."
            ) from error

    def _guard_request(self, route) -> None:
        url = route.request.url
        try:
            if self._emergency_check is not None and self._emergency_check():
                route.abort()
                return
            if url == "about:blank":
                route.continue_()
                return
            validated = self._validate_url(url)
            host = urlsplit(validated).hostname
            if self._approved_host and host != self._approved_host:
                route.abort()
                return
            route.continue_()
        except AutomationPolicyError:
            route.abort()

    def _validate_url(self, url: str) -> str:
        if self._resolver is None:
            return validate_public_url(url)
        return validate_public_url(url, resolver=self._resolver)

    def _require_page(self):
        if self._page is None:
            raise BrowserAutomationError("No controlled browser page is open.")
        return self._page
