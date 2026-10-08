"""SAP module cross-mapping: client module names -> catalogue (LOB, Business Area) filters.

Ported from module_matcher_layer1.py (`parse_cross_mapping_entry`, alias index, exact
match). The LLM fuzzy matcher is gone: the `sap-scope-mapping` skill reads the
generated alias guide and calls `cross_map_lookup` instead.

Mapping-value conventions (from the source workbook):
  `|` sub-filters (LOB|Business Area|Component), `,` separates alternatives,
  "Others" / "?" = an SAP tool or system with no catalogue scope items.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_PAREN_RE = re.compile(r"^(.*?)\s*\(([^)]+)\)\s*$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class LobBaFilter:
    lob: str = ""                  # "" = search every LOB
    business_area: str = ""        # "" = the whole LOB
    description_filter: str = ""   # Description contains ...
    component_filter: str = ""     # Component contains ...


@dataclass
class CrossMapEntry:
    module_name: str
    mapping_type: str
    mapping_value: str
    aliases: list[str] = field(default_factory=list)
    is_others: bool = False
    others_label: str = ""
    filters: list[LobBaFilter] = field(default_factory=list)

    def target_text(self) -> str:
        """Human-readable summary of what this row resolves to."""
        if self.is_others:
            return f"Others ({self.others_label or 'Unclassified'}) - SAP tool/system, no catalogue scope items"
        parts = []
        for f in self.filters:
            seg = f.lob or "(all LOBs)"
            if f.business_area:
                seg += f" | {f.business_area}"
            elif not f.description_filter and not f.component_filter:
                seg += " (whole LOB)"
            if f.description_filter:
                seg += f" [Description contains '{f.description_filter}']"
            if f.component_filter:
                seg += f" [Component contains '{f.component_filter}']"
            parts.append(seg)
        return "; ".join(parts) or "(no target)"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _unwrap(prefix: str, text: str) -> str:
    return text.replace(f"{prefix}(", "", 1).rstrip(")").strip('"').strip("'")


def parse_entry(module_name: str, mapping_type: str, mapping_value: str, aliases: list[str]) -> CrossMapEntry:
    entry = CrossMapEntry(_clean(module_name), _clean(mapping_type), _clean(mapping_value), aliases)
    kind = entry.mapping_type.lower()
    if kind in ("others", "?"):
        entry.is_others = True
        entry.others_label = entry.mapping_value or "Unclassified"
        return entry
    if kind == "description":
        m = re.match(r'^Description\(["\']?(.+?)["\']?\)\s*$', entry.mapping_value)
        entry.filters.append(LobBaFilter(description_filter=m.group(1) if m else entry.mapping_value))
        return entry
    for part in (p.strip() for p in entry.mapping_value.split(",") if p.strip()):
        segments = [s.strip() for s in part.split("|")]
        lob, ba, desc, comp = segments[0], "", "", ""
        for seg in segments[1:3]:
            if seg.startswith("Description("):
                desc = _unwrap("Description", seg)
            elif seg.startswith("Component("):
                comp = _unwrap("Component", seg)
            elif not ba:
                # "Cost Management and Profitability Analysis(CO Modules)" -> drop the annotation
                m = re.match(r"^(.+?)\s*\(.*\)\s*$", seg)
                ba = m.group(1).strip() if m else seg
        if lob:
            entry.filters.append(LobBaFilter(lob, ba, desc, comp))
    return entry


def normalize_module_name(value: str) -> str:
    """Case-fold and strip punctuation so "Production & Planning" == "production-planning"."""
    return _NON_ALNUM_RE.sub(" ", _clean(value).lower()).strip()


def module_name_candidates(entry: CrossMapEntry) -> list[str]:
    """Own name, both halves of "Name (ABBR)", and every alias - normalised."""
    candidates = {normalize_module_name(entry.module_name)}
    m = _PAREN_RE.match(entry.module_name)
    if m:
        candidates.update({normalize_module_name(m.group(1)), normalize_module_name(m.group(2))})
    candidates.update(normalize_module_name(a) for a in entry.aliases)
    candidates.discard("")
    return sorted(candidates)


class CrossMap:
    """The whole rulebook with an exact/alias index."""

    def __init__(self, entries: list[CrossMapEntry]):
        self.entries = entries
        self.by_name = {e.module_name: e for e in entries}
        self._alias_index: dict[str, str] = {}
        for e in entries:
            for candidate in module_name_candidates(e):
                self._alias_index.setdefault(candidate, e.module_name)

    def resolve(self, name: str) -> CrossMapEntry | None:
        """Exact match on name / abbreviation / alias; None when nothing matches exactly."""
        hit = self._alias_index.get(normalize_module_name(name))
        return self.by_name.get(hit) if hit else None

    def suggest(self, name: str, limit: int = 5) -> list[CrossMapEntry]:
        """Token-overlap suggestions for a name with no exact hit (for the agent to judge)."""
        tokens = {t for t in normalize_module_name(name).split() if len(t) > 1}
        if not tokens:
            return []
        scored = []
        for e in self.entries:
            cand = set(" ".join(module_name_candidates(e)).split())
            overlap = len(tokens & cand)
            if overlap:
                scored.append((overlap, e.module_name))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [self.by_name[n] for _, n in scored[:limit]]
