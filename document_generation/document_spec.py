from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Any
from urllib.parse import urlsplit


class DocumentFormat(str, Enum):
    POWERPOINT = "pptx"
    WORD = "docx"
    PDF = "pdf"
    EXCEL = "xlsx"
    TEXT = "txt"
    MARKDOWN = "md"


CellValue = str | int | float | bool | None


@dataclass(frozen=True)
class DataTable:
    headers: list[str]
    rows: list[list[CellValue]]


@dataclass(frozen=True)
class WorksheetSpec:
    name: str
    headers: list[str]
    rows: list[list[CellValue]]


@dataclass(frozen=True)
class DocumentSection:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    tables: list[DataTable] = field(default_factory=list)
    code_blocks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceReference:
    title: str
    url: str
    published_date: str | None = None


@dataclass(frozen=True)
class DocumentSpec:
    format: DocumentFormat
    title: str
    sections: list[DocumentSection]
    subtitle: str | None = None
    audience: str | None = None
    slide_count: int | None = None
    worksheets: list[WorksheetSpec] = field(default_factory=list)
    sources: list[SourceReference] = field(default_factory=list)
    include_totals: bool = False
    output_filename: str | None = None
    formatting: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        document_format: DocumentFormat,
        payload: Any,
        *,
        expected_slide_count: int | None = None,
        sources: list[SourceReference] | None = None,
        include_totals: bool = False,
    ) -> DocumentSpec:
        if not isinstance(payload, dict):
            raise ValueError("The generated document content must be a JSON object.")

        title = _required_text(payload.get("title"), "title", maximum=160)
        subtitle = _optional_text(payload.get("subtitle"), "subtitle", maximum=240)
        audience = _optional_text(payload.get("audience"), "audience", maximum=160)
        output_filename = _optional_text(payload.get("output_filename"), "output filename", maximum=160)
        formatting = _parse_formatting(payload.get("formatting", {}))

        raw_sections = payload.get("sections", [])
        if not isinstance(raw_sections, list) or len(raw_sections) > 50:
            raise ValueError("The document must contain no more than 50 sections.")
        sections = [_parse_section(item) for item in raw_sections]

        raw_worksheets = payload.get("worksheets", [])
        if not isinstance(raw_worksheets, list) or len(raw_worksheets) > 20:
            raise ValueError("The workbook must contain no more than 20 worksheets.")
        worksheets = [_parse_worksheet(item) for item in raw_worksheets]

        slide_count = expected_slide_count
        if document_format is DocumentFormat.POWERPOINT:
            slide_count = expected_slide_count or _bounded_int(
                payload.get("slide_count", 6), "slide_count", minimum=2, maximum=30
            )
            if len(sections) != slide_count - 1:
                raise ValueError(
                    f"The presentation needs exactly {slide_count - 1} content sections "
                    "in addition to its title slide."
                )

        spec = cls(
            format=document_format,
            title=title,
            subtitle=subtitle,
            audience=audience,
            sections=sections,
            slide_count=slide_count,
            worksheets=worksheets,
            sources=list(sources or []),
            include_totals=include_totals,
            output_filename=output_filename,
            formatting=formatting,
        )
        spec.validate()
        return spec

    def validate(self) -> None:
        if not isinstance(self.format, DocumentFormat):
            raise ValueError("The document format is not supported.")
        if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 160:
            raise ValueError("A document title of at most 160 characters is required.")
        if self.subtitle is not None and (
            not isinstance(self.subtitle, str) or len(self.subtitle) > 240
        ):
            raise ValueError("The document subtitle must contain at most 240 characters.")
        if self.audience is not None and (
            not isinstance(self.audience, str) or len(self.audience) > 160
        ):
            raise ValueError("The document audience must contain at most 160 characters.")
        if self.output_filename is not None and (
            not isinstance(self.output_filename, str)
            or not self.output_filename.strip()
            or len(self.output_filename) > 160
        ):
            raise ValueError("The output filename must contain at most 160 characters.")
        if not isinstance(self.formatting, dict) or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or len(key) > 32
            or len(value) > 100
            for key, value in self.formatting.items()
        ):
            raise ValueError("Document formatting preferences are invalid.")
        if not isinstance(self.sections, list) or not isinstance(self.worksheets, list):
            raise ValueError("Document sections and worksheets must be lists.")
        if not isinstance(self.sources, list):
            raise ValueError("Document sources must be a list.")
        if len(self.sections) > 50 or len(self.worksheets) > 20:
            raise ValueError("The document contains too many sections or worksheets.")

        total_chars = len(self.title) + len(self.subtitle or "")
        total_cells = 0
        for section in self.sections:
            if not isinstance(section, DocumentSection):
                raise ValueError("Each document section must be a valid section specification.")
            if (
                not isinstance(section.heading, str)
                or not section.heading.strip()
                or len(section.heading) > 160
            ):
                raise ValueError("Section headings must contain at most 160 characters.")
            if (
                not isinstance(section.paragraphs, list)
                or not isinstance(section.bullets, list)
                or not isinstance(section.code_blocks, list)
                or not isinstance(section.tables, list)
            ):
                raise ValueError("Section paragraphs, bullets, code blocks, and tables must be lists.")
            if any(
                not isinstance(value, str) or len(value) > 2_000
                for value in section.paragraphs + section.bullets + section.code_blocks
            ):
                raise ValueError("Section text and code blocks must be at most 2,000 characters.")
            if (
                len(section.paragraphs) > 30
                or len(section.bullets) > 30
                or len(section.code_blocks) > 10
                or len(section.tables) > 10
            ):
                raise ValueError("A section contains too many paragraphs, bullets, code blocks, or tables.")
            total_chars += len(section.heading)
            total_chars += sum(map(len, section.paragraphs))
            total_chars += sum(map(len, section.bullets))
            total_chars += sum(map(len, section.code_blocks))
            for table in section.tables:
                _validate_table(table)
                total_cells += len(table.headers) * (len(table.rows) + 1)
                total_chars += sum(map(len, table.headers))
                total_chars += sum(
                    len(str(value)) for row in table.rows for value in row if value is not None
                )
        worksheet_names = set()
        for sheet in self.worksheets:
            if not isinstance(sheet, WorksheetSpec):
                raise ValueError("Each worksheet must be a valid worksheet specification.")
            if (
                not isinstance(sheet.name, str)
                or not sheet.name.strip()
                or len(sheet.name) > 31
                or any(char in sheet.name for char in "[]:*?/\\")
                or sheet.name.startswith("'")
                or sheet.name.endswith("'")
                or any(ord(char) < 32 for char in sheet.name)
            ):
                raise ValueError("An Excel worksheet name is invalid.")
            if sheet.name.casefold() in worksheet_names:
                raise ValueError("Worksheet names must be unique, ignoring case.")
            worksheet_names.add(sheet.name.casefold())
            _validate_table(DataTable(sheet.headers, sheet.rows), max_rows=10_000)
            total_cells += len(sheet.headers) * (len(sheet.rows) + 1)
            total_chars += len(sheet.name) + sum(map(len, sheet.headers))
            total_chars += sum(
                len(str(value)) for row in sheet.rows for value in row if value is not None
            )
        if total_chars > 100_000:
            raise ValueError("Document content exceeds the 100,000 character limit.")
        if total_cells > 50_000:
            raise ValueError("The document contains too many table cells.")
        if self.format is DocumentFormat.EXCEL:
            worksheet_count = len(self.worksheets) or sum(
                len(section.tables) for section in self.sections
            )
            if self.sources:
                worksheet_count += 1
            if worksheet_count > 20:
                raise ValueError("The workbook may contain no more than 20 worksheets, including sources.")
        if len(self.sources) > 30:
            raise ValueError("A document can contain no more than 30 source references.")
        for source in self.sources:
            if not isinstance(source, SourceReference):
                raise ValueError("Each source must be a valid source reference.")
            if (
                not isinstance(source.title, str)
                or not source.title.strip()
                or len(source.title) > 300
                or not isinstance(source.url, str)
                or len(source.url) > 2_000
            ):
                raise ValueError("A source title or URL is invalid.")
            parts = urlsplit(source.url)
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username is not None
                or parts.password is not None
            ):
                raise ValueError("Source URLs must be valid HTTP or HTTPS links.")

        has_section_content = any(
            section.paragraphs or section.bullets or section.code_blocks or section.tables
            for section in self.sections
        )
        if self.format is DocumentFormat.EXCEL:
            if not self.worksheets and not any(section.tables for section in self.sections):
                raise ValueError("An Excel document needs at least one table or worksheet.")
        elif not has_section_content:
            raise ValueError("The document needs at least one non-empty content section.")

        if self.format is DocumentFormat.POWERPOINT:
            if self.slide_count is None or not 2 <= self.slide_count <= 30:
                raise ValueError("PowerPoint slide count must be between 2 and 30.")
            if len(self.sections) != self.slide_count - 1:
                raise ValueError("The PowerPoint slide count does not match its sections.")


