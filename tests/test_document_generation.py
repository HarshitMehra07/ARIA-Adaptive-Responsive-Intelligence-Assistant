import json
from pathlib import Path

import pytest

from core.aria_core import AriaCore
from core.cloud_model_client import CloudModelError, CloudModelResponse
from core.conversation_manager import ConversationManager
from document_generation.document_intent import (
    detect_document_command,
    requested_slide_count,
)
from document_generation.document_reader import DocumentReader
from document_generation.document_service import DocumentGenerationError, DocumentService
from document_generation.document_spec import (
    DocumentFormat,
    DocumentSpec,
    source_references_from_results,
)
from document_generation.file_manager import (
    FileManagementError,
    GeneratedFileManager,
)
from research.research_manager import ResearchManager


class RecordingCloudClient:
    def __init__(self, payload, model="test-model"):
        self.payload = payload
        self.model = model
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if isinstance(self.payload, Exception):
            raise self.payload
        return CloudModelResponse(
            text=json.dumps(self.payload, ensure_ascii=False),
            model=self.model,
            raw={},
        )


class StubResearchManager:
    def __init__(self, results=None, available=True):
        self.results = results or []
        self.available = available
        self.queries = []

    def has_live_search(self):
        return self.available

    def search_web(self, query):
        self.queries.append(query)
        return self.results


def _payload(document_format, *, title="Neural Networks"):
    if document_format is DocumentFormat.EXCEL:
        return {
            "title": title,
            "output_filename": "study plan.xlsx",
            "worksheets": [
                {
                    "name": "Study Planner",
                    "headers": ["Date", "=Topic", "Hours"],
                    "rows": [
                        ["2026-10-28", "Neural networks", 2.5],
                        ["2026-10-29", "=1+1", 1.5],
                    ],
                }
            ],
        }
    count = 4 if document_format is DocumentFormat.POWERPOINT else 1
    return {
        "title": title,
        "subtitle": "A concise guide",
        "audience": "Students",
        "slide_count": count + 1,
        "sections": [
            {
                "heading": "Core concepts",
                "paragraphs": ["Neural networks learn patterns from examples."],
                "bullets": ["Layers transform input data.", "Training adjusts model parameters."],
                "code_blocks": (
                    ["print('hello')"]
                    if document_format is DocumentFormat.MARKDOWN
                    else []
                ),
                "tables": [
                    {
                        "headers": ["Term", "Meaning"],
                        "rows": [["Neuron", "A computational unit"]],
                    }
                ],
            }
            for _ in range(count)
        ],
    }


def _service(tmp_path, document_format, *, research=None, payload=None):
    cloud = RecordingCloudClient(payload or _payload(document_format))
    manager = GeneratedFileManager(tmp_path / "output")
    return DocumentService(cloud, research or StubResearchManager(), manager), cloud, manager


