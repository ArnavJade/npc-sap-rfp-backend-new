"""Tables: pipe-table rendering/parsing and the deterministic third-party system scan.

WHY: RFP scope lives in tables (module matrices, system landscapes, interface lists).  Every
format therefore renders a table the same way - a GitHub pipe table inside an
`[EXTRACTED TABLE -- p.N]` block - and everything downstream (the index's table list, the
third-party scan) re-reads tables from that one representation, whichever engine produced them.

`table_to_markdown` is ported from aperture/table_formatter.py with one fix: cell text is escaped
('|' -> '\\|', line breaks -> '<br>', the convention pymupdf4llm also uses), so a cell can no
longer break its row; rows longer than the header are no longer cut.

`scan_for_third_party` ports the deterministic scanner of aperture/third_party_table_scanner.py
(header detection, column selection, multi-name cell splitting) and returns {name, evidence}
dicts.  Two adaptations for pymupdf4llm output, both seen on the ARASCO RFP: a caption that the
PDF engine split across cells mid-word is not taken for the header, and a headerless table that
continues a named-system table on the next page can be scanned with that table's header
(`header=`).  No LLM anywhere: the scan exists to raise recall and as a hook-side recall check.
"""

from __future__ import annotations

import re
from typing import Any

from .models import BLOCK_CHARS, TABLE_BLOCK_RE, table_block

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_INLINE_MARKUP_RE = re.compile(r"\*\*|__|</?(?:sup|sub|mark|b|i|u|em|strong)>", re.IGNORECASE)
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")


# ---------------------------------------------------------------------------
# Rendering and parsing
# ---------------------------------------------------------------------------

def escape_cell(value: Any) -> str:
    """One cell as pipe-table text: whitespace collapsed per line, line breaks as '<br>'."""
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\v", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "<br>".join(line for line in lines if line).replace("|", "\\|")


def table_to_markdown(rows: list[list[Any]]) -> str:
    """Rows -> GitHub pipe table; the first row is the header.  Cells are laid out, never edited."""
    if not rows:
        return ""
    width = max(len(row) for row in rows) or 1
    lines = []
    for index, row in enumerate(rows):
        cells = ([escape_cell(cell) for cell in row] + [""] * width)[:width]
        lines.append("| " + " | ".join(cells) + " |")
        if index == 0:
            lines.append("| " + " | ".join(["---"] * width) + " |")
    return "\n".join(lines)


def is_meaningful_table(rows: list[list[Any]] | None) -> bool:
    """A header plus at least one row, with some text somewhere (ported guard)."""
    if not rows or len(rows) < 2:
        return False
    return any(str(cell).strip() for row in rows for cell in row if cell is not None)


def chunk_rows(rows: list[list[Any]], max_chars: int = BLOCK_CHARS) -> list[list[list[Any]]]:
    """Split a long table into row groups of roughly `max_chars`, each repeating the header row.

    Char-based successor of aperture's `chunk_large_table`: it keeps every synthetic page small
    enough for one read_section call.  A group always carries at least one data row."""
    if len(rows) <= 2:
        return [rows]
    header, body = rows[0], rows[1:]

    def size(row: list[Any]) -> int:
        return sum(len(escape_cell(cell)) + 3 for cell in row) + 2

    base = 2 * size(header)
    groups: list[list[list[Any]]] = []
    current: list[list[Any]] = []
    used = base
    for row in body:
        if current and used + size(row) > max_chars:
            groups.append([header, *current])
            current, used = [], base
        current.append(row)
        used += size(row)
    if current:
        groups.append([header, *current])
    return groups


def split_pipe_row(line: str) -> list[str]:
    """'| a | b\\|c |' -> ['a', 'b\\|c'] (cells stay escaped; see clean_cell)."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    return [cell.strip() for cell in _CELL_SPLIT_RE.split(text)]


def _is_separator(line: str) -> bool:
    cells = [cell.replace(" ", "") for cell in split_pipe_row(line)]
    return any(cells) and all(_SEPARATOR_CELL_RE.match(cell) for cell in cells if cell)


def clean_cell(cell: str) -> str:
    """Escaped pipe-table cell -> plain text ('<br>' back to newlines, emphasis/sup tags removed)."""
    text = _INLINE_MARKUP_RE.sub("", _BR_RE.sub("\n", cell)).replace("\\|", "|")
    return "\n".join(" ".join(line.split()) for line in text.split("\n")).strip()


def wrap_pipe_tables(text: str, page: int) -> str:
    """Wrap every pipe table found in engine Markdown into an [EXTRACTED TABLE -- p.N] block."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("|"):
            out.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            j += 1
        run = [line.strip() for line in lines[i:j]]
        if len(run) >= 2 and any(_is_separator(line) for line in run[1:3]):
            out.extend(["", table_block(page, "\n".join(run)), ""])
        else:
            out.extend(run)
        i = j
    return "\n".join(out)


