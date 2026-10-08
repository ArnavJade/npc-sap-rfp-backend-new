"""Evidence grounding: does a quoted phrase really occur in the RFP?

Ported from data_migration_scope.py (`_clean_text`, `_norm_key`, `CorpusIndex`). A phrase is found
when its alphanumeric-only form occurs in the corpus, or - for labels stitched from a table or
diagram whose extracted text puts other cells between the words - when all its words occur in
order within a short window (3 words per phrase word, + 5).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]+")
_PAGE_MARKER_RE = re.compile(r"<!--\s*(?:page|slide|block)[^>]*-->", re.IGNORECASE)


def clean_text(value: Any) -> str:
    """Collapse whitespace and rejoin words a PDF cell broke with a hyphen ('Mainte- nance')."""
    text = " ".join(str(value or "").split())
    return re.sub(r"(?<=[a-z])- (?=[a-z])", "", text)


def norm_key(value: Any) -> str:
    """Alphanumeric-only lower-case form, used for dedup and grounding."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


class CorpusIndex:
    def __init__(self, text: str):
        text = _PAGE_MARKER_RE.sub(" ", clean_text(text))
        self.flat = norm_key(text)
        self.positions: dict[str, list[int]] = {}
        for index, word in enumerate(_WORD_RE.findall(text.lower())):
            self.positions.setdefault(word, []).append(index)

    @classmethod
    def from_dir(cls, rfp_dir: Path) -> "CorpusIndex":
        parts = [p.read_text(encoding="utf-8", errors="replace")
                 for p in sorted(rfp_dir.glob("*.md")) if p.name != "index.md"]
        return cls("\n".join(parts))

    def contains(self, phrase: str) -> bool:
        needle = norm_key(clean_text(phrase))
        if not needle:
            return False
        if needle in self.flat:
            return True
        words = _WORD_RE.findall(str(phrase).lower())
        if len(words) < 2:
            return False
        span = 3 * len(words) + 5
        for start in self.positions.get(words[0], ()):
            current = start
            for word in words[1:]:
                later = [p for p in self.positions.get(word, ()) if current < p <= start + span]
                if not later:
                    break
                current = later[0]
            else:
                return True
        return False

    def mentions(self, name: str) -> int:
        """Rough occurrence count of a short name (for recall checks)."""
        needle = norm_key(name)
        return self.flat.count(needle) if needle else 0