@pytest.mark.parametrize(
    "document_format",
    [
        DocumentFormat.POWERPOINT,
        DocumentFormat.WORD,
        DocumentFormat.PDF,
        DocumentFormat.EXCEL,
        DocumentFormat.TEXT,
        DocumentFormat.MARKDOWN,
    ],
)
def test_generates_and_validates_real_documents(tmp_path, document_format):
    service, _cloud, _manager = _service(tmp_path, document_format)
    request = (
        "Create a five-slide PowerPoint about neural networks"
        if document_format is DocumentFormat.POWERPOINT
        else f"Create a {document_format.value} document about neural networks"
    )
    if document_format is DocumentFormat.EXCEL:
        request = "Create an Excel study planner with total hours"

    result = service.create_from_request(request, document_format)

    assert result.path.is_file()
    assert result.path.parent == (tmp_path / "output").resolve()
    assert result.path.suffix == f".{document_format.value}"
    assert result.size_bytes == result.path.stat().st_size > 0
    if document_format is DocumentFormat.POWERPOINT:
        from pptx import Presentation

        presentation = Presentation(result.path)
        assert len(presentation.slides) == 5
        assert "Neural Networks" in presentation.slides[0].shapes.title.text
        assert "Core concepts" in "\n".join(
            shape.text for shape in presentation.slides[1].shapes if hasattr(shape, "text")
        )
    elif document_format is DocumentFormat.WORD:
        from docx import Document

        document = Document(result.path)
        assert any(paragraph.text == "Core concepts" for paragraph in document.paragraphs)
        assert document.tables[0].cell(1, 0).text == "Neuron"
    elif document_format is DocumentFormat.PDF:
        from pypdf import PdfReader

        pdf = PdfReader(str(result.path), strict=True)
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert "Neural Networks" in text
        assert "Core concepts" in text
    elif document_format is DocumentFormat.EXCEL:
        from datetime import datetime
        from openpyxl import load_workbook

        assert result.path.name == "study_plan.xlsx"
        workbook = load_workbook(result.path, data_only=False)
        sheet = workbook["Study Planner"]
        assert sheet["A3"].value == datetime(2026, 10, 28)
        assert sheet["B2"].value == "=Topic"
        assert sheet["B2"].data_type == "s"
        assert sheet["C5"].value == "=SUM(C3:C4)"
        assert sheet["B4"].value == "=1+1"
        assert sheet["B4"].data_type == "s"
        workbook.close()
    elif document_format is DocumentFormat.TEXT:
        assert "Core concepts" in result.path.read_text(encoding="utf-8")
    else:
        markdown = result.path.read_text(encoding="utf-8")
        assert markdown.startswith("# Neural Networks")
        assert "```" in markdown and "print('hello')" in markdown


def test_document_filename_collision_is_safe_and_unique(tmp_path):
    service, _cloud, _manager = _service(tmp_path, DocumentFormat.TEXT)
    first = service.create_from_request("Create a text file", DocumentFormat.TEXT)
    second = service.create_from_request("Create a text file", DocumentFormat.TEXT)

    assert first.path.name == "Neural_Networks.txt"
    assert second.path.name == "Neural_Networks_2.txt"
    assert first.path.read_bytes() != b""
    assert second.path.read_bytes() != b""


def test_file_manager_rejects_traversal_and_lists_only_supported_files(tmp_path):
    manager = GeneratedFileManager(tmp_path / "output")
    with pytest.raises(FileManagementError):
        manager.suggested_filename("..\\..\\aria.db", DocumentFormat.TEXT)

    temporary = manager.make_temporary_path()
    temporary.write_text("safe", encoding="utf-8")
    with pytest.raises(FileManagementError):
        manager.commit_temporary_file(temporary, "..\\aria.db")
    assert manager.list_files() == []


def test_reader_extracts_local_documents_without_cloud_upload(tmp_path):
    service, cloud, manager = _service(tmp_path, DocumentFormat.MARKDOWN)
    result = service.create_from_request("Create a Markdown guide", DocumentFormat.MARKDOWN)

    extracted = DocumentReader(manager).read(result.path)
    summary, partial = service.summarize_document(result.path)

    assert "Core concepts" in extracted.text
    assert "Neural networks learn patterns" in summary
    assert not partial
    assert len(cloud.calls) == 1
    assert len(service.list_generated_files()) == 1


def test_reading_missing_or_external_paths_reports_safe_error(tmp_path):
    manager = GeneratedFileManager(tmp_path / "output")
    reader = DocumentReader(manager)
    with pytest.raises(FileManagementError):
        reader.read(tmp_path / "missing.pdf")
    with pytest.raises(FileManagementError):
        reader.read(Path("C:\\Windows\\win.ini"))


def test_invalid_document_specification_is_rejected():
    with pytest.raises(ValueError, match="same number of columns"):
        DocumentSpec.from_payload(
            DocumentFormat.WORD,
            {
                "title": "Invalid",
                "sections": [
                    {
                        "heading": "Table",
                        "tables": [{"headers": ["A", "B"], "rows": [["only one"]]}],
                    }
                ],
            },
        )


