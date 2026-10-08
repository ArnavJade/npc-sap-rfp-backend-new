"""Client files -> the ingested RFP workspace (`rfp/<slug>.md` + `rfp/index.md`), and reads from it.

WHY: agents never get a whole RFP in their prompt.  They start from a compact `index.md` (files,
outline with pages, tables, wave anchors, third-party candidates), grep the per-file Markdown, and
pull page ranges with `read_section`.  The page marker `<!-- page: N -->` is the citation unit of
every ledger evidence row, so the same format is produced for every input type.

The index is rebuilt from ALL files in the directory on every ingest, so call 2 can add an RFP file
call 1 never saw without losing the original.  File records persist in `rfp/.files.json`; the
deterministic pre-scans (anchors, declared waves, third-party candidates) are also written to
`<cache_dir>/prescan.json` for workflow-side recall checks.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

from .anchors import detect_sequencing, find_wave_anchors, scan_declared_waves
from .images import CaptionCache, CaptionFn, max_images_per_file, process_images, render_image
from .models import PAGE_MARKER_RE, Extracted, IngestedFile, IngestResult, ImageRef, page_marker
from .tables import scan_for_third_party, table_blocks, third_party_header

FILES_JSON = ".files.json"
INDEX_NAME = "index.md"
DEFAULT_MAX_CHARS = 20_000
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_KINDS = {".pdf": "pdf", ".docx": "docx", ".docm": "docx", ".pptx": "pptx", ".xlsx": "xlsx", ".xlsm": "xlsx",
          ".csv": "csv", ".txt": "txt", ".md": "md", ".markdown": "md"}
_INDEX_LIMITS = {"outline": 80, "tables": 40, "anchors": 40, "third_party": 60}


def file_kind(name: str) -> str:
    return _KINDS.get(Path(name).suffix.lower(), "unsupported")


def _slug(name: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-")
    return stem[:60].strip("-") or "file"


def _convert(kind: str, data: bytes, pdf_engine: str | None) -> Extracted:
    if kind == "pdf":
        from .pdf import get_engine, pdf_pages
        return pdf_pages(data, get_engine(pdf_engine))
    from . import office
    converters: dict[str, Callable[[bytes], Extracted]] = {
        "docx": office.docx_pages, "pptx": office.pptx_pages, "xlsx": office.xlsx_pages, "csv": office.csv_pages,
        "txt": office.text_pages, "md": lambda d: office.text_pages(d, markdown=True),
    }
    return converters[kind](data)


def _render(name: str, kind: str, extracted: Extracted) -> str:
    out = [f"# {name}", "", f"Source file: {name} ({kind}); page markers = {extracted.unit_note or 'pages'}.", ""]
    for page in extracted.pages:
        out += [page_marker(page.number), ""]
        for part in page.parts:
            text = render_image(part, page.number) if isinstance(part, ImageRef) else part
            if text:
                out += [text, ""]
    return "\n".join(out).rstrip() + "\n"


def _load_records(rfp_dir: Path) -> dict[str, IngestedFile]:
    path = rfp_dir / FILES_JSON
    if not path.is_file():
        return {}
    try:
        return {r["slug"]: IngestedFile.model_validate(r) for r in json.loads(path.read_text(encoding="utf-8"))}
    except (ValueError, KeyError, TypeError):
        return {}


def _save_records(rfp_dir: Path, records: dict[str, IngestedFile]) -> None:
    (rfp_dir / FILES_JSON).write_text(
        json.dumps([r.model_dump() for r in records.values()], indent=1, ensure_ascii=False), encoding="utf-8")


def _unique_slug(name: str, sha: str, records: dict[str, IngestedFile], taken: set[str]) -> str:
    base = _slug(name)
    for record in records.values():          # same bytes as an earlier ingest: reuse its file
        if record.sha256 == sha and record.slug not in taken:
            return record.slug
    slug, n = base, 2
    while slug in taken or (slug in records and records[slug].sha256 != sha) or slug == "index":
        slug, n = f"{base}-{n}", n + 1
    return slug


def ingest(files: list[tuple[str, bytes]], rfp_dir: Path, *, pdf_engine: str | None = None,
           caption: CaptionFn | None = None, cache_dir: Path | None = None) -> IngestResult:
    """Convert `(filename, bytes)` pairs into page-marked Markdown under `rfp_dir` and rebuild the index.

    Unsupported or unreadable files are recorded with a warning, never raised."""
    rfp_dir.mkdir(parents=True, exist_ok=True)
    records = _load_records(rfp_dir)
    cache = CaptionCache(cache_dir / "captions.json" if cache_dir else None)
    taken: set[str] = set()
    fresh: list[IngestedFile] = []
    for name, data in files:
        sha = hashlib.sha256(data).hexdigest()
        kind = file_kind(name)
        slug = _unique_slug(name, sha, records, taken)
        taken.add(slug)
        record = IngestedFile(name=name, slug=slug, md_path=f"rfp/{slug}.md", kind=kind, sha256=sha)
        if kind == "unsupported":
            record.warnings.append(f"unsupported file type '{Path(name).suffix}' - not ingested")
            fresh.append(record)
            continue
        try:
            extracted = _convert(kind, data, pdf_engine)
        except Exception as exc:   # one broken file must not lose the others
            record.warnings.append(f"could not read file: {type(exc).__name__}: {exc}"[:300])
            fresh.append(record)
            continue
        captioned, image_warnings = process_images(extracted.pages, caption=caption, cache=cache,
                                                   max_images=max_images_per_file(), label=name)
        text = _render(name, kind, extracted)
        (rfp_dir / f"{slug}.md").write_text(text, encoding="utf-8")
        record.pages = len(PAGE_MARKER_RE.findall(text))
        record.chars = len(text)
        record.tables = len(table_blocks(text))
        record.images_captioned = captioned
        record.warnings += extracted.warnings + image_warnings
        records[slug] = record
        fresh.append(record)
    _save_records(rfp_dir, records)
    result = build_index(rfp_dir)
    result.files = fresh
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "prescan.json").write_text(result.model_dump_json(indent=1), encoding="utf-8")
    return result


# --------------------------------------------------------------------------- reading

def split_pages(text: str) -> list[tuple[int, str]]:
    """[(page number, page text without its marker)] in document order."""
    marks = list(PAGE_MARKER_RE.finditer(text))
    return [(int(m.group(1)), text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)].strip("\n"))
            for i, m in enumerate(marks)]


def list_pages(rfp_dir: Path, file: str) -> list[int]:
    return [n for n, _ in split_pages(_read_file(rfp_dir, file))]


def _read_file(rfp_dir: Path, file: str) -> str:
    name = Path(file.replace("\\", "/")).name
    if not name.endswith(".md"):
        name += ".md"
    path = rfp_dir / name
    if name == INDEX_NAME or not path.is_file():
        raise FileNotFoundError(f"no ingested RFP file '{file}'")
    return path.read_text(encoding="utf-8")


def _truncate(text: str, max_chars: int, hint: str) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + f"\n\n[... truncated at {max_chars} characters - {hint}]"


def read_section(rfp_dir: Path, file: str, page_from: int | None = None, page_to: int | None = None,
                 heading: str = "", max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Pages `page_from..page_to` (inclusive, with their markers), or the block under `heading`."""
    text = _read_file(rfp_dir, file)
    if heading:
        return _read_heading(text, heading, max_chars)
    if page_from is None:
        raise ValueError("give page_from (and optionally page_to) or a heading")
    page_to = page_from if page_to is None else page_to
    if page_to < page_from:
        page_from, page_to = page_to, page_from
    pages = split_pages(text)
    chosen = [(n, body) for n, body in pages if page_from <= n <= page_to]
    if not chosen:
        last = pages[-1][0] if pages else 0
        return f"No pages {page_from}-{page_to} in {Path(file).name} (it has pages 1-{last})."
    out = "\n\n".join(f"{page_marker(n)}\n{body}" for n, body in chosen)
    return _truncate(out, max_chars, "read fewer pages at a time")


