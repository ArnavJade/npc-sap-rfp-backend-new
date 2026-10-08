"""draft_check: a section draft may not type figures or show detail the client did not ask for.

Replaces the old harmonisation number guard. Allowed bare numbers: years, section references,
list numbering, numbers inside a quote that really occurs in the RFP, and the small ledger counts
(waves, countries, weeks...) stored in ledger.figures["counts"]. Everything else must be a
{{fig:...}} / {{table:...}} placeholder the renderer fills from the ledger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bidcore.evidence import CorpusIndex
from bidcore.figures import known_placeholder, withheld_keys

PLACEHOLDER_RE = re.compile(r"\{\{\s*((?:fig|table|diagram):[a-z0-9_:\-]+)\s*\}\}")
QUOTE_RE = re.compile(r"[\"“]([^\"”]{8,400})[\"”]")
NUMBER_RE = re.compile(r"(?<![\w/.\-])(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*%?(?![\w/])")
SECTION_REF_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)+(?![\w])")
LIST_MARKER_RE = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
CURRENCY_RE = re.compile(r"(?:USD|US\$|\$|€|EUR|SAR|INR)\s?\d", re.IGNORECASE)


@dataclass
class DraftReport:
    section_id: str
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    words: int = 0

    @property
    def clean(self) -> bool:
        return not self.problems


def _allowed_numbers(counts: dict) -> set[str]:
    allowed: set[str] = set()
    for value in counts.values():
        for v in (value if isinstance(value, list) else [value]):
            if isinstance(v, (int, float)) and v:
                allowed.add(f"{v:g}")
    return allowed


def check_draft(section_id: str, markdown: str, figures: dict, withheld: list[str],
                corpus: CorpusIndex | None, words: list[int] | None = None) -> DraftReport:
    report = DraftReport(section_id)
    text = markdown or ""
    report.words = len(re.findall(r"\b\w+\b", PLACEHOLDER_RE.sub(" ", text)))

    known_figs = set((figures.get("fig") or {}).keys())
    blocked = withheld_keys(withheld)
    for key in PLACEHOLDER_RE.findall(text):
        kind, _, name = key.partition(":")
        if not known_placeholder(key) or (kind == "fig" and name not in known_figs):
            report.problems.append(f"unknown placeholder {{{{{key}}}}} - use a key from bid_facts('figures')")
        elif key in blocked:
            report.problems.append(f"{{{{{key}}}}} is withheld by the client's disclosure profile - remove it")

    scrubbed = PLACEHOLDER_RE.sub(" ", text)
    for quote in QUOTE_RE.findall(scrubbed):          # numbers inside verified RFP quotes are fine
        if corpus is None or corpus.contains(quote):
            scrubbed = scrubbed.replace(quote, " ")
    scrubbed = SECTION_REF_RE.sub(" ", LIST_MARKER_RE.sub(" ", scrubbed))
    scrubbed = re.sub(r"\b(?:19|20)\d{2}\b", " ", scrubbed)                       # years
    scrubbed = re.sub(r"(?i)\bS/4\s?HANA\b|\bBW/4\s?HANA\b|\bR/3\b|\b[A-Z]{1,3}\d[A-Z0-9]*\b", " ", scrubbed)
    allowed = _allowed_numbers(figures.get("counts") or {})
    if CURRENCY_RE.search(scrubbed):
        report.problems.append("a currency amount is typed in the text - use {{fig:total_project_cost}} or a table")
    bad = sorted({m.group(1) for m in NUMBER_RE.finditer(scrubbed)
                  if m.group(1).replace(",", "") not in allowed and m.group(1) not in ("0", "1")})
    if bad:
        report.problems.append(f"typed figures {bad[:12]} - use {{{{fig:...}}}} placeholders, quote the RFP "
                               "verbatim, or drop the number")
    if words and len(words) == 2:
        low, high = words
        if report.words < low * 0.6:
            report.warnings.append(f"{report.words} words; target {low}-{high}")
        elif report.words > high * 1.5:
            report.warnings.append(f"{report.words} words; target {low}-{high} - tighten")
    if re.match(r"^\s*#\s", text):
        report.warnings.append("do not repeat the section heading - the template has it")
    return report