def test_intent_detection_is_specific_and_reports_unsupported_formats():
    command = detect_document_command("Create a 5-slide PowerPoint about neural networks")
    assert command.action == "generate"
    assert command.document_format is DocumentFormat.POWERPOINT
    assert detect_document_command("Create a CSV file with my notes").action == "unsupported"
    assert detect_document_command("Create a .doc file with my notes").action == "unsupported"
    assert detect_document_command("What is a PDF?") is None
    assert detect_document_command("List my generated files").action == "list"
    assert detect_document_command("Summarize the selected document").action == "summarize"
    assert detect_document_command("Create a weekly study planner").document_format is DocumentFormat.EXCEL
    assert detect_document_command("Build a project task tracker").document_format is DocumentFormat.EXCEL
    assert requested_slide_count("Create a five-slide presentation") == 5
    with pytest.raises(ValueError, match="between 2 and 30"):
        requested_slide_count("Create a 31-slide presentation")


def test_aria_routes_generation_and_returns_the_real_path(tmp_path):
    ConversationManager.clear()
    cloud = RecordingCloudClient(_payload(DocumentFormat.POWERPOINT))
    manager = GeneratedFileManager(tmp_path / "output")
    service = DocumentService(cloud, StubResearchManager(), manager)
    aria = AriaCore(cloud_client=cloud, document_service=service)

    response = aria.process_input("Create a five-slide PowerPoint about neural networks")

    assert aria.state.intent == "document_generate"
    assert "Created and validated PPTX" in response
    assert str(tmp_path / "output" / "Neural_Networks.pptx") in response
    assert aria.state.metadata["document_result"].path.is_file()


def test_cloud_and_research_failures_do_not_claim_success(tmp_path):
    ConversationManager.clear()
    cloud = RecordingCloudClient(CloudModelError("private provider details"))
    service = DocumentService(
        cloud,
        StubResearchManager(),
        GeneratedFileManager(tmp_path / "output"),
    )
    aria = AriaCore(cloud_client=cloud, document_service=service)
    response = aria.process_input("Create a Word report about neural networks")
    assert "couldn't create the document" in response.lower()
    assert "private provider details" not in response
    assert not (tmp_path / "output").exists()

    research = StubResearchManager(available=False)
    cloud = RecordingCloudClient(_payload(DocumentFormat.PDF))
    service = DocumentService(
        cloud,
        research,
        GeneratedFileManager(tmp_path / "research-output"),
    )
    aria = AriaCore(cloud_client=cloud, document_service=service)
    response = aria.process_input("Research recent AI developments and create a PDF report")
    assert "isn't configured" in response
    assert cloud.calls == []
    assert not (tmp_path / "research-output").exists()


def test_research_results_are_preserved_in_sources_and_prompt(tmp_path):
    source = {
        "title": "Official research release",
        "url": "https://example.org/release",
        "snippet": "An unverified provider snippet about a release.",
        "published_date": "2026-10-28",
    }
    research = StubResearchManager([source])
    service, cloud, _manager = _service(
        tmp_path,
        DocumentFormat.MARKDOWN,
        research=research,
    )
    result = service.create_from_request(
        "Research recent AI releases and create a Markdown report",
        DocumentFormat.MARKDOWN,
    )

    content = result.path.read_text(encoding="utf-8")
    model_input = cloud.calls[0]["messages"][1]["content"]
    assert research.queries == ["Research recent AI releases"]
    assert "https://example.org/release" in content
    assert "2026-10-28" in content
    assert "not independently verified" in content
    assert "unverified provider snippet" in model_input
    assert source["url"] in model_input
    assert source_references_from_results([source])[0].published_date == "2026-10-28"


