"""Deterministic wave/phase pre-scan of RFP text (pure regex, no LLM).

WHY: RFPs rarely state their delivery waves in one place - the methodology names them, the
payment-milestone table restates them, the table of contents lists them first.  These scans give
the timeline agent (and the ledger's wave-anchor checklist) a list of every wave mention with its
page, so a wave the document plainly names cannot be overlooked.

Ported from services/project_timeline_extraction_layer.py (`scan_declared_waves`,
`find_wave_anchors`, `detect_sequencing` and their regexes), unchanged in what they match.  One
adaptation: the old code read pdfplumber layout text, one visual line per line; pymupdf4llm joins
the visual lines of a paragraph, so the ARASCO RFP's three wave lines arrive as one line
('**Wave 1: FOODS** 3 Month Hyper Care ... **Wave 2 : Corporate + ...** ...').  The line-based
regexes therefore run over *logical lines*: Markdown emphasis removed, '<br>' and sentence ends
treated as breaks, and a break inserted before a mid-line wave heading ('... Wave 2: X').
"""

from __future__ import annotations

import re

_WAVE_TOKEN = r"(?:wave|phase|tranche|release|stage|rollout|roll-out|batch|go-?live)"
_ORDINAL = r"(?:\d{1,2}|[IVX]{1,4}|one|two|three|four|five|six)"

# "Wave 1:", "Phase II -", "Tranche 3 –", "Release 2:", "Wave 3   MEFSCO" ... a wave heading is the
# token plus an ordinal plus a separator or tabular whitespace.
_WAVE_HEADING_RE = re.compile(
    rf"^\W*(?:\|\s*)?{_WAVE_TOKEN}\s*[-#]?\s*(?:\d{{1,2}}|[IVX]{{1,4}}|one|two|three|four|five|six)\b(?:\s*[:.\-–—)]|\s{{2,}}|\s*\|\s*|\s+[A-Za-z0-9])",
    re.IGNORECASE | re.MULTILINE,
)

_DECLARED_WAVE_LINE_RE = re.compile(
    rf"^\W*(?:\|\s*)?({_WAVE_TOKEN}\s*[-#]?\s*(\d{{1,2}}|[IVX]{{1,4}}|one|two|three|four|five|six))\b(?:\s*[:.\-–—)]|\s{{2,}}|\s*\|\s*|\t+)\s*([^\n\r]+)",
    re.IGNORECASE | re.MULTILINE,
)

_ORDINAL_MAP = {
    "1": 1, "one": 1, "i": 1,
    "2": 2, "two": 2, "ii": 2,
    "3": 3, "three": 3, "iii": 3,
    "4": 4, "four": 4, "iv": 4,
    "5": 5, "five": 5, "v": 5,
    "6": 6, "six": 6, "vi": 6,
    "7": 7, "seven": 7, "vii": 7,
    "8": 8, "eight": 8, "viii": 8,
}

# "implemented in three waves", "divided into 3 phases", "two sequential tranches" - the count
# statement, which says how many waves to expect even when the headings sit in an image.
_WAVE_COUNT_RE = re.compile(
    rf"\b(?:in|into|across|over)\s+(\d{{1,2}}|two|three|four|five|six|seven|eight)\s+"
    rf"(?:\w+\s+){{0,2}}{_WAVE_TOKEN}s\b",
    re.IGNORECASE,
)

_SEQUENCING_RE = re.compile(
    r"\b(sequential|sequentially|one after|back[- ]to[- ]back|consecutive|"
    r"in parallel|parallel|simultaneous|simultaneously|concurrent|concurrently|staggered|overlapping)\b",
    re.IGNORECASE,
)

_MARKUP_RE = re.compile(r"\*\*|__|`|</?(?:sup|sub|mark|b|i|u|em|strong)>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_SENTENCE_BREAK_RE = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(])")
_MIDLINE_WAVE_RE = re.compile(rf"(?<=\S)\s+(?={_WAVE_TOKEN}\s*[-#]?\s*{_ORDINAL}\s*[:\-–—])", re.IGNORECASE)
_STAGE_WORDS = ("design", "implementation", "blueprint", "testing", "cutover", "realize", "explore", "prepare")