def table_blocks(text: str) -> list[tuple[str, list[list[str]]]]:
    """(location, clean rows) of every [EXTRACTED TABLE] block in `text`, in order."""
    found = []
    for match in TABLE_BLOCK_RE.finditer(text):
        rows = [
            [clean_cell(cell) for cell in split_pipe_row(line)]
            for line in match.group("body").split("\n")
            if line.strip().startswith("|") and not _is_separator(line)
        ]
        found.append((match.group("where"), rows))
    return found


# ---------------------------------------------------------------------------
# Third-party system scan (ported from aperture/third_party_table_scanner.py)
# ---------------------------------------------------------------------------

# A table is scanned only when one of these phrases occurs anywhere in it.  A bare "interface"
# was removed upstream (it matched capability tables); "interfac* with" replaces it.
_TABLE_SIGNAL_KEYWORDS = (
    "3rd party", "third party", "third-party", "non-sap", "non sap",
    "external system", "legacy system",
)
_INTERFACE_PHRASE_RE = re.compile(r"interfac\w*\s+with", re.IGNORECASE)
# Header keywords of commentary/metadata columns - never scanned for names.
_NON_NAME_COLUMN_KEYWORDS = (
    "description", "detail", "remark", "note", "function", "plan",
    "communication channel", "area", "service", "type", "category",
    "status", "phase", "date", "owner", "priority",
    "sap module", "bp id",
)
# Header keywords of high-confidence name columns - always scanned.
_POSITIVE_NAME_COLUMN_KEYWORDS = (
    "application", "solution", "tool", "3rd party", "third party",
    "third-party", "non-sap", "vendor", "product",
)
# A cell reads as an enumerated list when it has one of these (a bare newline is a visual wrap).
_LIST_SEPARATOR_RE = re.compile(r",|\band\b|&|\s/\s", re.IGNORECASE)
# Split a multi-name cell on the same separators, but never inside "(...)".
_MULTI_NAME_SPLIT_RE = re.compile(r"(?:,|\band\b|&|\s/\s)(?![^()]*\))", re.IGNORECASE)
_MIN_NAME_LENGTH = 2
_MAX_NAME_WORDS = 6
_NOISE_TOKENS = frozenset({"etc", "etc.", "-", "n/a", "na", "none", "tbd", "x", "o"})
_MAX_SHORT_FRAGMENT_WORDS = 2
_SENTENCE_END_RE = re.compile(r"[.!?]\s*$")
_MIN_NON_EMPTY_CELL_FRACTION = 0.34
_MAX_HEADER_CELL_WORDS = 12
_MAX_HEADER_SEARCH_ROWS = 3
_MIN_TABLE_COLUMNS = 2
_WHITESPACE_RE = re.compile(r"\s+")


def _clean(value: Any) -> str:
    return (str(value) if value is not None else "").strip()


