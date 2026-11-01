from __future__ import annotations

import re
from dataclasses import dataclass

from document_generation.document_spec import DocumentFormat


@dataclass(frozen=True)
class DocumentCommand:
    action: str
    document_format: DocumentFormat | None = None


_FORMAT_PATTERNS = (
    (DocumentFormat.POWERPOINT, r"\b(?:power\s*point|pptx|presentation|slides?)\b"),
    (DocumentFormat.WORD, r"\b(?:word|docx|word document)\b"),
    (DocumentFormat.PDF, r"\bpdf\b"),
    (DocumentFormat.EXCEL, r"\b(?:excel|xlsx|spreadsheet|workbook)\b"),
    (DocumentFormat.MARKDOWN, r"\b(?:markdown|md|readme)\b"),
    (DocumentFormat.TEXT, r"\b(?:plain text|text file|txt)\b"),
)
_CREATE_VERBS = r"\b(?:create|generate|make|write|draft|export|save|turn|convert|build|prepare)\b"
_DOCUMENT_NOUNS = re.compile(
    r"\b(?:report|proposal|guide|planner|tracker|document|presentation|"
    r"workbook|spreadsheet|readme|budget)\b",
    re.IGNORECASE,
)
_FORMAT_WORDS = re.compile(
    r"\b(?:csv|html|json|rtf|odt|ods|keynote|pages|xml|ppt|doc|xls)\b",
    re.IGNORECASE,
)


def detect_document_command(text: str) -> DocumentCommand | None:
    lowered = text.strip().lower()
    if not lowered:
        return None

    if re.search(r"\b(?:list|show)\b.*\b(?:generated|created)\s+files\b", lowered) or (
        re.search(r"\b(?:list|show)\s+my\s+files\b", lowered)
        and "generated" in lowered
    ):
        return DocumentCommand("list")

    if re.search(r"\b(?:summari[sz]e|read)\b.*\b(?:document|file)\b", lowered):
        return DocumentCommand("summarize")

    if not re.search(_CREATE_VERBS, lowered):
        return None

    for document_format, pattern in _FORMAT_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return DocumentCommand("generate", document_format)

    if _FORMAT_WORDS.search(lowered):
        return DocumentCommand("unsupported")
    if _DOCUMENT_NOUNS.search(lowered):
        if re.search(r"\breadme\b", lowered):
            return DocumentCommand("generate", DocumentFormat.MARKDOWN)
        if re.search(r"\b(?:planner|tracker|budget)\b", lowered):
            return DocumentCommand("generate", DocumentFormat.EXCEL)
        return DocumentCommand("generate", DocumentFormat.WORD)
    if re.search(r"\bfile\b", lowered):
        return DocumentCommand("unsupported")
    return None


def requests_live_research(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "research ",
            "research this",
            "research online",
            "search the web",
            "web research",
            "look this up online",
            "look it up online",
            "find the latest",
            "find latest",
            "find recent",
            "official documentation",
        )
    ) or bool(re.search(r"\b(?:recent|latest)\b.*\b(?:research|developments|releases|documentation)\b", lowered))


def requested_slide_count(text: str) -> int | None:
    match = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s*[- ]?\s*slides?\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    count_text = match.group(1).lower()
    count = (
        int(count_text)
        if count_text.isdigit()
        else ("one two three four five six seven eight nine ten".split().index(count_text) + 1)
    )
    if not 2 <= count <= 30:
        raise ValueError("PowerPoint slide count must be between 2 and 30.")
    return count


def requests_totals(text: str) -> bool:
    return bool(re.search(r"\b(?:total|sum|formula|weekly hours)\b", text, re.IGNORECASE))
