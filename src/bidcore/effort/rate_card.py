"""Best Practice rate card: person-days per scope item, per country key (policy/rate_cards/bp_efforts.parquet).

Ported from effort_calculator_layer4.EffortIndex. The card prices a scope item per Country/Region Key,
but a bid country rarely has its own row (today every row is keyed 'US'), so a lookup falls back in a
fixed order - exact country row -> global (blank key) row -> any other country's row - and a borrowed
row is relabelled to the requested country so N fanned-out lines never read as copies of one source row.

The total of a row is the sum of all FIVE phases. The source sheet's own Total formula omitted UAT;
the old agent summed all five and so do we (EffortRow.compute_total).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import pandas as pd

from bidcore.effort.models import PHASE_FIELDS
from bidcore.paths import rate_card_path

logger = logging.getLogger(__name__)
_WARNED: set[tuple[str, str, str]] = set()

EXACT, GLOBAL, BORROWED = "exact", "global", "borrowed"


@dataclass(frozen=True)
class RateCardRow:
    """One rate-card line. `match` says how a lookup found it (exact | global | borrowed)."""
    sheet: str
    lob: str
    business_area: str
    country_key: str                  # "" = global row
    scope_id: str
    description: str
    complexity: str
    comments: str
    workshops_configuration: float
    unit_testing: float
    integration_testing: float
    documentation_training: float
    user_acceptance_testing: float
    has_effort: bool
    match: str = EXACT

    @property
    def total(self) -> float:
        return round(sum(getattr(self, f) for f in PHASE_FIELDS), 2)

    def phases(self) -> dict[str, float]:
        return {f: getattr(self, f) for f in PHASE_FIELDS}


def _text(value) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()


def _number(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if number != number else number      # NaN -> 0


@lru_cache(maxsize=4)
def _read(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


@lru_cache(maxsize=8)
def _index(path: str, sheet: str) -> dict[str, dict[str, RateCardRow]]:
    """scope_id -> {country_key: row}, in file order. A repeated (scope_id, country) key keeps the
    LAST row (EffortIndex: 'last write wins'), at the position of its first occurrence."""
    frame = _read(path)
    sheets = sorted(frame["sheet"].dropna().unique().tolist())
    if sheet not in sheets:
        raise ValueError(f"rate card sheet '{sheet}' not found in {path}; available sheets: {sheets}")
    index: dict[str, dict[str, RateCardRow]] = {}
    duplicates = 0
    for rec in frame[frame["sheet"] == sheet].to_dict("records"):
        scope_id = _text(rec.get("scope_id"))
        if not scope_id:
            continue
        country = _text(rec.get("country_key")).upper()
        bucket = index.setdefault(scope_id, {})
        duplicates += country in bucket
        bucket[country] = RateCardRow(
            sheet=sheet, lob=_text(rec.get("lob")), business_area=_text(rec.get("business_area")),
            country_key=country, scope_id=scope_id, description=_text(rec.get("description")),
            complexity=_text(rec.get("complexity")), comments=_text(rec.get("comments")),
            **{f: _number(rec.get(f)) for f in PHASE_FIELDS},
            has_effort=bool(rec.get("has_effort", True)),
        )
    if duplicates:
        logger.info("rate card %s: %d repeated (scope_id, country) rows; the last one wins", sheet, duplicates)
    return index


class RateCard:
    """Lookups on one rate-card sheet ('SAP BP' | 'YASH BP'); the parsed sheet is cached per process."""

    def __init__(self, sheet: str, path: Path | None = None):
        self.sheet = sheet
        self.path = Path(path) if path else rate_card_path()
        self._rows = _index(str(self.path.resolve()), sheet)

    def __contains__(self, scope_id: str) -> bool:
        return str(scope_id or "").strip() in self._rows

    def __len__(self) -> int:
        return len(self._rows)

    def countries(self, scope_id: str) -> list[str]:
        """Country keys the card prices this scope item for ('' = global)."""
        return list(self._rows.get(str(scope_id or "").strip(), {}))

    def get(self, scope_id: str, country: str | None = None) -> RateCardRow | None:
        """The row pricing `scope_id` for `country`, or None when the card has no row for it at all.

        Order: exact (scope, country) row -> global row -> any other country's row (the first the card
        lists), relabelled to `country` and logged, since its figures were set for another country.
        Without a country the global row is tried first, then the first other row (not relabelled).
        """
        scope_id = str(scope_id or "").strip()
        bucket = self._rows.get(scope_id)
        if not bucket:
            return None
        country = str(country or "").strip().upper()
        if country and country in bucket:
            return bucket[country]
        if "" in bucket:
            return replace(bucket[""], match=GLOBAL)
        source = next(iter(bucket.values()))
        if (self.sheet, scope_id, country) not in _WARNED:     # once per process, not once per sizing pass
            _WARNED.add((self.sheet, scope_id, country))
            if country:
                logger.warning("rate card %s: no row for %s in %s; using its %s figures (labelled %s)",
                               self.sheet, scope_id, country, source.country_key, country)
            else:
                logger.debug("rate card %s: %s has no global row; using its %s row",
                             self.sheet, scope_id, source.country_key)
        return replace(source, country_key=country or source.country_key, match=BORROWED)
