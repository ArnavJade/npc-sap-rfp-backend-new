"""Embedded images: extract, filter, caption through an injected callable, cache, render.

WHY: diagrams and pasted tables carry scope that text extraction cannot see (integration
landscapes, country x module matrices).  The old Aperture pipeline sent them to a vision model;
here the model call is injected - `caption(image_bytes, mime, context) -> str` - so bidcore has no
LLM/network imports and tests can count calls.  The caller sends VISION_PROMPT (filled with the
context) plus the image and returns the model's text; that text is inserted verbatim as an
`[EMBEDDED IMAGE -- p.N]` block.  Captions are cached by image sha1 in `<cache_dir>/captions.json`
so a re-ingest (call 2 re-reading the call-1 RFP) never pays twice.

Filtering ports aperture/image_filter.py (min bytes / size / aspect) and the sha1 de-duplication
of aperture/orchestrator.py, plus one rule: an image repeated on 3+ pages of a file is page
furniture (logo, banner) and is never captioned.  At most INGEST_MAX_IMAGES_PER_FILE (default 30)
images per file go to the captioner.
"""

from __future__ import annotations

import io
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from .models import PAGE_MARKER_RE, ImageRef, Page, image_block

CaptionFn = Callable[[bytes, str, str], str]

# Ported from aperture/prompts.py ANALYSIS_PROMPT_TEMPLATE; the JSON envelope is replaced by a
# plain-text reply because the caller's string is inserted as-is.  Fill with
# VISION_PROMPT.format(context=...) - the text has no other braces.
NO_CONTENT_REPLY = "NO_SCOPE_CONTENT"
VISION_PROMPT = """You are analysing ONE image extracted from an SAP RFP (Request for Proposal)
document. It may be a country x module scope matrix, a requirements table,
an organisation chart, an architecture/interface/integration diagram, a
spreadsheet screenshot, or a purely decorative graphic (logo, banner,
divider).

Downstream, your transcription is read exactly like the RFP's native text.
For architecture/interface/integration diagrams specifically, it is used to
identify THIRD-PARTY (non-SAP) systems or tools that integrate with the
client's SAP landscape, and the SAP-side detail of each integration (which
SAP module/process/component it connects to, interface type, data
exchanged, direction, etc.) -- NOT to produce a general description of the
picture. Anything you summarise instead of transcribe/extract, or skip
because it looked minor, becomes permanently invisible downstream -- so
completeness matters more than brevity here.

RULES
1. Transcribe ALL visible text verbatim. Do not summarise, paraphrase, or
   omit any label, header, footnote, or number, however small.
2. If the image contains a table or matrix -- especially a country x module
   / capability matrix -- reconstruct it as a markdown table, every row and
   column exactly as shown. Do not skip rows or merge cells with different
   content. Transcribe marks (X, checkmark, filled cell, "Yes") exactly
   against their row and column.
3. Preserve country names, country codes, and SAP module/solution names
   exactly as written. Do not translate, rename, or normalise them.
4. If the image is an architecture, interface, or integration diagram
   (boxes/systems connected by lines or arrows, an integration landscape,
   an interface/connectivity map, etc.), do NOT write a prose description
   of the picture. Instead extract EVERY connection/edge shown as one
   concise line per connection, in this exact form:
       <System/Tool A> <-> <System/Tool B, or the specific SAP module/
       process/component it connects to> : <label, purpose, or technical
       detail attached to that connection, verbatim>
   - Preserve every system/tool name and every SAP-related term (module
     names such as FI, CO, MM, Treasury, Cash, Bank, etc.) exactly as
     labelled -- do not translate, rename, or normalise them.
   - One line per distinct connection; never merge multiple connections
     into a single sentence.
   - If a connection has no attached label/detail text, omit the trailing
     " : <detail>" part rather than inventing one.
   - Example lines (format only -- transcribe what you actually see, never
     copy these verbatim):
       REST <-> SAP FI/CO : Real-time RFC interfaces (SAP side)
       Coupa <-> SAP (Treasury / Cash / Bank)
   For any OTHER kind of diagram with no integration/interface meaning (org
   chart, timeline, generic process flow), describe every labelled node and
   every connection between them in plain sentences, quoting each label
   verbatim.
5. If the image is decorative and carries no RFP-scope information, reply
   with exactly NO_SCOPE_CONTENT and nothing else. Never invent, infer, or
   complete content not visibly present.
6. Before answering, re-scan the image once more end-to-end and confirm
   every row of every table, every visible country/module name, and every
   connection/edge of any diagram, has been captured.

Document context, for orientation only -- do not copy it back:
\"\"\"
{context}
\"\"\"

Reply in plain text (markdown tables allowed), with no preamble and no code
fences. First line: "Image type: <table_matrix | diagram | chart |
screenshot_text | other>", then the transcription."""