def _read_heading(text: str, heading: str, max_chars: int) -> str:
    wanted = " ".join(heading.lower().lstrip("#").split())
    headings = list(_HEADING_RE.finditer(text))
    match = next((h for h in headings if " ".join(h.group(2).lower().split()) == wanted), None)
    match = match or next((h for h in headings if wanted in h.group(2).lower()), None)
    if match is None:
        # Headings in PDFs are often plain bold lines: fall back to the first line containing the text.
        for line in re.finditer(r"^.*$", text, re.MULTILINE):
            if wanted and wanted in line.group(0).lower() and not PAGE_MARKER_RE.match(line.group(0)):
                start = line.start()
                page = _page_at(text, start)
                return _truncate(f"(from page {page})\n" + text[start:start + max_chars], max_chars,
                                 "use page ranges for more")
        return f"No heading matching '{heading}'. See the outline in /rfp/index.md or grep for it."
    level = len(match.group(1))
    end = len(text)
    for h in headings:
        if h.start() > match.start() and len(h.group(1)) <= level:
            end = h.start()
            break
    block = text[match.start():end].strip()
    return _truncate(f"(from page {_page_at(text, match.start())})\n{block}", max_chars, "use page ranges for more")


def _page_at(text: str, pos: int) -> int:
    page = 0
    for m in PAGE_MARKER_RE.finditer(text):
        if m.start() > pos:
            break
        page = int(m.group(1))
    return page


# --------------------------------------------------------------------------- index