def _parse_section(value: Any) -> DocumentSection:
    if not isinstance(value, dict):
        raise ValueError("Each document section must be an object.")
    heading = _required_text(value.get("heading"), "section heading", maximum=160)
    paragraphs = _text_list(value.get("paragraphs", []), "paragraphs", maximum_items=30)
    bullets = _text_list(value.get("bullets", []), "bullets", maximum_items=30)
    code_blocks = _text_list(value.get("code_blocks", []), "code blocks", maximum_items=10)
    raw_tables = value.get("tables", [])
    if not isinstance(raw_tables, list) or len(raw_tables) > 10:
        raise ValueError("A section may contain no more than 10 tables.")
    tables = [_parse_table(item) for item in raw_tables]
    return DocumentSection(heading, paragraphs, bullets, tables, code_blocks)


def _parse_table(value: Any) -> DataTable:
    if not isinstance(value, dict):
        raise ValueError("Each table must be an object.")
    headers = _text_list(value.get("headers"), "table headers", maximum_items=30)
    if not headers:
        raise ValueError("Tables need at least one column header.")
    raw_rows = value.get("rows", [])
    if not isinstance(raw_rows, list) or len(raw_rows) > 500:
        raise ValueError("A table may contain no more than 500 rows.")
    rows = [_parse_row(row, len(headers)) for row in raw_rows]
    return DataTable(headers, rows)


