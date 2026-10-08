"""Build and price the resource plan for every wave (ported from generate_resource_grid).

Only the deterministic, wave-attributed path survives. What changed is where the numbers come from:
each wave's effort is an INPUT (`wave_lob_effort[i]`, `wave_pool_effort[i]`, computed from the agent's
allocations) instead of the old wave_attribution object, and each wave's phase split rides on its
WaveSpec. The rules are the old ones:

* A wave is funded with, and staffed by, only what it delivers: its LOBs plus its share of the two
  pooled blocks (non-catalogue tools, third-party integrations).
* A LOB whose share of its OWN programme-wide effort in a wave is below policy `wave_role_min_share`
  raises no roles there and is taken out of that wave's funding map (left in, it would be effort with
  no row to carry it). Its days are not lost: rebalance pass 2 scales the wave's remaining build rows
  to the full build target.
* The one-per-programme roles (Program Manager, Solution Architect) are staffed once: in the longest
  wave when waves overlap (its span IS the programme's), in every wave when they run back to back (a
  PM across three sequential waves is paid for all three). The per-wave tier is in every wave.
* Pooled head counts divide a block by the PROGRAMME's capacity, not a wave's, so one integration
  consultant working across concurrent waves is not raised once per wave.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence

from bidcore.policy import Policy, get_policy
from bidcore.resourcing.grid import derive_resource_grid, implementation_months
from bidcore.resourcing.models import ResourcePlan, WaveSpec
from bidcore.resourcing.pricing import price_plan
from bidcore.resourcing.roles import clean, required_roles

logger = logging.getLogger(__name__)


def _clean_map(values: Mapping[str, float] | None) -> dict[str, float]:
    """Keys cleaned (collisions summed), values as non-negative floats."""
    out: dict[str, float] = {}
    for key, days in (values or {}).items():
        name = clean(key)
        if name:
            out[name] = out.get(name, 0.0) + max(float(days or 0.0), 0.0)
    return out


def split_approved_by_wave(approved: Mapping[str, float], waves: Sequence[WaveSpec]) -> list[dict[str, float]]:
    """Split every entry of `approved` across the waves by implementation-month share.

    The delivery-calendar fallback for when no per-wave allocation exists: stated, always defined, and
    sums back to the approved total (to the cent per wave). Hypercare months earn no scope effort."""
    if len(waves) <= 1:
        return [dict(approved)]
    months = [implementation_months(wave) for wave in waves]
    total = sum(months)
    shares = [m / total for m in months] if total > 0 else [1.0 / len(waves)] * len(waves)
    buckets: list[dict[str, float]] = [{} for _ in waves]
    for key, days in approved.items():
        for index, share in enumerate(shares):
            portion = round(float(days or 0.0) * share, 2)
            if portion > 0:
                buckets[index][key] = portion
    return buckets


def build_resource_plan(
    waves: Sequence[WaveSpec],
    sequential: bool,
    programme_months: float,
    wave_lob_effort: Sequence[Mapping[str, float]],
    wave_pool_effort: Sequence[Mapping[str, float]],
    approved_by_lob: Mapping[str, float],
    submodules_by_lob: Mapping[str, Iterable[str]],
    submodule_effort_by_lob: Mapping[str, Mapping[str, float]],
    non_catalogue_names: Iterable[str],
    third_party_names: Iterable[str],
    pm_names: Iterable[str],
    policy: Policy | None = None,
) -> ResourcePlan:
    """One deterministic grid per wave, start months from the WaveSpecs, priced.

    `wave_lob_effort[i]` = {LOB: person-days wave i delivers}; empty -> `approved_by_lob` split by
    implementation-month share. `wave_pool_effort[i]` = {pool name (or policy pool key): person-days},
    already WITHOUT the project-management systems in `pm_names` (those keep a named lead instead).
    `approved_by_lob` (programme-wide) gives the LOB roster and its order. `programme_months` is the
    programme's elapsed span (pool sizing); <= 0 falls back to the waves' own span."""
    policy = policy or get_policy()
    res = policy.resourcing
    waves = list(waves or [])
    if not waves:
        logger.warning("resourcing: no waves; no resource plan")
        return ResourcePlan()
    for name, values in (("wave_lob_effort", wave_lob_effort), ("wave_pool_effort", wave_pool_effort)):
        if values and len(values) != len(waves):
            raise ValueError(f"{name} has {len(values)} entr(ies) for {len(waves)} wave(s)")

    pool_names = dict(res.pools)                                   # policy key -> pool name
    pool_of = {**{name: name for name in pool_names.values()}, **pool_names}
    approved_total = {k: v for k, v in _clean_map(approved_by_lob).items() if k not in pool_of}
    lob_by_wave = ([_clean_map(m) for m in wave_lob_effort] if wave_lob_effort
                   else split_approved_by_wave(approved_total, waves))
    pool_by_wave: list[dict[str, float]] = [{} for _ in waves]
    for index, raw in enumerate(wave_pool_effort or []):
        for key, days in _clean_map(raw).items():
            if key in pool_of:
                pool = pool_of[key]
                pool_by_wave[index][pool] = pool_by_wave[index].get(pool, 0.0) + days
            else:
                logger.warning("resourcing: unknown pool %r in wave_pool_effort[%d]; ignored", key, index)
    for index, lob_map in enumerate(lob_by_wave):                  # a pool key in a LOB map is pool effort
        for key in [k for k in lob_map if k in pool_of]:
            pool = pool_of[key]
            pool_by_wave[index][pool] = pool_by_wave[index].get(pool, 0.0) + lob_map.pop(key)

    lob_order = list(approved_total)
    for lob_map in lob_by_wave:
        lob_order += [lob for lob in lob_map if lob not in lob_order]
    lob_totals = {lob: sum(m.get(lob, 0.0) for m in lob_by_wave) for lob in lob_order}
    submodules = {clean(lob): [clean(n) for n in names or []] for lob, names in (submodules_by_lob or {}).items()}
    submodule_effort = {clean(lob): _clean_map(split) for lob, split in (submodule_effort_by_lob or {}).items()}
    non_catalogue_names, third_party_names, pm_names = list(non_catalogue_names), list(third_party_names), set(pm_names)
    if programme_months <= 0:
        spans = [max(w.total_months, 1) for w in waves]
        programme_months = float(sum(spans) if sequential else max(spans))
    min_share = max(0.0, float(res.wave_role_min_share))
    programme_wave = -1 if sequential else max(range(len(waves)), key=lambda i: waves[i].total_months)

    def lob_share(index: int, lob: str) -> float:
        total = lob_totals.get(lob, 0.0)
        return lob_by_wave[index].get(lob, 0.0) / total if total > 0 else 0.0

    grids = []
    for index, wave in enumerate(waves):
        approved = dict(lob_by_wave[index])
        for pool, days in pool_by_wave[index].items():
            if days > 0:
                approved[pool] = round(days, 2)
        if min_share > 0:
            dropped = {lob: approved.pop(lob) for lob in list(lob_by_wave[index])
                       if lob in approved and lob_share(index, lob) < min_share}
            if dropped:
                logger.info("resourcing: %s carries under %.0f%% of %s; those %.1f PD ride on its other rows",
                            wave.name, min_share * 100, ", ".join(sorted(dropped)), sum(dropped.values()))
        wave_submodule_effort = {
            lob: {name: round(days * lob_share(index, lob), 2) for name, days in split.items()}
            for lob, split in submodule_effort.items() if lob in approved
        }
        pools = pool_by_wave[index]
        roles = required_roles(
            [lob for lob in lob_order if lob in approved],
            non_catalogue_names, third_party_names,
            include_singular_programme_roles=sequential or index == programme_wave,
            submodules_by_lob=submodules, submodule_effort_by_lob=wave_submodule_effort,
            approved_effort_by_lob=approved, programme_months=programme_months,
            pooled_third_party_days=pools.get(pool_names["third_party"], 0.0),
            pooled_non_catalogue_days=pools.get(pool_names["non_catalogue"], 0.0),
            pm_names=pm_names, policy=policy,
        )
        grid = derive_resource_grid(wave, roles, approved, policy)
        grid.start_month = wave.start_month
        grids.append(grid)

    plan = price_plan(ResourcePlan(grids=grids, source="derived"), policy)
    logger.info("resourcing: %d %s wave grid(s), %.2f man-months, peak %.2f FTE", len(grids),
                "sequential" if sequential else "overlapping", plan.grand_total_mm, plan.peak_fte)
    return plan
