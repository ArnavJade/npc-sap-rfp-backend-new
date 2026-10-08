"""PDF -> per-page Markdown through a pluggable engine.

WHY: most RFPs are PDFs and their tables carry the scope.  pymupdf4llm (default) renders every
page as Markdown with pipe tables, in-process, using PyMuPDF's ONNX layout model (~0.3 s/page).
Docling (optional extra: MIT but heavy - torch) is the alternative for documents where its table
model does better.  Both sit behind one protocol and the INGEST_PDF_ENGINE switch, so the choice
is configuration, not code.  PyMuPDF is AGPL-3.0: licence review before production (pyproject).

Engine-independent post-processing also lives here:
- running headers/footers - a line repeated at the top/bottom edge of >= 40 % of pages, digits
  ignored ('ARASCO Confidential ...', 'Page 3 of 52') - are removed: they would be the most
  frequent grep hit and pollute the outline.  The engine is asked to KEEP its header/footer boxes
  and we strip by repetition instead, because pymupdf4llm's layout model also labels real content
  at the top of a sparse page as a page header (a 'Phase II -' line was lost that way);
- dot leaders ('INTRODUCTION ........ 4') are collapsed, headings lose their bold markers, and
  '<br>' outside tables (diagram text) becomes a line break;
- pipe tables are wrapped in [EXTRACTED TABLE -- p.N] blocks;
- embedded raster images are appended to their page (captioned later, see images.py);
- pages without extractable text are reported (scanned page or blank) - OCR is off by default.
"""

from __future__ import annotations

import io
import math
import os
import re
from collections import Counter
from typing import Protocol

from .images import pdf_page_images
from .models import Extracted, Page
from .tables import wrap_pipe_tables

DEFAULT_ENGINE = "pymupdf4llm"
_RUNNING_SHARE = 0.4
_DIGITS_RE = re.compile(r"\d+")
_HEADING_PREFIX_RE = re.compile(r"^#{1,6}\s+")
_DOT_LEADER_RE = re.compile(r"(?:\s?\.){5,}")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


class PdfEngine(Protocol):
    """Turns PDF bytes into one Markdown string per physical page (index 0 = page 1)."""

    name: str

    def to_pages(self, data: bytes) -> list[str]: ...


class Pymupdf4llmEngine:
    name = "pymupdf4llm"

    def __init__(self, *, use_ocr: bool = False) -> None:
        self.use_ocr = use_ocr  # needs Tesseract/RapidOCR installed; off keeps runs deterministic

    def to_pages(self, data: bytes) -> list[str]:
        import pymupdf
        import pymupdf4llm

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise ValueError("PDF is password-protected")
            count = doc.page_count
            if not count:
                return []
            chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, header=True, footer=True,
                                             use_ocr=self.use_ocr, show_progress=False)
        pages = [""] * count
        for index, chunk in enumerate(chunks):
            meta = chunk.get("metadata") or {}
            number = int(meta.get("page_number") or meta.get("page") or index + 1)
            if 1 <= number <= count:
                pages[number - 1] = str(chunk.get("text") or "")
        return pages


class DoclingEngine:
    name = "docling"

    def __init__(self) -> None:
        try:
            import docling.document_converter  # noqa: F401  (lazy: optional, heavy dependency)
        except ImportError as exc:
            raise RuntimeError(
                "INGEST_PDF_ENGINE=docling needs the optional 'docling' extra, which is not "
                "installed: pip install 'sap-rfp-harness[docling]' (or use pymupdf4llm)"
            ) from exc
        self._converter = None

    def to_pages(self, data: bytes) -> list[str]:
        from docling.datamodel.base_models import DocumentStream
        from docling.document_converter import DocumentConverter

        if self._converter is None:
            self._converter = DocumentConverter()
        result = self._converter.convert(DocumentStream(name="document.pdf", stream=io.BytesIO(data)))
        document = result.document
        return [document.export_to_markdown(page_no=n) for n in range(1, document.num_pages() + 1)]