def _scan_file(slug: str, text: str) -> dict:
    outline, tables, anchors, third_party = [], [], [], []
    previous_header: list[str] | None = None
    for number, body in split_pages(text):
        for h in _HEADING_RE.finditer(body):
            outline.append({"page": number, "level": len(h.group(1)), "title": h.group(2)[:120]})
        for anchor in find_wave_anchors(body):
            anchors.append({"file": f"{slug}.md", "page": number, "text": anchor[:200]})
        for index, (_, rows) in enumerate(table_blocks(body)):
            if not rows:
                continue
            header = [c for c in rows[0] if c]
            tables.append({"page": number, "columns": len(rows[0]), "rows": len(rows) - 1,
                           "header": " | ".join(header)[:160]})
            found = scan_for_third_party(rows)
            if not found and index == 0 and previous_header and len(previous_header) == len(rows[0]):
                found = scan_for_third_party(rows, header=previous_header)    # continuation from last page
            for item in found:
                third_party.append({"name": item["name"], "file": f"{slug}.md", "page": number,
                                    "evidence": item["evidence"]})
            previous_header = third_party_header(rows) or (previous_header if found else None)
    return {"outline": outline, "tables": tables, "anchors": anchors, "third_party": third_party}


def build_index(rfp_dir: Path) -> IngestResult:
    """Rebuild `index.md` from every ingested file; return the pre-scan results."""
    records = _load_records(rfp_dir)
    result = IngestResult(index_path=f"rfp/{INDEX_NAME}")
    lines = ["# RFP index", "",
             "Every file below is page-marked with `<!-- page: N -->`. grep /rfp/ to find a term, then "
             "`read_section(file, page_from, page_to)` for just those pages. Cite evidence as file + page.", "",
             "## Files", "", "| File | Source | Kind | Pages | Characters | Tables | Notes |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    scans: dict[str, dict] = {}
    all_text: list[str] = []
    for slug, record in sorted(records.items()):
        path = rfp_dir / f"{slug}.md"
        notes = "; ".join(record.warnings)[:200].replace("|", "/")
        lines.append(f"| /rfp/{slug}.md | {record.name.replace('|', '/')} | {record.kind} | {record.pages} | "
                     f"{record.chars:,} | {record.tables} | {notes} |")
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        all_text.append(text)
        scans[slug] = _scan_file(slug, text)
        result.total_chars += len(text)
    for slug, scan in scans.items():
        result.wave_anchors += scan["anchors"]
        result.third_party_candidates += scan["third_party"]
    joined = "\n".join(all_text)
    result.declared_waves = scan_declared_waves(joined)
    result.sequencing_hint = detect_sequencing(joined)

    for slug, scan in scans.items():
        lines += ["", f"## Outline - /rfp/{slug}.md", ""]
        outline = scan["outline"][:_INDEX_LIMITS["outline"]]
        lines += [f"{'  ' * (o['level'] - 1)}- p.{o['page']} {o['title']}" for o in outline] or ["(no headings found)"]
        if len(scan["outline"]) > len(outline):
            lines.append(f"- ... {len(scan['outline']) - len(outline)} more headings (grep '^#' in the file)")
        if scan["tables"]:
            lines += ["", f"### Tables - /rfp/{slug}.md", ""]
            shown = scan["tables"][:_INDEX_LIMITS["tables"]]
            lines += [f"- p.{t['page']}: {t['rows']} rows x {t['columns']} cols - {t['header']}" for t in shown]
            if len(scan["tables"]) > len(shown):
                lines.append(f"- ... {len(scan['tables']) - len(shown)} more tables (grep 'EXTRACTED TABLE')")

    lines += ["", "## Delivery waves (deterministic pre-scan - verify in the text)", ""]
    if result.declared_waves:
        lines += [f"- Declared: {w['label']}: {', '.join(w['entities']) or '-'}  ({w['raw_line'][:120]})"
                  for w in result.declared_waves]
    if result.sequencing_hint:
        lines.append(f"- Sequencing wording near wave mentions: {result.sequencing_hint}")
    anchors = result.wave_anchors[:_INDEX_LIMITS["anchors"]]
    lines += [f"- {a['file']} p.{a['page']}: {a['text']}" for a in anchors]
    if not (result.declared_waves or anchors):
        lines.append("- none found (single-wave programme, or waves only in images/tables)")

    lines += ["", "## Third-party system candidates (table scan - recall aid, not a decision)", ""]
    seen: set[str] = set()
    shown_tp = 0
    for item in result.third_party_candidates:
        key = item["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        if shown_tp >= _INDEX_LIMITS["third_party"]:
            break
        shown_tp += 1
        lines.append(f"- {item['name']} ({item['file']} p.{item['page']})")
    if not seen:
        lines.append("- none found by the table scan (still read integration sections and diagrams)")
    (rfp_dir / INDEX_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