def _parse_worksheet(value: Any) -> WorksheetSpec:
    if not isinstance(value, dict):
        raise ValueError("Each worksheet must be an object.")
    name = _required_text(value.get("name"), "worksheet name", maximum=31)
    if any(char in name for char in "[]:*?/\\"):
        raise ValueError(f"Invalid Excel worksheet name: {name!r}.")
    headers = _text_list(value.get("headers"), "worksheet headers", maximum_items=100)
    if not headers:
        raise ValueError("Worksheets need at least one column header.")
    raw_rows = value.get("rows", [])
    if not isinstance(raw_rows, list) or len(raw_rows) > 10_000:
        raise ValueError("A worksheet may contain no more than 10,000 rows.")
    rows = [_parse_row(row, len(headers)) for row in raw_rows]
    return WorksheetSpec(name, headers, rows)


def _parse_formatting(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > 10:
        raise ValueError("Formatting preferences must be an object with at most 10 entries.")
    formatting = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str) or len(item) > 100:
            raise ValueError("Formatting preferences must contain short text values.")
        if key in {"theme", "font_family", "page_size"}:
            formatting[key] = item.strip()
        elif key == "accent_color" and re.fullmatch(r"#[0-9A-Fa-f]{6}", item):
            formatting[key] = item.upper()
        else:
            raise ValueError(f"Unsupported or invalid formatting preference: {key}.")
    if "page_size" in formatting and formatting["page_size"].lower() not in {"letter", "a4"}:
        raise ValueError("PDF page size must be Letter or A4.")
    if "font_family" in formatting and formatting["font_family"] not in {
        "Arial", "Aptos", "Calibri", "Times New Roman", "Verdana"
    }:
        raise ValueError("The requested font family is not supported.")
    return formatting


def _validate_table(table: DataTable, *, max_rows: int = 500) -> None:
    if not isinstance(table, DataTable):
        raise ValueError("Each table must be a valid table specification.")
    if (
        not isinstance(table.headers, list)
        or not table.headers
        or len(table.headers) > 100
        or any(not isinstance(header, str) or not header.strip() or len(header) > 2_000 for header in table.headers)
    ):
        raise ValueError("Table headers must be non-empty text.")
    if not isinstance(table.rows, list) or len(table.rows) > max_rows:
        raise ValueError(f"A table may contain no more than {max_rows} rows.")
    for row in table.rows:
        if not isinstance(row, list) or len(row) != len(table.headers):
            raise ValueError("Every table row must have exactly the same number of columns as its header.")
        for value in row:
            if value is not None and (
                isinstance(value, (dict, list))
                or not isinstance(value, (str, int, float, bool))
                or (isinstance(value, str) and len(value) > 2_000)
                or (isinstance(value, float) and not math.isfinite(value))
            ):
                raise ValueError("Table cells must be text, numbers, booleans, or null.")


def _parse_row(value: Any, expected_columns: int) -> list[CellValue]:
    if not isinstance(value, list) or len(value) != expected_columns:
        raise ValueError("Every table row must have exactly the same number of columns as its header.")
    cells: list[CellValue] = []
    for cell in value:
        if cell is None or isinstance(cell, (str, bool, int)):
            cells.append(cell)
        elif isinstance(cell, float) and cell == cell and abs(cell) != float("inf"):
            cells.append(cell)
        else:
            raise ValueError("Table cells must be plain text, numbers, booleans, or null.")
    return cells


def _text_list(
    value: Any, field_name: str, *, maximum_items: int
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ValueError(f"{field_name.capitalize()} must be a list of at most {maximum_items} items.")
    return [_required_text(item, field_name, maximum=2_000) for item in value]


def _required_text(value: Any, field_name: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field_name.capitalize()} must be non-empty text of at most {maximum} characters.")
    return value.strip()


def _optional_text(value: Any, field_name: str, *, maximum: int) -> str | None:
    if value is None or value == "":
        return None
    return _required_text(value, field_name, maximum=maximum)


def _bounded_int(value: Any, field_name: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{field_name.capitalize()} must be between {minimum} and {maximum}.")
    return value


def source_references_from_results(results: list[dict[str, Any]]) -> list[SourceReference]:
    sources = []
    for result in results[:30]:
        title = result.get("title")
        url = result.get("url")
        if not isinstance(title, str) or not isinstance(url, str):
            continue
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            continue
        published_date = result.get("published_date")
        sources.append(
            SourceReference(
                title=title[:300],
                url=url[:2_000],
                published_date=published_date[:100]
                if isinstance(published_date, str)
                else None,
            )
        )
    return sources