def _norm_header(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", _clean(value)).lower()


def _row_has_enough_content(row: list[str], num_columns: int) -> bool:
    if num_columns <= 0:
        return False
    return sum(1 for cell in row if _clean(cell)) / num_columns >= _MIN_NON_EMPTY_CELL_FRACTION


def _is_split_caption_row(row: list[str]) -> bool:
    """A caption the PDF engine cut into cells mid-word ('Scope of integra' | 'tion of ...')."""
    cells = [_clean(cell) for cell in row if _clean(cell)]
    joins = sum(1 for a, b in zip(cells, cells[1:]) if a[-1].islower() and b[0].islower())
    return joins >= 2


def _looks_like_a_header_row(row: list[str], num_columns: int) -> bool:
    if not _row_has_enough_content(row, num_columns):
        return False
    for cell in row:
        words = _clean(cell).split()
        if len(words) > _MAX_HEADER_CELL_WORDS:
            return False
        if len(words) > _MAX_SHORT_FRAGMENT_WORDS and _SENTENCE_END_RE.search(_clean(cell)):
            return False
    return True


def _find_header_row_index(rows: list[list[str]], num_columns: int) -> int | None:
    """First header-looking row; sparse rows and split captions are skipped for free."""
    dense_rows_checked = 0
    for index, row in enumerate(rows):
        if not _row_has_enough_content(row, num_columns) or _is_split_caption_row(row):
            continue
        if _looks_like_a_header_row(row, num_columns):
            return index
        dense_rows_checked += 1
        if dense_rows_checked >= _MAX_HEADER_SEARCH_ROWS:
            return None
    return None


def _is_named_system_table(rows: list[list[str]]) -> bool:
    text = " | ".join(_clean(cell) for row in rows for cell in row).lower()
    return any(k in text for k in _TABLE_SIGNAL_KEYWORDS) or bool(_INTERFACE_PHRASE_RE.search(text))


def _scannable_column_indices(header: list[str], data_rows: list[list[str]]) -> list[int]:
    """Commentary header -> skip; name header -> scan; ambiguous -> scan if >= half list-like."""
    columns: list[int] = []
    for i, col in enumerate(_norm_header(cell) for cell in header):
        if any(bad in col for bad in _NON_NAME_COLUMN_KEYWORDS):
            continue
        if any(good in col for good in _POSITIVE_NAME_COLUMN_KEYWORDS):
            columns.append(i)
            continue
        values = [_clean(row[i]) for row in data_rows if i < len(row) and _clean(row[i])]
        if values and sum(1 for v in values if _LIST_SEPARATOR_RE.search(v)) >= len(values) / 2:
            columns.append(i)
    return columns


def _split_cell_into_names(cell_text: str) -> list[str]:
    names = []
    for candidate in _MULTI_NAME_SPLIT_RE.split(cell_text):
        name = _WHITESPACE_RE.sub(" ", _clean(candidate))
        words = name.split()
        if len(name) < _MIN_NAME_LENGTH or name.lower() in _NOISE_TOKENS or len(words) > _MAX_NAME_WORDS:
            continue
        if len(words) > _MAX_SHORT_FRAGMENT_WORDS and _SENTENCE_END_RE.search(name):
            continue
        names.append(name)
    return names


def _row_evidence(header: list[str], row: list[str]) -> str:
    parts = [f"{_norm_cell(h)}: {_norm_cell(c)}" for h, c in zip(header, row) if _clean(c)]
    return " | ".join(parts)[:200]


def _norm_cell(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", _clean(value))


def third_party_header(rows: list[list[str]] | None) -> list[str] | None:
    """The header row of a named-system table (used to scan its next-page continuation)."""
    if not rows or len(rows) < 2 or not _is_named_system_table(rows):
        return None
    num_columns = max(len(row) for row in rows)
    if num_columns < _MIN_TABLE_COLUMNS:
        return None
    index = _find_header_row_index(rows, num_columns)
    return list(rows[index]) if index is not None else None


def scan_for_third_party(rows: list[list[str]] | None, *, header: list[str] | None = None) -> list[dict[str, str]]:
    """One parsed table -> [{name, evidence}] of named third-party systems; [] if not such a table.

    `header` marks the table as the continuation of a named-system table and supplies its header
    row.  A table with no header row contributes nothing (upstream decision: guessing from cell
    shape alone emitted process labels as fake system names).  Never raises."""
    try:
        if header is not None:
            rows = [list(header), *(rows or [])]
        if not rows or len(rows) < 2:
            return []
        if header is None and not _is_named_system_table(rows):
            return []
        num_columns = max(len(row) for row in rows)
        if num_columns < _MIN_TABLE_COLUMNS:
            return []
        header_index = _find_header_row_index(rows, num_columns)
        if header_index is None:
            return []
        head = rows[header_index]
        data_rows = [row for row in rows[header_index + 1:] if _row_has_enough_content(row, num_columns)]
        columns = _scannable_column_indices(head, data_rows) if data_rows else []
        found: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in data_rows:
            evidence = _row_evidence(head, row)
            for col in columns:
                for name in _split_cell_into_names(row[col]) if col < len(row) else []:
                    if name.lower() not in seen:
                        seen.add(name.lower())
                        found.append({"name": name, "evidence": evidence})
        return found
    except Exception:  # a malformed table contributes nothing rather than aborting ingestion
        return []