# Decorative-image filter thresholds (aperture/config.py defaults).
MIN_IMAGE_WIDTH = 100
MIN_IMAGE_HEIGHT = 100
MIN_IMAGE_BYTES = 5000
MAX_ASPECT_RATIO = 20.0
LOGO_REPEAT_PAGES = 3
CONTEXT_CHARS = 400
_MAX_VISION_EDGE = 2000  # px; larger images (scanned pages) are downscaled before captioning
_MAX_VISION_BYTES = 4_500_000

_EXT_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
             "webp": "image/webp", "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff",
             "jpx": "image/jp2", "jp2": "image/jp2"}
_A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
_V_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
_R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_BLOCK_LINE_RE = re.compile(r"^\s*\[(?:END )?(?:EMBEDDED IMAGE|EXTRACTED TABLE)\b.*$", re.MULTILINE)


def vision_prompt(context: str) -> str:
    return VISION_PROMPT.format(context=(context or "").strip() or "(no surrounding text available)")


def max_images_per_file() -> int:
    try:
        return max(0, int(os.getenv("INGEST_MAX_IMAGES_PER_FILE", "30")))
    except ValueError:
        return 30


def is_relevant_image(data: bytes, width: int | None = None, height: int | None = None) -> bool:
    """True when an image is plausibly content (table, chart, diagram, photo), not decoration.

    Fails open when dimensions are unknown (ported from aperture/image_filter.py)."""
    if not data or len(data) < MIN_IMAGE_BYTES:
        return False
    if width and height and width > 0 and height > 0:
        if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
            return False
        if max(width, height) / min(width, height) > MAX_ASPECT_RATIO:
            return False
    return True


def _dimensions(ref: ImageRef) -> tuple[int | None, int | None]:
    if ref.width and ref.height:
        return ref.width, ref.height
    try:
        from PIL import Image

        with Image.open(io.BytesIO(ref.data)) as img:
            return img.size
    except Exception:
        return None, None


def prepare_for_vision(data: bytes, mime: str) -> tuple[bytes, str] | None:
    """Bytes a vision API accepts (PNG/JPEG/GIF/WEBP, <= 2000 px edge); None if unreadable here."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or "").upper()
            small = max(img.size) <= _MAX_VISION_EDGE and len(data) <= _MAX_VISION_BYTES
            if small and fmt in ("PNG", "JPEG", "GIF", "WEBP") and img.mode in ("RGB", "RGBA", "L", "P"):
                return data, Image.MIME.get(fmt, mime)
            img.load()
            out = img.convert("RGB")
            out.thumbnail((_MAX_VISION_EDGE, _MAX_VISION_EDGE))
            buffer = io.BytesIO()
            out.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue(), "image/png"
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Extraction helpers (positions are decided by the format converters)
# ---------------------------------------------------------------------------

def pdf_page_images(doc: Any, page: Any) -> list[ImageRef]:
    """Embedded raster images of one pymupdf page (cheap size pre-filter applied)."""
    refs: list[ImageRef] = []
    seen: set[int] = set()
    for info in page.get_images(full=True):
        xref, width, height = info[0], info[2], info[3]
        if xref in seen or width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
            continue
        seen.add(xref)
        try:
            extracted = doc.extract_image(xref)
        except Exception:
            continue
        if not extracted or not extracted.get("image"):
            continue
        ext = str(extracted.get("ext") or "png").lower()
        refs.append(ImageRef(data=extracted["image"], mime=_EXT_MIME.get(ext, f"image/{ext}"),
                             width=width, height=height, context=_pdf_context(page, xref)))
    return refs


def _pdf_context(page: Any, xref: int) -> str:
    """Text just above the image (the caption/heading usually sits there), else the page start."""
    try:
        import pymupdf

        rects = page.get_image_rects(xref)
        if rects:
            top = rects[0].y0
            clip = pymupdf.Rect(page.rect.x0, max(page.rect.y0, top - 150), page.rect.x1, top)
            text = " ".join(page.get_text("text", clip=clip).split())
            if text:
                return text[-CONTEXT_CHARS:]
        return " ".join(page.get_text("text").split())[:CONTEXT_CHARS]
    except Exception:
        return ""


def docx_element_images(element: Any, part: Any) -> list[tuple[bytes, str]]:
    """(blob, content type) of every picture referenced inside a DOCX body element, in order.

    Resolves DrawingML blips and legacy VML imagedata through the package relationships, so
    floating (anchored) pictures are found as well as inline ones; mc:Fallback copies are skipped."""
    found: list[tuple[bytes, str]] = []
    for node in element.iter(_A_BLIP, _V_IMAGEDATA):
        if any(ancestor.tag == _MC_FALLBACK for ancestor in node.iterancestors()):
            continue
        rid = node.get(_R_NS + ("embed" if node.tag == _A_BLIP else "id"))
        target = part.related_parts.get(rid) if rid else None
        blob = getattr(target, "blob", None)
        if blob:
            found.append((blob, str(getattr(target, "content_type", "") or "")))
    return found


def pptx_shape_image(shape: Any) -> tuple[bytes, str, int | None, int | None] | None:
    """(blob, content type, width, height) for a picture shape, else None."""
    try:
        image = shape.image
        blob = image.blob
    except Exception:
        return None
    try:
        width, height = image.size
    except Exception:
        width = height = None
    return blob, str(image.content_type or ""), width, height


# ---------------------------------------------------------------------------
# Cache, selection, captioning, rendering
# ---------------------------------------------------------------------------

class CaptionCache:
    """{image sha1: caption} persisted as JSON; '' records 'no scope content' so it is not re-asked."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._data: dict[str, str] = {}
        if path is not None and path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._data = {str(k): str(v) for k, v in loaded.items()}
            except (OSError, ValueError):
                self._data = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, caption: str) -> None:
        self._data[key] = caption
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)