def clean_markup(text: str) -> str:
    """Markdown emphasis/inline tags removed, '<br>' as a line break."""
    return _MARKUP_RE.sub("", _BR_RE.sub("\n", text or ""))


def logical_lines(text: str) -> list[str]:
    """Physical lines split further at sentence ends and before mid-line wave headings."""
    lines: list[str] = []
    for line in clean_markup(text).splitlines():
        for sentence in _SENTENCE_BREAK_RE.split(line):
            lines.extend(part.strip() for part in _MIDLINE_WAVE_RE.split(sentence))
    return [line for line in lines if line]


def scan_declared_waves(text: str) -> list[dict]:
    """Explicitly declared wave/phase lines ('Wave 2: Corporate + FEED + GTU').

    Returns [{ordinal, label, entities, raw_line}] sorted by ordinal; the first line per ordinal
    wins; trailing durations/hypercare are cut from the entity list."""
    if not text:
        return []
    results = []
    seen_ordinals: set[int] = set()
    for line_clean in logical_lines(text):
        if len(line_clean) > 300:
            continue
        m = _DECLARED_WAVE_LINE_RE.match(line_clean)
        if not m:
            continue
        ord_token = m.group(2).strip().lower()
        seq = _ORDINAL_MAP.get(ord_token)
        if seq is None:
            try:
                seq = int(ord_token)
            except ValueError:
                continue
        if seq in seen_ordinals:
            continue
        seen_ordinals.add(seq)

        payload = m.group(3).strip()
        payload_clean = re.sub(
            r"(?:\(?\s*\b\d+\s*(?:month|week|day|year|yr|mo|m|w)s?\b.*|\bhyper\s*care\b.*)$",
            "", payload, flags=re.IGNORECASE,
        ).strip().rstrip("()| \t-–—").strip()
        parts = [
            p.strip("()[]{} \t-–—")
            for p in re.split(r"\s*(?:\+|\band\b|&|,)\s*", payload_clean)
            if p.strip()
        ]
        entities = [p for p in parts if p and not any(stop in p.lower() for stop in _STAGE_WORDS)]
        results.append({"ordinal": seq, "label": f"Wave {seq}", "entities": entities, "raw_line": line_clean})
    results.sort(key=lambda x: x["ordinal"])
    return results


def find_wave_anchors(text: str, max_anchors: int = 60) -> list[str]:
    """Lines that look like a delivery-wave heading or a wave count, deduplicated, in order."""
    if not text:
        return []
    anchors: list[str] = []
    for stripped in logical_lines(text):
        if len(stripped) > 300:
            continue
        if (_WAVE_HEADING_RE.search(stripped) or _WAVE_COUNT_RE.search(stripped)) and stripped not in anchors:
            anchors.append(stripped)
        if len(anchors) >= max_anchors:
            break
    return anchors


def detect_sequencing(text: str) -> str:
    """'sequential' | 'parallel' | 'staggered' | '' from wording within 160 chars of a wave mention.

    Only wording near a wave token counts, so 'parallel processing' elsewhere cannot flip it."""
    if not text:
        return ""
    text = clean_markup(text)
    votes = {"sequential": 0, "parallel": 0, "staggered": 0}
    for match in re.finditer(rf"{_WAVE_TOKEN}s?\b", text, re.IGNORECASE):
        window = text[max(match.start() - 160, 0):match.end() + 160]
        for word in _SEQUENCING_RE.findall(window):
            word = word.lower()
            if word in ("sequential", "sequentially", "one after", "back-to-back", "back to back", "consecutive"):
                votes["sequential"] += 1
            elif word in ("staggered", "overlapping"):
                votes["staggered"] += 1
            else:
                votes["parallel"] += 1
    best = max(votes, key=lambda k: votes[k])
    return best if votes[best] else ""
