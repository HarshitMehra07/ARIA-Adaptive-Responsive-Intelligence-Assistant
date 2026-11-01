from __future__ import annotations

import re
from dataclasses import dataclass

from automation.command_parser import ComputerCommand, detect_computer_command
from document_generation.document_intent import DocumentCommand, detect_document_command


@dataclass(frozen=True)
class CapabilityRoute:
    capability: str
    intent: str
    command: ComputerCommand | DocumentCommand | None = None
    target: str | None = None


_SAFETY_REQUEST = re.compile(
    r"\b(?:is|are|can you check|could you check|please check|check whether|"
    r"check if|assess whether|assess if)\b.{0,100}\b"
    r"(?:safe|legitimate|legit|trustworthy|a scam|phishing|malicious)\b"
    r"|\b(?:check|assess|analyze)\b.{0,100}\b"
    r"(?:website|site|domain|url|link)\b.{0,100}\b"
    r"(?:safe|legitimate|legit|trustworthy|scam|phishing|malicious)\b",
    re.IGNORECASE,
)
_URL_OR_DOMAIN = re.compile(
    r"(?:(?:https?://)?(?:www\.)?(?:"
    r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?:\.[a-z0-9-]{2,})+"
    r"|\d{1,3}(?:\.\d{1,3}){3}|\[[0-9a-f:]+\])"
    r"(?::\d{1,5})?(?:/[^\s<>\"']*)?)",
    re.IGNORECASE,
)
_UNAVAILABLE_MEDIA_REQUEST = re.compile(
    r"\b(?:generate|create|make|produce)\b.{0,80}\b"
    r"(?:image|picture|illustration|video|movie|animation|audio|music|song|"
    r"voice[- ]over|voiceover)\b"
    r"|\b(?:generate|create|make|produce)\b.{0,80}\b"
    r"(?:for|from)\b.{0,30}\b(?:image|picture|video|audio|music)\b",
    re.IGNORECASE,
)


def requests_web_research(text: str) -> bool:
    lowered = str(text or "").casefold()
    explicit_phrases = (
        "search the web",
        "web search",
        "web research",
        "research online",
        "look this up online",
        "look it up online",
        "look up on the web",
        "find sources online",
        "find the latest",
        "find latest",
        "search for the latest",
        "search for latest",
        "official documentation",
    )
    return any(phrase in lowered for phrase in explicit_phrases) or bool(
        re.search(
            r"\b(?:research|search online|look up online)\b",
            lowered,
        )
    )


class CapabilityRouter:
    """Select an implemented ARIA capability without delegating to page content."""

    @staticmethod
    def resolve(text: str) -> CapabilityRoute | None:
        original = str(text or "").strip()
        if not original:
            return None

        computer_command = detect_computer_command(original)
        if computer_command is not None:
            return CapabilityRoute(
                "automation",
                "computer_control",
                command=computer_command,
            )

        document_command = detect_document_command(original)
        if document_command is not None:
            return CapabilityRoute(
                "document_generation",
                f"document_{document_command.action}",
                command=document_command,
            )

        if _SAFETY_REQUEST.search(original):
            match = _URL_OR_DOMAIN.search(original)
            return CapabilityRoute(
                "website_safety",
                "website_safety",
                target=match.group(0).rstrip(".,!?;:)") if match else None,
            )

        if requests_web_research(original):
            return CapabilityRoute("web_research", "web_research")

        if _UNAVAILABLE_MEDIA_REQUEST.search(original):
            capability = CapabilityRouter._media_type(original)
            return CapabilityRoute(
                capability,
                "capability_unavailable",
            )

        return None

    @staticmethod
    def _media_type(text: str) -> str:
        lowered = text.casefold()
        if re.search(r"\b(?:video|movie|animation)\b", lowered):
            return "video_generation"
        if re.search(r"\b(?:audio|music|song|voice[- ]over|voiceover)\b", lowered):
            return "audio_generation"
        return "image_generation"
