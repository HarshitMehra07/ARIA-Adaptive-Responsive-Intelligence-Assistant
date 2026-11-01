from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from document_generation.document_spec import DocumentFormat
from document_generation.file_manager import FileManagementError, GeneratedFileManager


SUPPORTED_EXTENSIONS = {
    f".{document_format.value}" for document_format in DocumentFormat
}
MAX_EXTRACTED_CHARACTERS = 100_000


@dataclass(frozen=True)
class ExtractedDocument:
    path: Path
    text: str
    partial: bool = False


class DocumentReader:
    def __init__(self, file_manager: GeneratedFileManager):
        self.file_manager = file_manager

    def read(self, value: str | Path) -> ExtractedDocument:
        path = self.file_manager.validate_read_path(value)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise FileManagementError("That document format is not supported for reading.")
        try:
            if path.suffix.lower() in {".docx", ".xlsx", ".pptx"}:
                _validate_office_archive(path)
            if path.suffix.lower() in (".txt", ".md"):
                return self._read_text(path)
            if path.suffix.lower() == ".pdf":
                return self._read_pdf(path)
            if path.suffix.lower() == ".docx":
                return self._read_word(path)
            if path.suffix.lower() == ".xlsx":
                return self._read_excel(path)
            return self._read_powerpoint(path)
        except FileManagementError:
            raise
        except Exception as error:
            raise FileManagementError(
                f"The {path.suffix.lower()} document is corrupted, encrypted, or unreadable."
            ) from error

    @staticmethod
    def _bounded(path: Path, text: str) -> ExtractedDocument:
        cleaned = text.strip()
        if not cleaned:
            raise FileManagementError("No readable text was found in that document.")
        partial = len(cleaned) > MAX_EXTRACTED_CHARACTERS
        return ExtractedDocument(
            path=path,
            text=cleaned[:MAX_EXTRACTED_CHARACTERS],
            partial=partial,
        )

    def _read_text(self, path: Path) -> ExtractedDocument:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_bytes().decode("utf-8", errors="replace")
        return self._bounded(path, text)

    def _read_pdf(self, path: Path) -> ExtractedDocument:
        from pypdf import PdfReader

        reader = PdfReader(str(path), strict=True)
        if reader.is_encrypted:
            raise FileManagementError("Encrypted PDF documents cannot be read.")
        texts = []
        partial = False
        for page in reader.pages[:1000]:
            texts.append(page.extract_text() or "")
        if len(reader.pages) > 1000:
            partial = True
        document = self._bounded(path, "\n".join(texts))
        return ExtractedDocument(document.path, document.text, document.partial or partial)

    def _read_word(self, path: Path) -> ExtractedDocument:
        from docx import Document

        document = Document(path)
        chunks = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
        for table in document.tables:
            chunks.extend(
                " | ".join(cell.text for cell in row.cells)
                for row in table.rows
            )
        return self._bounded(path, "\n".join(chunks))

    def _read_excel(self, path: Path) -> ExtractedDocument:
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            chunks = []
            partial = len(workbook.worksheets) > 20
            for sheet in workbook.worksheets[:20]:
                chunks.append(f"Worksheet: {sheet.title}")
                for row in sheet.iter_rows(max_row=10001, max_col=100, values_only=True):
                    values = ["" if value is None else str(value) for value in row]
                    if any(values):
                        chunks.append(" | ".join(values))
                if (
                    (sheet.max_row and sheet.max_row > 10_000)
                    or (sheet.max_column and sheet.max_column > 100)
                ):
                    partial = True
            document = self._bounded(path, "\n".join(chunks))
            return ExtractedDocument(
                document.path,
                document.text,
                document.partial or partial,
            )
        finally:
            workbook.close()

    def _read_powerpoint(self, path: Path) -> ExtractedDocument:
        from pptx import Presentation

        presentation = Presentation(path)
        chunks = []
        for index, slide in enumerate(presentation.slides[:100], start=1):
            chunks.append(f"Slide {index}")
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    chunks.append(shape.text.strip())
                if getattr(shape, "has_table", False):
                    chunks.extend(
                        " | ".join(cell.text for cell in row.cells)
                        for row in shape.table.rows
                    )
        document = self._bounded(path, "\n".join(chunks))
        return ExtractedDocument(
            document.path,
            document.text,
            document.partial or len(presentation.slides) > 100,
        )


def extractive_summary(text: str, *, max_sentences: int = 6) -> str:
    """Return a local-only extractive summary; document contents are not uploaded."""
    sentences = [
        match.group().strip()
        for match in re.finditer(r"[^.!?\n]+[.!?]?", text)
        if len(match.group().strip()) > 25
    ]
    if not sentences:
        return text[:1_200]

    stop_words = {
        "about", "after", "again", "also", "and", "are", "because", "been",
        "before", "being", "between", "but", "can", "could", "does", "during",
        "each", "from", "have", "into", "its", "more", "most", "much", "not",
        "only", "other", "our", "over", "same", "such", "than", "that", "the",
        "their", "there", "these", "they", "this", "through", "under", "very",
        "was", "were", "what", "when", "where", "which", "while", "with", "would",
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    frequencies: dict[str, int] = {}
    for word in words:
        if word not in stop_words:
            frequencies[word] = frequencies.get(word, 0) + 1
    scored = []
    for index, sentence in enumerate(sentences):
        tokens = [word for word in re.findall(r"\b[a-zA-Z]{3,}\b", sentence.lower()) if word in frequencies]
        score = sum(frequencies[word] for word in tokens) / max(len(tokens), 1)
        scored.append((score, -index, sentence))
    selected = sorted(scored, reverse=True)[:max_sentences]
    return "\n".join(sentence for _, _, sentence in sorted(selected, key=lambda item: -item[1]))


def _validate_office_archive(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
    except (OSError, zipfile.BadZipFile) as error:
        raise FileManagementError("The Office document is not a valid package.") from error
    if len(entries) > 5_000 or sum(entry.file_size for entry in entries) > 50 * 1024 * 1024:
        raise FileManagementError("The Office document expands beyond the 50 MB reading limit.")
