from __future__ import annotations

import re
import html
from datetime import date
from pathlib import Path

from document_generation.document_spec import (
    DataTable,
    DocumentFormat,
    DocumentSpec,
    WorksheetSpec,
)


def generate_document(spec: DocumentSpec, path: Path) -> None:
    spec.validate()
    generators = {
        DocumentFormat.POWERPOINT: _generate_powerpoint,
        DocumentFormat.WORD: _generate_word,
        DocumentFormat.PDF: _generate_pdf,
        DocumentFormat.EXCEL: _generate_excel,
        DocumentFormat.TEXT: _generate_text,
        DocumentFormat.MARKDOWN: _generate_markdown,
    }
    generators[spec.format](spec, path)


def validate_generated_document(spec: DocumentSpec, path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("The generated document is missing or empty.")
    if spec.format is DocumentFormat.POWERPOINT:
        from pptx import Presentation

        document = Presentation(path)
        if len(document.slides) != spec.slide_count:
            raise ValueError("The generated PowerPoint does not contain the requested slide count.")
        slide_texts = [_slide_text(slide) for slide in document.slides]
        if any(not text.strip() for text in slide_texts):
            raise ValueError("The generated PowerPoint contains an empty slide.")
        if spec.title not in slide_texts[0] or any(
            section.heading not in text
            for section, text in zip(spec.sections, slide_texts[1:])
        ):
            raise ValueError("The generated PowerPoint is missing a slide title.")
    elif spec.format is DocumentFormat.WORD:
        from docx import Document

        document = Document(path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        if spec.title not in text:
            raise ValueError("The generated Word document is missing its title.")
        if any(
            section.heading not in {paragraph.text for paragraph in document.paragraphs}
            for section in spec.sections
        ):
            raise ValueError("The generated Word document is missing a section heading.")
    elif spec.format is DocumentFormat.PDF:
        from pypdf import PdfReader

        document = PdfReader(str(path), strict=True)
        text = "\n".join(page.extract_text() or "" for page in document.pages)
        if not document.pages or not _pdf_text(spec.title)[:40] in _pdf_text(text):
            raise ValueError("The generated PDF is invalid or missing its title.")
        if any(_pdf_text(section.heading) not in _pdf_text(text) for section in spec.sections):
            raise ValueError("The generated PDF is missing a section heading.")
    elif spec.format is DocumentFormat.EXCEL:
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            if not workbook.sheetnames:
                raise ValueError("The generated workbook contains no worksheets.")
            if not any(
                cell.value == spec.title
                for sheet in workbook.worksheets
                for row in sheet.iter_rows()
                for cell in row
            ):
                raise ValueError("The generated workbook is missing its title.")
        finally:
            workbook.close()
    else:
        text = path.read_text(encoding="utf-8")
        if spec.title not in text:
            raise ValueError("The generated text document is missing its title.")


def _generate_powerpoint(spec: DocumentSpec, path: Path) -> None:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_AUTO_SIZE
    from pptx.util import Inches, Pt

    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    accent = RGBColor(*_hex_rgb(spec.formatting.get("accent_color", "#1F4E79")))
    font_family = spec.formatting.get("font_family", "Aptos")

    title_slide = presentation.slides.add_slide(presentation.slide_layouts[0])
    title_slide.shapes.title.text = spec.title
    title_slide.shapes.title.text_frame.paragraphs[0].font.size = Pt(34)
    title_slide.shapes.title.text_frame.paragraphs[0].font.name = font_family
    subtitle = title_slide.placeholders[1]
    subtitle.text = spec.subtitle or (f"For {spec.audience}" if spec.audience else "")
    if spec.subtitle and spec.audience:
        subtitle.text += f"\nFor {spec.audience}"

    for section in spec.sections:
        visible_tables = [table for table in section.tables if table.rows]
        has_table = bool(visible_tables)
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        title_box = slide.shapes.add_textbox(Inches(0.65), Inches(0.35), Inches(12), Inches(0.8))
        title_paragraph = title_box.text_frame.paragraphs[0]
        title_paragraph.text = section.heading
        title_paragraph.font.size = Pt(27)
        title_paragraph.font.bold = True
        title_paragraph.font.color.rgb = accent
        title_paragraph.font.name = font_family

        content_height = 3.45 if has_table else 5.5
        content_box = slide.shapes.add_textbox(
            Inches(0.8),
            Inches(1.35),
            Inches(11.8),
            Inches(content_height),
        )
        frame = content_box.text_frame
        frame.word_wrap = True
        frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        frame.margin_left = Inches(0.1)
        frame.margin_right = Inches(0.1)
        frame.margin_top = Inches(0.05)
        frame.clear()
        entries = [("paragraph", item) for item in section.paragraphs]
        entries.extend(("bullet", item) for item in section.bullets)
        entries.extend(("code", item) for item in section.code_blocks)
        if section is spec.sections[-1]:
            if spec.sources:
                entries.append(
                    (
                        "paragraph",
                        "Research note: source references use provider snippets; AI-generated "
                        "explanations are not independently verified.",
                    )
                )
            entries.extend(
                (
                    "bullet",
                    f"Source: {source.title} — {source.url}"
                    + (
                        f" (provider publication date: {source.published_date})"
                        if source.published_date
                        else ""
                    )
                    + " [search-result snippet; page not independently verified]",
                )
                for source in spec.sources
            )
        if not entries:
            for table in section.tables:
                entries.extend(("bullet", " | ".join(map(str, row))) for row in table.rows[:8])
        if not entries:
            entries.append(("paragraph", "See the source notes for supporting references."))
        entry_limit = 6 if has_table else 14
        for index, (kind, content) in enumerate(entries[:entry_limit]):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            paragraph.text = content
            paragraph.font.size = Pt(
                11 if kind == "code" else (14 if has_table else (17 if kind == "paragraph" else 19))
            )
            paragraph.space_after = Pt(10)
            if kind == "bullet":
                paragraph.level = 0
                paragraph.text = f"• {content}"
            if len(content) > 280:
                paragraph.font.size = Pt(11 if has_table else 14)

        for table_spec in visible_tables[:1]:
            if not table_spec.rows:
                continue
            rows = min(len(table_spec.rows), 3) + 1
            columns = min(len(table_spec.headers), 5)
            table = slide.shapes.add_table(
                rows,
                columns,
                Inches(0.8),
                Inches(4.95),
                Inches(11.8),
                Inches(1.65),
            ).table
            for column, header in enumerate(table_spec.headers[:columns]):
                table.cell(0, column).text = header[:80]
                table.cell(0, column).text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
            for row_index, row in enumerate(table_spec.rows[: rows - 1], start=1):
                for column, value in enumerate(row[:columns]):
                    table.cell(row_index, column).text = str(value or "")[:100]
                    table.cell(row_index, column).text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
            omitted_rows = len(table_spec.rows) - (rows - 1)
            omitted_columns = len(table_spec.headers) - columns
            notes = []
            if omitted_rows:
                notes.append(f"{omitted_rows} additional table rows omitted")
            if omitted_columns:
                notes.append(f"{omitted_columns} additional columns omitted")
            if len(section.tables) > 1:
                notes.append(f"{len(section.tables) - 1} additional tables omitted")
            if len(entries) > entry_limit:
                notes.append(f"{len(entries) - entry_limit} additional content items omitted")
            if notes:
                note_box = slide.shapes.add_textbox(
                    Inches(0.8),
                    Inches(6.68),
                    Inches(11.8),
                    Inches(0.35),
                )
                note_paragraph = note_box.text_frame.paragraphs[0]
                note_paragraph.text = "; ".join(notes)
                note_paragraph.font.size = Pt(9)

    presentation.save(path)


def _generate_word(spec: DocumentSpec, path: Path) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)
    document.add_heading(spec.title, level=0)
    font_family = spec.formatting.get("font_family", "Aptos")
    accent = _hex_rgb(spec.formatting.get("accent_color", "#1F4E79"))
    document.styles["Normal"].font.name = font_family
    for style_name in ("Title", "Heading 1", "Heading 2"):
        if style_name in document.styles:
            document.styles[style_name].font.name = font_family
            document.styles[style_name].font.color.rgb = RGBColor(*accent)
    if spec.subtitle:
        subtitle = document.add_paragraph(spec.subtitle)
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if spec.audience:
        document.add_paragraph(f"Audience: {spec.audience}")
    if spec.sources:
        document.add_paragraph(
            "Research note: source references use provider snippets; AI-generated "
            "explanations are not independently verified."
        )
    for content_section in spec.sections:
        document.add_heading(content_section.heading, level=1)
        for paragraph in content_section.paragraphs:
            document.add_paragraph(paragraph)
        for bullet in content_section.bullets:
            document.add_paragraph(bullet, style="List Bullet")
        for code in content_section.code_blocks:
            code_paragraph = document.add_paragraph(style="No Spacing")
            code_run = code_paragraph.add_run(code)
            code_run.font.name = "Consolas"
        for table_spec in content_section.tables:
            _add_word_table(document, table_spec)
    _append_sources(document, spec)
    for style_name in ("Normal", "Body Text"):
        if style_name in document.styles:
            document.styles[style_name].font.size = Pt(10.5)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Page ")
    _add_word_field(footer, "PAGE")
    document.save(path)


def _add_word_table(document, table_spec: DataTable) -> None:
    table = document.add_table(rows=1, cols=len(table_spec.headers))
    table.style = "Light Shading Accent 1"
    for cell, value in zip(table.rows[0].cells, table_spec.headers):
        cell.text = value
    for row in table_spec.rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = "" if value is None else str(value)


def _add_word_field(paragraph, field: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = f" {field} "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instruction)
    run._r.append(end)


def _add_word_hyperlink(paragraph, text: str, url: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE

    relationship_id = paragraph.part.relate_to(
        url,
        RELATIONSHIP_TYPE.HYPERLINK,
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    properties.append(color)
    run.append(properties)
    text_node = OxmlElement("w:t")
    text_node.text = text
    run.append(text_node)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _generate_pdf(spec: DocumentSpec, path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer

    styles = getSampleStyleSheet()
    accent_color = colors.HexColor(spec.formatting.get("accent_color", "#1F4E79"))
    styles.add(
        ParagraphStyle(
            name="AriaTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            textColor=accent_color,
        )
    )
    styles.add(ParagraphStyle(name="AriaSubtitle", parent=styles["Normal"], alignment=TA_CENTER))
    story = [
        Paragraph(_pdf_escape(spec.title), styles["AriaTitle"]),
        Spacer(1, 0.2 * inch),
    ]
    if spec.subtitle:
        story.append(Paragraph(_pdf_escape(spec.subtitle), styles["AriaSubtitle"]))
    if spec.audience:
        story.append(Paragraph(f"Audience: {_pdf_escape(spec.audience)}", styles["Normal"]))
    if spec.sources:
        story.append(
            Paragraph(
                "Research note: source references use provider snippets; AI-generated "
                "explanations are not independently verified.",
                styles["Italic"],
            )
        )
    for content_section in spec.sections:
        story.append(Paragraph(_pdf_escape(content_section.heading), styles["Heading1"]))
        for paragraph in content_section.paragraphs:
            story.append(Paragraph(_pdf_escape(paragraph), styles["BodyText"]))
        for bullet in content_section.bullets:
            story.append(Paragraph(f"&bull; {_pdf_escape(bullet)}", styles["BodyText"]))
        for code in content_section.code_blocks:
            from reportlab.platypus import Preformatted

            story.append(Preformatted(_pdf_text(code), styles["Code"]))
        for table_spec in content_section.tables:
            page_width = A4[0] if spec.formatting.get("page_size", "letter").lower() == "a4" else letter[0]
            story.append(_pdf_table(table_spec, styles, colors, page_width - 1.4 * inch))
    if spec.sources:
        story.append(Paragraph("Sources", styles["Heading1"]))
        for source in spec.sources:
            title = _pdf_escape(source.title)
            url = html.escape(source.url, quote=True)
            date = (
                f" (provider publication date: {_pdf_escape(source.published_date)})"
                if source.published_date
                else ""
            )
            story.append(
                Paragraph(
                    f'<link href="{url}" color="blue">{title}</link>{date}<br/>'
                    f'<font size="8">{html.escape(source.url)}; search-result snippet, '
                    "page not independently verified</font>",
                    styles["BodyText"],
                )
            )

    document = BaseDocTemplate(
        str(path),
        pagesize=A4 if spec.formatting.get("page_size", "letter").lower() == "a4" else letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=_pdf_text(spec.title),
    )
    frame = Frame(
        document.leftMargin,
        document.bottomMargin,
        document.width,
        document.height,
        id="normal",
    )
    document.addPageTemplates(
        PageTemplate(id="numbered", frames=[frame], onPage=_draw_page_number)
    )
    document.build(story)


def _pdf_table(table_spec: DataTable, styles, colors, available_width):
    from reportlab.platypus import Paragraph, Table, TableStyle

    rows = [[Paragraph(_pdf_escape(item), styles["BodyText"]) for item in table_spec.headers]]
    rows.extend(
        [Paragraph(_pdf_escape("" if item is None else str(item)), styles["BodyText"]) for item in row]
        for row in table_spec.rows
    )
    column_width = available_width / len(table_spec.headers)
    table = Table(
        rows,
        repeatRows=1,
        hAlign="LEFT",
        colWidths=[column_width for _ in table_spec.headers],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9eaf7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _draw_page_number(canvas, document) -> None:
    from reportlab.lib.units import inch

    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(document.pagesize[0] / 2, 0.35 * inch, f"Page {document.page}")
    canvas.restoreState()


def _generate_excel(spec: DocumentSpec, path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.remove(workbook.active)
    accent_color = spec.formatting.get("accent_color", "#1F4E79").lstrip("#")
    header_color = spec.formatting.get("accent_color", "#4472C4").lstrip("#")
    worksheets = list(spec.worksheets)
    if not worksheets:
        index = 1
        for section in spec.sections:
            for table in section.tables:
                worksheets.append(
                    WorksheetSpec(
                        name=section.heading[:31] or f"Sheet{index}",
                        headers=table.headers,
                        rows=table.rows,
                    )
                )
                index += 1
    if spec.sources:
        source_sheet_name = _unique_sheet_name(
            "Source references",
            {sheet.name.casefold() for sheet in worksheets},
        )
        worksheets.append(
            WorksheetSpec(
                name=source_sheet_name,
                headers=[
                    "Source",
                    "URL",
                    "Provider publication date",
                    "Verification",
                    "Content note",
                ],
                rows=[
                    [
                        source.title,
                        source.url,
                        source.published_date,
                        "Search-result snippet; page not independently verified",
                        "Document explanations are AI-generated and not independently verified.",
                    ]
                    for source in spec.sources
                ],
            )
        )
    for index, worksheet_spec in enumerate(worksheets):
        worksheet = workbook.create_sheet(worksheet_spec.name)
        worksheet.append([spec.title])
        worksheet["A1"].data_type = "s"
        worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(worksheet_spec.headers))
        worksheet["A1"].font = Font(bold=True, size=16, color="FFFFFF")
        worksheet["A1"].fill = PatternFill("solid", fgColor=accent_color)
        worksheet.append(worksheet_spec.headers)
        for cell in worksheet[2]:
            cell.data_type = "s"
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=header_color)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        for row in worksheet_spec.rows:
            normalized = [
                _excel_value(worksheet_spec.headers[column], value)
                for column, value in enumerate(row)
            ]
            worksheet.append(normalized)
            for column, (cell, value) in enumerate(zip(worksheet[worksheet.max_row], normalized)):
                if isinstance(value, str):
                    cell.data_type = "s"
                header = worksheet_spec.headers[column].lower()
                if isinstance(value, date):
                    cell.number_format = "yyyy-mm-dd"
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    if re.search(r"\b(?:hour|hours|duration)\b", header):
                        cell.number_format = "0.0"
                    elif re.search(r"\b(?:cost|budget|price|amount)\b", header):
                        cell.number_format = '"$"#,##0.00'
                    elif "%" in header or "percent" in header:
                        cell.number_format = "0.0%"
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        if worksheet_spec.name.startswith("Source references"):
            for row_index in range(3, worksheet.max_row + 1):
                url_cell = worksheet.cell(row_index, 2)
                if isinstance(url_cell.value, str):
                    url_cell.hyperlink = url_cell.value
                    url_cell.style = "Hyperlink"
        if (
            spec.include_totals
            and worksheet_spec.rows
            and not worksheet_spec.name.startswith("Source references")
        ):
            worksheet.append([""] * len(worksheet_spec.headers))
            total_row = worksheet.max_row
            label_column = next(
                (
                    column
                    for column, header in enumerate(worksheet_spec.headers, start=1)
                    if not any(
                        isinstance(row[column - 1], (int, float))
                        and not isinstance(row[column - 1], bool)
                        for row in worksheet_spec.rows
                    )
                ),
                1,
            )
            worksheet.cell(total_row, label_column, "Total")
            first_data_row = 3
            last_data_row = 2 + len(worksheet_spec.rows)
            for column, header in enumerate(worksheet_spec.headers, start=1):
                values = [row[column - 1] for row in worksheet_spec.rows]
                numeric_column = any(
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    for value in values
                )
                semantic_total = bool(
                    re.search(
                        r"\b(?:hour|hours|duration|amount|cost|budget|price|quantity|total|sum)\b",
                        header,
                        re.IGNORECASE,
                    )
                )
                if numeric_column and semantic_total:
                    target = worksheet.cell(total_row, column)
                    target.value = (
                        f"=SUM({get_column_letter(column)}{first_data_row}:"
                        f"{get_column_letter(column)}{last_data_row})"
                    )
                    target.font = Font(bold=True)
            if not any(
                re.search(
                    r"\b(?:hour|hours|duration|amount|cost|budget|price|quantity|total|sum)\b",
                    header,
                    re.IGNORECASE,
                )
                and any(
                    isinstance(row[column - 1], (int, float))
                    and not isinstance(row[column - 1], bool)
                    for row in worksheet_spec.rows
                )
                for column, header in enumerate(worksheet_spec.headers, start=1)
            ):
                for column, header in enumerate(worksheet_spec.headers, start=1):
                    if any(
                        isinstance(row[column - 1], (int, float))
                        and not isinstance(row[column - 1], bool)
                        for row in worksheet_spec.rows
                    ):
                        worksheet.cell(total_row, column).value = (
                            f"=SUM({get_column_letter(column)}{first_data_row}:"
                            f"{get_column_letter(column)}{last_data_row})"
                        )
        worksheet.freeze_panes = "A3"
        worksheet.auto_filter.ref = f"A2:{get_column_letter(len(worksheet_spec.headers))}{2 + len(worksheet_spec.rows)}"
        for column, header in enumerate(worksheet_spec.headers, start=1):
            values = [str(header)] + [
                str(row[column - 1] if row[column - 1] is not None else "")
                for row in worksheet_spec.rows
            ]
            worksheet.column_dimensions[get_column_letter(column)].width = min(
                max(max(map(len, values)) + 2, 12), 48
            )
    workbook.save(path)


def _generate_text(spec: DocumentSpec, path: Path) -> None:
    chunks = [spec.title, "=" * len(spec.title)]
    if spec.subtitle:
        chunks.extend((spec.subtitle, ""))
    if spec.audience:
        chunks.extend((f"Audience: {spec.audience}", ""))
    for section in spec.sections:
        chunks.extend((section.heading, "-" * len(section.heading)))
        chunks.extend(section.paragraphs)
        chunks.extend(f"- {item}" for item in section.bullets)
        chunks.extend(section.code_blocks)
        chunks.extend(_plain_table(table) for table in section.tables)
        chunks.append("")
    _append_text_sources(chunks, spec)
    path.write_text("\n".join(chunks).rstrip() + "\n", encoding="utf-8")


def _generate_markdown(spec: DocumentSpec, path: Path) -> None:
    chunks = [f"# {spec.title}"]
    if spec.subtitle:
        chunks.extend(("", f"*{spec.subtitle}*"))
    if spec.audience:
        chunks.extend(("", f"**Audience:** {spec.audience}"))
    for section in spec.sections:
        chunks.extend(("", f"## {section.heading}"))
        for paragraph in section.paragraphs:
            chunks.extend(("", paragraph))
        if section.bullets:
            chunks.append("")
            chunks.extend(f"- {item}" for item in section.bullets)
        for code in section.code_blocks:
            fence = "```"
            while fence in code:
                fence += "`"
            chunks.extend(("", fence, code, fence))
        for table in section.tables:
            chunks.extend(("", _markdown_table(table)))
    if spec.sources:
        chunks.extend(
            (
                "",
                "## Research note",
                "Source references use provider snippets; AI-generated explanations "
                "are not independently verified.",
                "",
                "## Sources",
            )
        )
        for source in spec.sources:
            title = source.title.replace("[", "\\[").replace("]", "\\]")
            date = (
                f" (provider publication date: {source.published_date})"
                if source.published_date
                else ""
            )
            chunks.append(f"- [{title}]({source.url}){date} — search-result snippet; page not independently verified")
    path.write_text("\n".join(chunks).rstrip() + "\n", encoding="utf-8")


def _append_sources(document, spec: DocumentSpec) -> None:
    if not spec.sources:
        return
    document.add_heading("Sources", level=1)
    for source in spec.sources:
        paragraph = document.add_paragraph(style="List Bullet")
        _add_word_hyperlink(paragraph, source.title, source.url)
        paragraph.add_run(f" — {source.url}")
        if source.published_date:
            paragraph.add_run(f" (provider publication date: {source.published_date})")
        paragraph.add_run(" [search-result snippet; page not independently verified]")


def _append_text_sources(chunks: list[str], spec: DocumentSpec) -> None:
    if spec.sources:
        chunks.extend(
            (
                "Research note: source references use provider snippets; AI-generated "
                "explanations are not independently verified.",
                "",
                "Sources",
                "-------",
            )
        )
        for source in spec.sources:
            date = f" (published: {source.published_date})" if source.published_date else ""
            chunks.append(f"- {source.title}: {source.url}{date} [search-result snippet; page not independently verified]")


def _plain_table(table: DataTable) -> str:
    rows = [" | ".join(table.headers)]
    rows.extend(" | ".join("" if value is None else str(value) for value in row) for row in table.rows)
    return "\n".join(rows)


def _markdown_table(table: DataTable) -> str:
    escape = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
    header = "| " + " | ".join(map(escape, table.headers)) + " |"
    separator = "| " + " | ".join("---" for _ in table.headers) + " |"
    rows = [
        "| " + " | ".join(escape(value) for value in row) + " |"
        for row in table.rows
    ]
    return "\n".join((header, separator, *rows))


def _pdf_escape(value: str) -> str:
    return html.escape(_pdf_text(value), quote=False).replace("\n", "<br/>")


def _pdf_text(value: str) -> str:
    return value.encode("latin-1", errors="replace").decode("latin-1")


def _hex_rgb(value: str) -> tuple[int, int, int]:
    color = value.lstrip("#")
    return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))


def _unique_sheet_name(name: str, existing: set[str]) -> str:
    candidate = name[:31]
    index = 2
    while candidate.casefold() in existing:
        suffix = f" {index}"
        candidate = f"{name[: 31 - len(suffix)]}{suffix}"
        index += 1
    return candidate


def _excel_value(header: str, value):
    if isinstance(value, str) and re.search(r"\bdate\b", header, re.IGNORECASE):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value
    return value


def _slide_text(slide) -> str:
    values = []
    for shape in slide.shapes:
        if hasattr(shape, "text"):
            values.append(shape.text)
        if getattr(shape, "has_table", False):
            values.extend(
                cell.text
                for row in shape.table.rows
                for cell in row.cells
            )
    return "\n".join(values)
