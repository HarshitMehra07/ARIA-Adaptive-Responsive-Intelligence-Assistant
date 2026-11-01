from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from config.settings import PROJECT_ROOT
from document_generation.document_spec import DocumentFormat


class FileManagementError(Exception):
    """A safe, user-presentable generated-file error."""


class GeneratedFileManager:
    MAX_FILE_SIZE = 50 * 1024 * 1024

    def __init__(self, output_dir: Path | str | None = None):
        self.output_dir = Path(output_dir or PROJECT_ROOT / "output").expanduser()

    def ensure_output_dir(self) -> Path:
        if self.output_dir.exists() and self.output_dir.is_symlink():
            raise FileManagementError("The generated-file output directory cannot be a symbolic link.")
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            resolved = self.output_dir.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise FileManagementError("The generated-file output directory is unavailable.") from error
        if not resolved.is_dir():
            raise FileManagementError("The generated-file output path is not a directory.")
        return resolved

    def make_temporary_path(self, extension: str | None = None) -> Path:
        root = self.ensure_output_dir()
        suffix = f".{extension}" if extension else ""
        return root / f".aria-{uuid.uuid4().hex}.tmp{suffix}"

    def suggested_filename(self, value: str, document_format: DocumentFormat) -> str:
        raw = value.strip()
        if any(separator in raw for separator in ("/", "\\", "\0")):
            raise FileManagementError("Output filenames cannot contain path separators.")
        suffix = Path(raw).suffix.lower().lstrip(".")
        known_formats = {item.value for item in DocumentFormat}
        if suffix in known_formats and suffix != document_format.value:
            raise FileManagementError("The output filename extension does not match the document format.")
        if raw.lower().endswith(f".{document_format.value}"):
            raw = raw[: -(len(document_format.value) + 1)]
        raw = re.sub(r"[^\w .()-]+", "_", raw, flags=re.UNICODE)
        raw = re.sub(r"\s+", "_", raw).strip(" ._")
        raw = raw[:100].rstrip(" .")
        if not raw or raw in {".", ".."}:
            raise FileManagementError("A safe, non-empty output filename is required.")
        if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", raw, re.IGNORECASE):
            raw = f"_{raw}"
        return f"{raw}.{document_format.value}"

    def commit_temporary_file(self, temporary_path: Path, filename: str) -> Path:
        root = self.ensure_output_dir()
        if (
            not filename
            or any(separator in filename for separator in ("/", "\\", "\0"))
            or Path(filename).name != filename
            or Path(filename).suffix.lower().lstrip(".")
            not in {item.value for item in DocumentFormat}
        ):
            raise FileManagementError("The generated document filename is invalid.")
        try:
            temporary_parent = temporary_path.resolve(strict=True).parent
        except (OSError, RuntimeError) as error:
            raise FileManagementError("The temporary document path is unavailable.") from error
        if temporary_path.is_symlink() or temporary_parent != root:
            raise FileManagementError("The temporary document path is outside the output directory.")
        try:
            size = temporary_path.stat().st_size
        except OSError as error:
            raise FileManagementError("The generated document could not be read.") from error
        if size <= 0 or size > self.MAX_FILE_SIZE:
            raise FileManagementError("The generated document is empty or exceeds the 50 MB limit.")

        stem = Path(filename).stem
        suffix = Path(filename).suffix
        for index in range(10_000):
            candidate_name = filename if index == 0 else f"{stem}_{index + 1}{suffix}"
            candidate = root / candidate_name
            try:
                os.rename(temporary_path, candidate)
                return candidate.resolve(strict=True)
            except FileExistsError:
                continue
            except OSError as error:
                raise FileManagementError("The generated document could not be saved.") from error
        raise FileManagementError("A unique output filename could not be allocated.")

    def list_files(self) -> list[dict[str, str | int]]:
        root = self.ensure_output_dir()
        files = []
        for path in root.iterdir():
            if (
                path.is_file()
                and not path.is_symlink()
                and path.suffix.lower().lstrip(".")
                in {item.value for item in DocumentFormat}
            ):
                stat = path.stat()
                files.append(
                    {"name": path.name, "path": str(path.resolve()), "size_bytes": stat.st_size}
                )
        return sorted(files, key=lambda item: str(item["name"]).casefold())

    def validate_read_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        try:
            resolved = path.resolve(strict=True)
            roots = (PROJECT_ROOT.resolve(), self.ensure_output_dir())
        except (OSError, RuntimeError) as error:
            raise FileManagementError("The requested document path does not exist or is unavailable.") from error
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise FileManagementError("Documents may only be read from the ARIA workspace or output directory.")
        try:
            if not resolved.is_file():
                raise FileManagementError("The requested document path is not a regular file.")
            size = resolved.stat().st_size
        except OSError as error:
            raise FileManagementError("The requested document path is unavailable.") from error
        if size > 10 * 1024 * 1024:
            raise FileManagementError("Documents larger than 10 MB cannot be read.")
        return resolved
