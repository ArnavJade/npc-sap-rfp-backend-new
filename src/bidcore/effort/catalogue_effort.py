"""Catalogue (Best Practice) effort: one EffortRow per scope item per delivery country, priced off the rate card.

Ported from effort_calculator_layer4.calculate_module_effort. Rolling the same scope item out to
several countries is separate configuration and testing in each, so a multi-country bid gets one line
per country the item is delivered in; a single-country bid (or an item with no country list) gets one
line. Nothing is dropped silently:
  * an item the rate card does not price keeps its place as a zero-effort line (policy comment) and is
    listed in ModuleEffort.unmatched_scope_ids;
  * a rate-card row that exists but carries 0 effort is kept as it is (0 totals), as the old agent did;
  * an item the client already runs unchanged ('excluded_existing') is not costed at all and is only
    recorded in ModuleEffort.excluded_scope_ids.
Line ids are stable across calls ('<scope_items row_id>@<country|ALL>'), which is what lets reviewer
edits (factors, wave tags) read back from the workbook find their line again.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping

from bidcore.effort.models import PHASE_FIELDS, EffortRow, ModuleEffort
from bidcore.effort.rate_card import RateCard
from bidcore.ledger.sections_effort import ItemTag, ScopeItem
from bidcore.policy import Policy, get_policy

logger = logging.getLogger(__name__)

EXCLUDED_STATUS = "excluded_existing"


def _codes(values: Iterable[str]) -> list[str]:
    """Distinct upper-cased ISO codes, first occurrence first."""
    out: list[str] = []
    for value in values or ():
        code = str(value or "").strip().upper()
        if code and code not in out:
            out.append(code)
    return out


def line_countries(item: ScopeItem, bid_countries: Iterable[str], policy: Policy | None = None) -> list[str]:
    """Countries the item gets one effort line for; [''] = a single line for the whole bid.

    Fan-out needs a multi-country bid, a per-item country list and the policy switch; otherwise the
    single line carries the bid's only country, or '' when the bid has several (or none).
    """
    p = policy or get_policy()
    bid = _codes(bid_countries)
    applicable = sorted(_codes(item.countries))
    if p.effort.rate_card.per_country_fan_out and len(bid) >= 2 and applicable:
        return applicable
    return [bid[0]] if len(bid) == 1 else [""]


def line_row_id(item: ScopeItem, country: str) -> str:
    return f"{item.row_id or item.scope_item_id.strip()}@{country or 'ALL'}"


def wave_tags_from_item_tags(scope_items: Iterable[ScopeItem], bid_countries: Iterable[str],
                             item_tags: Iterable[ItemTag], policy: Policy | None = None) -> dict[str, str]:
    """EffortRow.row_id -> wave for the wave-planner's item tags.

    A tag without a country covers every line of its item; a tag naming a country covers only that
    country's line and wins over a whole-item tag. A tag that matches no line is logged and skipped.
    """
    bid = list(bid_countries)
    items = {item.row_id: item for item in scope_items}
    tags: dict[str, str] = {}
    for tag in sorted(item_tags, key=lambda t: bool(t.country.strip())):   # whole-item tags first
        item, wave, want = items.get(tag.row_id), tag.wave.strip(), tag.country.strip().upper()
        if item is None or not wave:
            logger.warning("wave tag %s -> %r matches no scope item; skipped", tag.row_id, tag.wave)
            continue
        hits = [c for c in line_countries(item, bid, policy) if not want or c == want]
        if not hits:
            logger.warning("wave tag %s@%s -> %s matches no effort line; skipped", tag.row_id, want, wave)
        for country in hits:
            tags[line_row_id(item, country)] = wave
    return tags


def _factor(value: object, row_id: str) -> float:
    try:
        factor = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"multiplication factor for {row_id} is not a number: {value!r}") from None
    if factor != factor or factor < 0:
        raise ValueError(f"multiplication factor for {row_id} must be >= 0, got {value!r}")
    return factor


def compute_catalogue_effort(
    scope_items: Iterable[ScopeItem],
    bid_countries: Iterable[str],
    sheet: str,
    policy: Policy | None = None,
    factors: Mapping[str, float] | None = None,
    wave_tags: Mapping[str, str] | None = None,
    *,
    rate_card: RateCard | None = None,
) -> dict[str, ModuleEffort]:
    """LOB -> ModuleEffort (sorted by LOB) for the ledger's scope items.

    `factors` / `wave_tags` are keyed by EffortRow.row_id (reviewer edits, wave-planner tags);
    `rate_card` overrides RateCard(sheet) (tests, or a caller that already holds one).
    """
    p = policy or get_policy()
    rc_policy = p.effort.rate_card
    card = rate_card or RateCard(sheet)
    factors, wave_tags = factors or {}, wave_tags or {}
    bid = _codes(bid_countries)
    modules: dict[str, ModuleEffort] = {}
    submodules: dict[str, set[str]] = {}

    for item in scope_items:
        scope_id = item.scope_item_id.strip()
        priced = card.get(scope_id)                       # None = the card has no row for it at all
        lob = item.lob.strip() or (priced.lob if priced else "") or rc_policy.unassigned_lob
        module = modules.setdefault(lob, ModuleEffort(lob=lob))
        if item.status == EXCLUDED_STATUS:
            if scope_id not in module.excluded_scope_ids:
                module.excluded_scope_ids.append(scope_id)
            continue
        if item.submodule.strip():
            submodules.setdefault(lob, set()).add(item.submodule.strip())
        if priced is None and scope_id not in module.unmatched_scope_ids:
            module.unmatched_scope_ids.append(scope_id)

        for country in line_countries(item, bid, p):
            row_id = line_row_id(item, country)
            rc = card.get(scope_id, country or None) if priced else None
            if rc is not None:
                labels = dict(business_area=item.business_area.strip() or rc.business_area,
                              description=item.description.strip() or rc.description,
                              complexity=rc.complexity, comments=rc.comments)
                phases = rc.phases()
            else:
                labels = dict(business_area=item.business_area.strip() or rc_policy.zero_effort_business_area,
                              description=item.description.strip()
                              or rc_policy.zero_effort_description.format(scope_id=scope_id),
                              complexity="", comments=rc_policy.zero_effort_comment)
                phases = {f: 0.0 for f in PHASE_FIELDS}
            row = EffortRow(
                row_id=row_id, item_row_id=item.row_id, lob=lob, country=country, scope_id=scope_id,
                multiplication_factor=_factor(factors.get(row_id, rc_policy.multiplication_factor), row_id),
                wave=str(wave_tags.get(row_id, "") or "").strip(), submodule=item.submodule.strip(),
                **labels, **phases,
            )
            row.compute_total()
            module.rows.append(row)

    for lob, module in modules.items():
        module.submodules = sorted(submodules.get(lob, ()))
        logger.info("catalogue effort %s: %d line(s), %.2f PD; %d unpriced, %d excluded", lob,
                    len(module.rows), module.total_effort, len(module.unmatched_scope_ids),
                    len(module.excluded_scope_ids))
    return dict(sorted(modules.items()))