def clean_caption(reply: Any) -> str:
    """Model reply -> block content; '' for decorative images.  Lines that would read as
    workspace markers are dropped so a caption can never corrupt the page/block structure."""
    text = str(reply or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z]*\n?|\n?```$", "", text).strip()
    if not text or text.upper().startswith(NO_CONTENT_REPLY):
        return ""
    text = _BLOCK_LINE_RE.sub("", PAGE_MARKER_RE.sub("", text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def process_images(pages: list[Page], *, caption: CaptionFn | None, cache: CaptionCache,
                   max_images: int, label: str = "") -> tuple[int, list[str]]:
    """Filter, de-duplicate and caption every ImageRef in `pages` in place.

    Returns (images captioned, warnings).  A captioner exception is reported, not cached, and
    never aborts ingestion."""
    refs = [(page.number, part) for page in pages for part in page.parts if isinstance(part, ImageRef)]
    if not refs:
        return 0, []
    pages_with: dict[str, set[int]] = defaultdict(set)
    for number, ref in refs:
        pages_with[ref.sha1].add(number)
    first: dict[str, tuple[int, ImageRef]] = {}
    counts: Counter[str] = Counter()
    failures: list[str] = []
    sent = 0
    for number, ref in refs:
        if not is_relevant_image(ref.data, *_dimensions(ref)) or len(pages_with[ref.sha1]) >= LOGO_REPEAT_PAGES:
            continue
        if ref.sha1 in first:
            ref.duplicate_of = first[ref.sha1][0]
            continue
        first[ref.sha1] = (number, ref)
        if caption is None:
            counts["uncaptioned"] += 1
            continue
        if sent >= max_images:
            counts["over_cap"] += 1
            continue
        sent += 1
        cached = cache.get(ref.sha1)
        if cached is not None:
            ref.caption = cached
            continue
        prepared = prepare_for_vision(ref.data, ref.mime)
        if prepared is None:
            counts["unsupported"] += 1
            continue
        context = f"File {label!r}, page {number}. Text near the image: {ref.context or '(none)'}"
        try:
            ref.caption = clean_caption(caption(prepared[0], prepared[1], context))
        except Exception as exc:  # the injected captioner may fail; ingestion goes on
            failures.append(f"p.{number}: {type(exc).__name__}: {exc}"[:200])
            continue
        cache.put(ref.sha1, ref.caption)
    for _, ref in refs:
        if ref.duplicate_of is not None and first[ref.sha1][1].caption:
            ref.caption = f"(same image as p.{ref.duplicate_of} - see the transcription there)"
    warnings = []
    if counts["uncaptioned"]:
        warnings.append(f"{counts['uncaptioned']} embedded image(s) not captioned: no captioner configured")
    if counts["over_cap"]:
        warnings.append(f"{counts['over_cap']} image(s) not captioned: over INGEST_MAX_IMAGES_PER_FILE={max_images}")
    if counts["unsupported"]:
        warnings.append(f"{counts['unsupported']} image(s) skipped: format cannot be rasterised here (e.g. EMF/WMF)")
    if failures:
        warnings.append(f"{len(failures)} caption call(s) failed (not cached, retried next run): {failures[0]}")
    captioned = sum(1 for _, ref in refs if ref.caption and ref.duplicate_of is None)
    return captioned, warnings


def render_image(ref: ImageRef, page: int) -> str:
    return image_block(page, ref.caption) if ref.caption else ""
