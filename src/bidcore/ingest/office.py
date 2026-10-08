"""DOCX / PPTX / XLSX / CSV / TXT / MD -> marker pages.

WHY: only PDFs have physical pages.  Every other format is cut into synthetic pages ("blocks") of
about BLOCK_CHARS characters - the old ingestion router's pseudo-page - so evidence can still cite a
page and read_section can still return a small slice.  A table is never split across a block
boundary except by `chunk_rows`, which repeats the header in each part; a PPTX slide and an XLSX
sheet chunk are each one page.

Structure that the agents rely on is kept: DOCX heading styles become Markdown headings (they feed
the index outline), DOCX/PPTX tables become `[EXTRACTED TABLE -- p.N]` blocks, embedded pictures
become ImageRefs at their position (captioned later by images.process_images).
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Iterable

from .images import docx_element_images, pptx_shape_image
from .models import BLOCK_CHARS, Extracted, ImageRef, Page, table_block
from .tables import chunk_rows, is_meaningful_table, table_to_markdown

_HEADING_STYLE_RE = re.compile(r"^(?:heading|überschrift|titre|título)\s*(\d)", re.IGNORECASE)
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class _Pager:
    """Accumulates rendered parts into pages of about `limit` characters."""

    def __init__(self, limit: int = BLOCK_CHARS) -> None:
        self.limit = limit
        self.pages: list[Page] = []
        self._parts: list[str | ImageRef] = []
        self._size = 0

    def _flush(self) -> None:
        if self._parts:
            self.pages.append(Page(len(self.pages) + 1, self._parts))
            self._parts, self._size = [], 0

    @property
    def number(self) -> int:
        """Page number the next part lands on."""
        return len(self.pages) + 1

    def add_text(self, text: str, *, keep_together: bool = False) -> None:
        text = text.strip()
        if not text:
            return
        if self._size and self._size + len(text) > self.limit:
            self._flush()
        if not keep_together and len(text) > self.limit:
            for piece in _split_long(text, self.limit):
                self.add_text(piece, keep_together=True)
            return
        self._parts.append(text)
        self._size += len(text) + 2

    def add_table(self, rows: list[list[Any]]) -> None:
        if not is_meaningful_table(rows):
            flat = " ".join(str(c).strip() for row in rows or [] for c in row if c is not None and str(c).strip())
            self.add_text(flat)
            return
        for index, group in enumerate(chunk_rows(rows, self.limit)):
            md = table_to_markdown(group)
            if self._size and self._size + len(md) > self.limit:
                self._flush()
            self._parts.append(table_block(self.number, md, continued=index > 0))
            self._size += len(md) + 60

    def add_image(self, ref: ImageRef) -> None:
        self._parts.append(ref)

    def break_page(self) -> None:
        self._flush()

    def finish(self) -> list[Page]:
        self._flush()
        return self.pages


def _split_long(text: str, limit: int) -> Iterable[str]:
    """Paragraph-, then line-, then hard-split a text longer than one block."""
    buf = ""
    for para in re.split(r"\n{2,}", text):
        pieces = [para] if len(para) <= limit else para.split("\n")
        for piece in pieces:
            while len(piece) > limit:
                yield piece[:limit]
                piece = piece[limit:]
            if buf and len(buf) + len(piece) + 2 > limit:
                yield buf
                buf = ""
            buf = f"{buf}\n\n{piece}" if buf else piece
    if buf:
        yield buf


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- DOCX

def _docx_heading_level(paragraph: Any) -> int:
    style = getattr(getattr(paragraph, "style", None), "name", "") or ""
    if style.lower() == "title":
        return 1
    match = _HEADING_STYLE_RE.match(style)
    return min(int(match.group(1)), 6) if match else 0


def _docx_paragraph_text(paragraph: Any) -> str:
    text = paragraph.text.strip()
    if not text:
        return ""
    level = _docx_heading_level(paragraph)
    if level:
        return f"{'#' * level} {' '.join(text.split())}"
    style = (getattr(getattr(paragraph, "style", None), "name", "") or "").lower()
    if "list" in style:
        return f"- {text}"
    return text


def _docx_table_rows(table: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.rows:
        cells: list[str] = []
        previous = None
        for cell in row.cells:
            # python-docx repeats a merged cell's object across its span; keep one copy
            text = "" if cell._tc is previous else cell.text
            previous = cell._tc
            cells.append(text)
        rows.append(cells)
    return rows


def docx_pages(data: bytes) -> Extracted:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(io.BytesIO(data))
    pager = _Pager()
    part = document.part
    for element in document.element.body.iterchildren():
        tag = element.tag
        if tag == f"{_W_NS}p":
            paragraph = Paragraph(element, document)
            text = _docx_paragraph_text(paragraph)
            if text.startswith("# ") and pager._size > BLOCK_CHARS // 3:
                pager.break_page()          # a new chapter starts a new block when the current one has content
            pager.add_text(text)
            for blob, mime in docx_element_images(element, part):
                pager.add_image(ImageRef(data=blob, mime=mime, context=text[:400]))
        elif tag == f"{_W_NS}tbl":
            table = Table(element, document)
            pager.add_table(_docx_table_rows(table))
            for blob, mime in docx_element_images(element, part):
                pager.add_image(ImageRef(data=blob, mime=mime))
    return Extracted(pager.finish(), unit_note=f"blocks of about {BLOCK_CHARS} characters (DOCX has no fixed pages)")


# --------------------------------------------------------------------------- PPTX

def _pptx_shape_parts(shape: Any, out: list[str | ImageRef], rows_out: list[list[list[str]]]) -> None:
    if getattr(shape, "shape_type", None) is not None and shape.shape_type == 6:      # GROUP
        for child in shape.shapes:
            _pptx_shape_parts(child, out, rows_out)
        return
    if getattr(shape, "has_table", False) and shape.has_table:
        rows_out.append([[cell.text for cell in row.cells] for row in shape.table.rows])
        out.append("\0table")
        return
    picture = pptx_shape_image(shape) if shape.__class__.__name__ == "Picture" else None
    if picture is not None:
        blob, mime, width, height = picture
        out.append(ImageRef(data=blob, mime=mime, width=width, height=height))
        return
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        text = "\n".join(p.text for p in shape.text_frame.paragraphs if p.text.strip())
        if text.strip():
            out.append(text.strip())


def pptx_pages(data: bytes) -> Extracted:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    pages: list[Page] = []
    for number, slide in enumerate(presentation.slides, start=1):
        parts: list[str | ImageRef] = []
        title_shape = slide.shapes.title
        title = title_shape.text.strip() if title_shape is not None and title_shape.has_text_frame else ""
        if title:
            parts.append(f"## {' '.join(title.split())}")
        raw: list[str | ImageRef] = []
        tables: list[list[list[str]]] = []
        for shape in slide.shapes:
            if title_shape is not None and shape.shape_id == title_shape.shape_id:
                continue
            _pptx_shape_parts(shape, raw, tables)
        table_iter = iter(tables)
        for item in raw:
            if item == "\0table":
                rows = next(table_iter)
                parts.append(table_block(number, table_to_markdown(rows)) if is_meaningful_table(rows)
                             else " ".join(c for r in rows for c in r if c.strip()))
            elif isinstance(item, ImageRef):
                item.context = title
                parts.append(item)
            else:
                parts.append(item)
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip() if slide.notes_slide.notes_text_frame else ""
            if notes:
                parts.append(f"Speaker notes: {notes}")
        pages.append(Page(number, parts))
    return Extracted(pages, unit_note="slides")


# --------------------------------------------------------------------------- XLSX / CSV

def _trim(rows: list[list[Any]]) -> list[list[Any]]:
    """Drop empty rows and trailing empty columns."""
    rows = [list(r) for r in rows if any(c is not None and str(c).strip() for c in r)]
    if not rows:
        return []
    width = max((max((i + 1 for i, c in enumerate(r) if c is not None and str(c).strip()), default=0) for r in rows))
    return [(r + [None] * width)[:width] for r in rows]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def xlsx_pages(data: bytes) -> Extracted:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    pager = _Pager()
    warnings: list[str] = []
    try:
        for sheet in workbook.worksheets:
            rows = _trim([[_cell(c) for c in row] for row in sheet.iter_rows(values_only=True)])
            pager.break_page()
            pager.add_text(f"## Sheet: {sheet.title}")
            if not rows:
                pager.add_text("(empty sheet)")
                continue
            pager.add_table(rows)
    finally:
        workbook.close()
    return Extracted(pager.finish(), warnings, unit_note="spreadsheet blocks (each sheet starts a new block)")


def csv_pages(data: bytes) -> Extracted:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = _trim([list(r) for r in csv.reader(io.StringIO(text), dialect)])
    pager = _Pager()
    pager.add_table(rows)
    return Extracted(pager.finish(), unit_note="table blocks")


# --------------------------------------------------------------------------- TXT / MD

def text_pages(data: bytes, *, markdown: bool = False) -> Extracted:
    text = _decode(data).replace("\r\n", "\n").replace("\r", "\n")
    pager = _Pager()
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if markdown and para.startswith("# ") and pager._size > BLOCK_CHARS // 3:
            pager.break_page()
        pager.add_text(para)
    return Extracted(pager.finish(), unit_note=f"blocks of about {BLOCK_CHARS} characters")