def test_research_sources_are_exported_as_clickable_excel_links(tmp_path):
    source = {
        "title": "Official framework documentation",
        "url": "https://example.org/framework",
        "snippet": "The provider result describes the framework.",
        "published_date": "2026-10-28",
    }
    research = StubResearchManager([source])
    service, _cloud, _manager = _service(
        tmp_path,
        DocumentFormat.EXCEL,
        research=research,
    )
    result = service.create_from_request(
        "Research recent AI developments and create an Excel comparison",
        DocumentFormat.EXCEL,
    )

    from openpyxl import load_workbook

    workbook = load_workbook(result.path, data_only=False)
    sheet = workbook["Source references"]
    assert sheet["A3"].value == source["title"]
    assert sheet["B3"].value == source["url"]
    assert sheet["B3"].hyperlink.target == source["url"]
    assert "not independently verified" in sheet["D3"].value
    workbook.close()


@pytest.mark.parametrize("document_format", [DocumentFormat.WORD, DocumentFormat.PDF])
def test_research_source_links_are_clickable_in_word_and_pdf(tmp_path, document_format):
    source = {
        "title": "Official source",
        "url": "https://example.org/official",
        "snippet": "An unverified search result.",
        "published_date": None,
    }
    service, _cloud, _manager = _service(
        tmp_path,
        document_format,
        research=StubResearchManager([source]),
    )
    request = (
        "Research recent AI developments and create a Word report"
        if document_format is DocumentFormat.WORD
        else "Research recent AI developments and create a PDF report"
    )
    result = service.create_from_request(request, document_format)

    if document_format is DocumentFormat.WORD:
        from docx import Document

        document = Document(result.path)
        assert any(
            relationship.is_external and relationship.target_ref == source["url"]
            for relationship in document.part.rels.values()
        )
    else:
        from pypdf import PdfReader

        pdf = PdfReader(str(result.path), strict=True)
        links = [
            annotation.get_object().get("/A", {}).get("/URI")
            for page in pdf.pages
            for annotation in page.get("/Annots", [])
        ]
        assert source["url"] in links


def test_missing_cloud_client_fails_without_writing(tmp_path):
    service = DocumentService(
        cloud_client=None,
        research_manager=StubResearchManager(),
        file_manager=GeneratedFileManager(tmp_path / "output"),
    )
    with pytest.raises(DocumentGenerationError, match="cloud model"):
        service.create_from_request("Create a PDF report", DocumentFormat.PDF)
    assert not (tmp_path / "output").exists()


def test_ordinary_chat_and_unsupported_request_keep_routing_honest(tmp_path):
    ConversationManager.clear()
    cloud = RecordingCloudClient(_payload(DocumentFormat.TEXT))
    service = DocumentService(
        cloud,
        StubResearchManager(),
        GeneratedFileManager(tmp_path / "output"),
    )
    aria = AriaCore(cloud_client=cloud, document_service=service)
    assert aria.process_input("What is a PDF?") != "That output format isn't supported."
    assert aria.state.intent == "question"

    response = aria.process_input("Create a CSV file of my notes")
    assert "isn't supported" in response
    assert aria.state.intent == "document_unsupported"
    assert len(cloud.calls) == 1


def test_selected_document_summary_is_local_and_list_intent_is_routed(tmp_path):
    ConversationManager.clear()
    cloud = RecordingCloudClient(_payload(DocumentFormat.TEXT))
    manager = GeneratedFileManager(tmp_path / "output")
    service = DocumentService(cloud, StubResearchManager(), manager)
    result = service.create_from_request("Create a text file", DocumentFormat.TEXT)
    aria = AriaCore(cloud_client=cloud, document_service=service)

    summary_response = aria.process_input(
        "Summarize the selected document",
        sensory_data={"selected_document_path": str(result.path)},
    )
    assert "Local extractive summary" in summary_response
    assert "Neural networks learn patterns" in summary_response
    assert len(cloud.calls) == 1

    list_response = aria.process_input("List my generated files")
    assert aria.state.intent == "document_list"
    assert str(result.path) in list_response
