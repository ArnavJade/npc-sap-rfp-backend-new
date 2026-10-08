"""Disclosure filtering for tables whose columns a writer chose (ported from layer5_disclosure.py).

A column whose header belongs to a withheld category is dropped; the first column (the row label)
always stays. Ledger-driven tables apply disclosure in render/docx/tables.py.
"""

from __future__ import annotations

import re

SCOPE_ITEMS, EFFORT, ALLOCATION, LOCATION, COMMERCIAL = (
    "scope_item_detail", "effort_detail", "resource_allocation", "resource_location", "commercial_detail")

# Word boundaries matter: "rate" must not match "Corporate", and "Phase / Wave & Entities" is planning
# structure, not allocation.
_HEADER_CUES = {
    SCOPE_ITEMS: re.compile(r"\bBP\b|\bBP[\s-]?IDs?\b|scope[\s-]?items?", re.IGNORECASE),
    EFFORT: re.compile(r"effort|person[\s-]?days?|man[\s-]?days?|\bPDs?\b|\(PD|\bhours\b|\bestimat", re.IGNORECASE),
    ALLOCATION: re.compile(
        r"\bFTEs?\b|man[\s-]?months?|person[\s-]?months?|headcount|resource\s+(model|loading|allocation)|"
        r"allocation|^\s*M\d+\s*$|^\s*month\s*\d+\s*$|^\s*wave\s*\d+\s*$", re.IGNORECASE),
    LOCATION: re.compile(r"on[\s-]?site|off[\s-]?site|off[\s-]?shore|on[\s-]?shore|near[\s-]?shore|\blocation\b",
                         re.IGNORECASE),
    COMMERCIAL: re.compile(r"\bcosts?\b|\bprices?\b|pricing|\brates?\b|\bUSD\b|\bEUR\b|\$|\bfees?\b|commercial|"
                           r"\bamount\b|budget|\bquot", re.IGNORECASE),
}


def header_categories(header: str) -> set[str]:
    return {category for category, cue in _HEADER_CUES.items() if cue.search(header or "")}


def filter_table_columns(headers: list[str], rows: list[list[str]], withheld: list[str] | set[str],
                         keep_first: bool = True) -> tuple[list[str], list[list[str]], list[str]]:
    """(headers, rows, dropped headers) with withheld-category columns removed."""
    withheld = set(withheld)
    if not withheld or not headers:
        return headers, rows, []
    keep = [i for i, h in enumerate(headers) if (keep_first and i == 0) or not (header_categories(str(h)) & withheld)]
    if len(keep) == len(headers):
        return headers, rows, []
    dropped = [str(headers[i]) for i in range(len(headers)) if i not in keep]
    return [headers[i] for i in keep], [[r[i] if i < len(r) else "" for i in keep] for r in rows], dropped