_ENGINES = {"pymupdf4llm": Pymupdf4llmEngine, "docling": DoclingEngine}


def get_engine(name: str | None = None) -> PdfEngine:
    """Engine by name, else env INGEST_PDF_ENGINE, else pymupdf4llm."""
    key = (name or os.getenv("INGEST_PDF_ENGINE") or DEFAULT_ENGINE).strip().lower()
    factory = _ENGINES.get(key)
    if factory is None:
        raise ValueError(f"unknown PDF engine {key!r}; expected one of: {', '.join(_ENGINES)}")
    return factory()


def _line_key(line: str) -> str:
    text = _HEADING_PREFIX_RE.sub("", line.strip())
    text = " ".join(text.replace("**", "").replace("__", "").replace("`", "").split()).lower()
    return _DIGITS_RE.sub("#", text)


def _edge_lines(lines: list[str]) -> set[int]:
    filled = [i for i, line in enumerate(lines) if line.strip()]
    return {i for i in filled[:2] + filled[-2:]
            if not lines[i].lstrip().startswith("|") and len(lines[i]) <= 200}


def strip_running_lines(pages: list[str], min_share: float = _RUNNING_SHARE) -> list[str]:
    """Drop header/footer lines repeated at the page edges of >= min_share of the pages."""
    if len(pages) < 3:
        return pages
    split = [text.split("\n") for text in pages]
    edges = [_edge_lines(lines) for lines in split]
    counts: Counter[str] = Counter()
    for lines, idx in zip(split, edges):
        counts.update({_line_key(lines[i]) for i in idx} - {""})
    threshold = max(3, math.ceil(min_share * len(pages)))
    running = {key for key, count in counts.items() if count >= threshold}
    if not running:
        return pages
    return ["\n".join(line for i, line in enumerate(lines) if not (i in idx and _line_key(line) in running))
            for lines, idx in zip(split, edges)]


def tidy(text: str) -> str:
    """Normalise engine Markdown (leaders, bold headings, stray backticks, blank runs)."""
    out = []
    for line in _DOT_LEADER_RE.sub(" ... ", text).split("\n"):
        line = line.rstrip()
        if line.strip() == "`":
            continue
        if _HEADING_PREFIX_RE.match(line):
            line = line.replace("**", "")
        elif not line.lstrip().startswith("|"):
            line = _BR_RE.sub("\n", line)
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def page_ranges(numbers: list[int]) -> str:
    """[3, 5, 6, 7] -> '3, 5-7'."""
    spans: list[list[int]] = []
    for n in sorted(numbers):
        if spans and n == spans[-1][1] + 1:
            spans[-1][1] = n
        else:
            spans.append([n, n])
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in spans)


def pdf_pages(data: bytes, engine: PdfEngine) -> Extracted:
    """PDF bytes -> marker pages with wrapped tables and image placeholders, plus warnings."""
    import pymupdf

    raw = strip_running_lines(engine.to_pages(data))
    pages: list[Page] = []
    scanned: list[int] = []
    blank: list[int] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for index, text in enumerate(raw):
            number = index + 1
            body = wrap_pipe_tables(tidy(text), number)
            page = Page(number, [body] if body else [])
            source = doc[index] if index < doc.page_count else None
            if source is not None:
                page.parts.extend(pdf_page_images(doc, source))
            if sum(ch.isalnum() for ch in body) < 20:
                (scanned if source is not None and source.get_images() else blank).append(number)
            pages.append(page)
    warnings = []
    if scanned:
        warnings.append(f"{len(scanned)} page(s) have images but no extractable text (scanned?): "
                        f"p.{page_ranges(scanned)} - content only via image captions")
    if blank:
        warnings.append(f"{len(blank)} page(s) have no extractable text: p.{page_ranges(blank)}")
    return Extracted(pages, warnings, unit_note=f"physical PDF pages (engine {engine.name})")
