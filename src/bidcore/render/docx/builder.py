"""Assemble the YASH response .docx: template cover + TOC, then every outline section in order.

For each section of `merged_outline(ledger)` (standard outline + client-required sections after their
anchors): the heading (template Heading 1/2 are auto-numbered, so no number is typed), the writer's
Markdown draft converted to Word, then the section's artifact (ledger table or diagram) unless the
draft already placed it. Placeholders are resolved here, never by a model:

  {{fig:<key>}}      -> the figure text from the sizing result (ledger.figures shape)
  {{table:<key>}}    -> a table built from the ledger + sizing   (tables.py)
  {{diagram:<key>}}  -> a PNG drawn from the sizing result       (diagrams.py)

Disclosure: a placeholder the client's disclosure profile withholds is never rendered - a withheld
figure reads 'available on request', a withheld table or diagram is dropped. Cover tokens
{{CLIENT_NAME}}, {{DATE}}, {{YEAR}} are replaced everywhere (text boxes and TOC included) and Word is
told to refresh the TOC when the file is opened (updateFields).
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor, Twips

from bidcore.drafts import PLACEHOLDER_RE
from bidcore.figures import compute_figures, withheld_keys
from bidcore.ledger.models import Ledger
from bidcore.outline import OutlineSection, merged_outline
from bidcore.paths import assets_dir, templates_dir
from bidcore.policy import Policy, get_policy
from bidcore.render.docx.diagrams import draw
from bidcore.render.docx.tables import TableData, build_table
from bidcore.sizing import SizingResult

log = logging.getLogger(__name__)

TEMPLATE_NAME = "YASH_RFP_Template.docx"
WITHHELD_FIGURE_TEXT = "available on request"
MISSING_DRAFT_TEXT = "[Draft missing - presales to complete this section before submission.]"
_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*|_[^_\s][^_]*_|`[^`]+`)")
_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HEADING_HANGING = {1: 432, 2: 576}      # twips: numbered heading levels (Heading 3+ are not numbered)
_BLOCK_ONLY_RE = re.compile(r"^\s*\{\{\s*((?:table|diagram):[a-z0-9_:\-]+)\s*\}\}\s*$")


def template_path() -> Path:
    for candidate in (templates_dir() / TEMPLATE_NAME, assets_dir() / "source" / TEMPLATE_NAME):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{TEMPLATE_NAME} not found under assets/templates or assets/source")


class _Writer:
    def __init__(self, doc, ledger: Ledger, sizing: SizingResult, figures: dict, withheld: list[str]):
        self.doc, self.ledger, self.sizing = doc, ledger, sizing
        self.fig = figures.get("fig", {})
        self.withheld = withheld
        self.blocked = withheld_keys(withheld)
        self.placed: set[str] = set()
        self.dropped: list[str] = []

    # ---------------------------------------------------------------- styles
    def _style(self, name: str, fallback: str = "Normal") -> str:
        try:
            self.doc.styles[name]
            return name
        except KeyError:
            return fallback

    # ---------------------------------------------------------------- placeholders
    def resolve_figures(self, text: str) -> str:
        def sub(match: re.Match) -> str:
            key = match.group(1)
            kind, _, name = key.partition(":")
            if kind != "fig":
                return match.group(0)
            if key in self.blocked:
                self.dropped.append(key)
                return WITHHELD_FIGURE_TEXT
            value = self.fig.get(name)
            if value is None:
                log.warning("unknown figure placeholder %s", key)
                return ""
            return str(value)
        return PLACEHOLDER_RE.sub(sub, text)

    def artifact(self, key: str) -> None:
        if key in self.placed:
            return
        if key in self.blocked:
            self.dropped.append(key)
            return
        kind, _, name = key.partition(":")
        if kind == "table":
            data = build_table(name, self.ledger, self.sizing, self.withheld)
            if data is not None and data.rows:
                self.table(data)
                self.placed.add(key)
        elif kind == "diagram":
            png = draw(name, self.ledger, self.sizing)
            if png:
                self.doc.add_picture(io.BytesIO(png), width=Inches(6.3))
                self.placed.add(key)

    # ---------------------------------------------------------------- blocks
    def heading(self, text: str, level: int) -> None:
        level = min(max(level, 1), 6)
        para = self.doc.add_paragraph(text, style=self._style(f"Heading {level}"))
        # The template's heading numbering carries stray indents (Heading 2: 10216 twips); a paragraph
        # indent wins over the numbering's, so pin number + hanging text to the margin.
        hanging = HEADING_HANGING.get(level, 0)
        para.paragraph_format.left_indent = Twips(hanging)
        para.paragraph_format.first_line_indent = Twips(-hanging)

    def paragraph(self, text: str, style: str = "Normal") -> None:
        text = self.resolve_figures(text)
        inline = [m.group(1) for m in PLACEHOLDER_RE.finditer(text)]
        text = PLACEHOLDER_RE.sub("", text).strip()
        if text:
            para = self.doc.add_paragraph(style=self._style(style))
            self._runs(para, text)
        for key in inline:                          # a table/diagram named mid-sentence goes after it
            self.artifact(key)

    def _runs(self, para, text: str) -> None:
        for part in _INLINE_RE.split(text):
            if not part:
                continue
            if part.startswith(("**", "__")) and part.endswith(("**", "__")) and len(part) > 4:
                para.add_run(part[2:-2]).bold = True
            elif part.startswith(("*", "_")) and part.endswith(("*", "_")) and len(part) > 2:
                para.add_run(part[1:-1]).italic = True
            elif part.startswith("`") and part.endswith("`"):
                para.add_run(part[1:-1])
            else:
                para.add_run(part)

    def table(self, data: TableData) -> None:
        caption = self.doc.add_paragraph(style=self._style("Caption"))
        caption.add_run(data.title).bold = True
        table = self.doc.add_table(rows=1, cols=len(data.headers))
        if self._style("Table Grid", ""):
            table.style = "Table Grid"
        for cell, text in zip(table.rows[0].cells, data.headers):
            cell.text = ""
            run = cell.paragraphs[0].add_run(text)
            run.bold, run.font.size, run.font.color.rgb = True, Pt(9), RGBColor(0xFF, 0xFF, 0xFF)
            _shade(cell, "1F4E78")
        for i, row in enumerate(data.rows):
            cells = table.add_row().cells
            last = data.total_row and i == len(data.rows) - 1
            for cell, text in zip(cells, row):
                cell.text = ""
                run = cell.paragraphs[0].add_run(str(text))
                run.font.size = Pt(9)
                if last:
                    run.bold = True
                    _shade(cell, "D9E1F2")
        _repeat_header(table)
        if data.widths and len(data.widths) == len(data.headers):
            total = sum(data.widths)
            for row in table.rows:
                for cell, w in zip(row.cells, data.widths):
                    cell.width = Inches(6.5 * w / total)
        self.doc.add_paragraph()

    def markdown(self, text: str, level: int) -> None:
        lines = text.replace("\r\n", "\n").split("\n")
        i = 0
        para: list[str] = []

        def flush() -> None:
            if para:
                self.paragraph(" ".join(s.strip() for s in para))
                para.clear()

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                flush()
                i += 1
                continue
            block = _BLOCK_ONLY_RE.match(stripped)
            if block:
                flush()
                self.artifact(block.group(1))
                i += 1
                continue
            if stripped.startswith("|"):
                flush()
                rows = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                        rows.append([self.resolve_figures(c) for c in cells])
                    i += 1
                if len(rows) >= 2:
                    self.table(TableData("", rows[0], rows[1:]))
                continue
            heading = _HEADING_RE.match(stripped)
            if heading:
                flush()
                self.heading(heading.group(2).strip(), min(level + 1, 4))
                i += 1
                continue
            if _BULLET_RE.match(line):
                flush()
                self.paragraph(_BULLET_RE.sub("", line), "List Bullet")
                i += 1
                continue
            if _ORDERED_RE.match(line):
                flush()
                self.paragraph(_ORDERED_RE.sub("", line), "List Number")
                i += 1
                continue
            if stripped.startswith(">"):
                flush()
                self.paragraph(stripped.lstrip("> ").strip(), "Intense Quote")
                i += 1
                continue
            para.append(stripped)
            i += 1
        flush()


def _shade(cell, hex_colour: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), hex_colour)
    tc_pr.append(shading)


def _repeat_header(table) -> None:
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def _replace_tokens(doc, tokens: dict[str, str]) -> None:
    """Replace cover tokens in every text node: body (text boxes, TOC), headers and footers."""
    parts = [doc.element]
    for section in doc.sections:
        for hf in (section.header, section.footer, section.first_page_header, section.first_page_footer):
            parts.append(hf._element)
    for root in parts:
        for node in root.iter(qn("w:t")):
            if node.text and "{{" in node.text:
                for token, value in tokens.items():
                    node.text = node.text.replace(token, value)


def _update_fields_on_open(doc) -> None:
    settings = doc.settings.element
    existing = settings.find(qn("w:updateFields"))
    if existing is None:
        existing = OxmlElement("w:updateFields")
        settings.append(existing)
    existing.set(qn("w:val"), "true")


def _draft(drafts_dir: Path, section_id: str) -> str | None:
    path = drafts_dir / f"{section_id}.md"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def render_proposal(ledger: Ledger, sizing: SizingResult, drafts_dir: Path, out: Path,
                    policy: Policy | None = None) -> Path:
    """Write the response .docx to `out` and return it."""
    policy = policy or get_policy()
    doc = Document(str(template_path()))
    now = datetime.now()
    client = ledger.meta.client_name or "Client"
    _replace_tokens(doc, {"{{CLIENT_NAME}}": client, "{{DATE}}": now.strftime("%d %B %Y"), "{{YEAR}}": str(now.year)})
    _update_fields_on_open(doc)
    for para in doc.paragraphs:     # empty heading paragraphs anchoring the cover would advance the numbering
        if para.style.name.startswith("Heading") and not para.text.strip():
            para.style = doc.styles["Normal"]

    figures = ledger.figures if ledger.figures.get("fig") else compute_figures(ledger, sizing)
    rr = ledger.response_requirements.data
    withheld = rr.disclosure.withheld if rr else []
    writer = _Writer(doc, ledger, sizing, figures, withheld)

    sections: list[OutlineSection] = merged_outline(ledger)
    for section in sections:
        # Heading 3 is not auto-numbered in the template: client-required subsections carry their id.
        title = f"{section.id} {section.title}" if section.client_required else section.title
        writer.heading(title, section.level)
        text = _draft(drafts_dir, section.id) if section.narrative else None
        if text is not None:
            writer.markdown(text.strip(), section.level)
        elif section.narrative:
            para = doc.add_paragraph()
            run = para.add_run(MISSING_DRAFT_TEXT)
            run.italic, run.font.color.rgb = True, RGBColor(0xC0, 0x00, 0x00)
        if section.artifact:
            writer.artifact(section.artifact)
    if writer.dropped:
        log.info("disclosure withheld: %s", sorted(set(writer.dropped)))
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out
