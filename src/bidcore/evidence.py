"""Evidence grounding: does a quoted phrase really occur in the RFP?

Ported from data_migration_scope.py (`_clean_text`, `_norm_key`, `CorpusIndex`). A phrase is found
when its alphanumeric-only form occurs in the corpus, or - for labels stitched from a table or
diagram whose extracted text puts other cells between the words - when all its words occur in
order within a short window (3 words per phrase word, + 5). A long quote (8+ words) also passes when
at least 85% of its words occur in that order (one OCR'd or re-hyphenated word must not sink it).

Both sides are normalised the same way first: the markup the ingestion layer leaves in table cells
(`<br>`, `<mark>`, `**`), HTML entities (`&amp;`), words a PDF cell broke with a hyphen
(`Man-<br>agement`) and '&' vs 'and'. The first live run rejected verbatim quotes of table cells
because `<br>` survived as the letters "br" inside the corpus.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]+")
_PAGE_MARKER_RE = re.compile(r"<!--\s*(?:page|slide|block)[^>]*-->", re.IGNORECASE)


_TAG_RE = re.compile(r"</?[a-zA-Z][^>\n]{0,40}>")
_AMP_RE = re.compile(r"\s*&\s*")


def clean_text(value: Any) -> str:
    """Drop markup tags and entities, collapse whitespace, rejoin words a PDF cell broke with a hyphen
    ('Mainte- nance', 'Man-<br>agement') and spell '&' as 'and'."""
    text = html.unescape(_TAG_RE.sub(" ", str(value or "")))
    text = " ".join(text.replace("**", " ").split())
    text = _AMP_RE.sub(" and ", text)
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
        cleaned = clean_text(phrase)
        needle = norm_key(cleaned)
        if not needle:
            return False
        if needle in self.flat:
            return True
        words = _WORD_RE.findall(cleaned.lower())
        if len(words) < 2:
            return False
        span = 3 * len(words) + 5
        if self._in_order(words, span, len(words)):
            return True
        if len(words) >= 8:   # near-verbatim long quote: tolerate a few mangled words
            return self._in_order(words, span, int(len(words) * 0.85 + 0.999))
        return False

    def _in_order(self, words: list[str], span: int, needed: int) -> bool:
        """Do at least `needed` of `words` occur in order within `span` words of an anchor word?
        The anchor is one of the first len(words) - needed + 1 words (earlier ones count as misses)."""
        for anchor_index in range(len(words) - needed + 1):
            for start in self.positions.get(words[anchor_index], ()):
                current, matched = start, 1
                for word in words[anchor_index + 1:]:
                    later = next((p for p in self.positions.get(word, ()) if current < p <= start + span), None)
                    if later is not None:
                        current, matched = later, matched + 1
                if matched >= needed:
                    return True
        return False

    def mentions(self, name: str) -> int:
        """Rough occurrence count of a short name (for recall checks)."""
        needle = norm_key(name)
        return self.flat.count(needle) if needle else 0
