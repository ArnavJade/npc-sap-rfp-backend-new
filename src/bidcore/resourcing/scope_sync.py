"""Scope sync: the final resource grid is the ground truth for the four specialist scope tables
(ported from resource_scope_sync.py; runs after the rebalance, before anything that ties one
sheet's figures to another's is written).

Why: after the rebalance a specialist category consultant row and its scope sheet describe the same
work twice, and a reviewer must not see them disagree. Each row is paired with one table:

    Data Migration Consultants  <->  data_migration tables (wave N row <-> wave N table)
    GRC Consultants             <->  security              (all waves combined)
    BASIS Consultants           <->  basis                 (all waves combined)
    Analytics / BI Consultants  <->  analytics             (all waves combined)

A row's grid figure is its total man-months (every month, PGLS included) x working days per month.
Three steps, in order:

  1. Off-grain category cells (the rebalance's 0.25 small-category grain) are rounded UP to the next
     slot (0.5 FTE): the Resource Estimation tables must not show quarter FTEs. No other row changes.
  2. A row showing 0 while its table does not is laid out from the table, which stays as it is: the
     table's man-months floored to whole slots (one slot = 0.5 FTE for one month; at least one), from
     each wave's first Realize month, one slot per wave in wave order, then round again a month later
     (Data Migration: consecutive months within its own wave).
  3. A table's In Scope effort cells are moved one step (1 PD) at a time, on randomly chosen cells,
     until its total lies in [grid, grid + max_variance_days]. Out of Scope rows are never touched. A
     cell stays inside its sheet's limits (Data Migration <= 4, Basis <= 5, Security <= 120; never
     lowered below 1) unless the target cannot be reached otherwise; then the cap is lifted for that
     table and a note says so. Analytics effort is computed from reference rates, so only its grid
     side is laid out; an out-of-band analytics table is reported, not moved.

The random choice is seeded (`random.Random(seed)`, seed = bid id by policy; the old module used an
unseeded RNG), so the same plan, tables and seed always produce the same tables. The plan's price
fields are not refreshed here: re-run `price_plan` if they are needed after the sync.
"""

from __future__ import annotations

import logging
import math
import random
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

from bidcore.effort.models import WorkstreamTables
from bidcore.policy import Policy, get_policy
from bidcore.resourcing.models import GridCell, GridRow, ResourcePlan, WaveResourceGrid

logger = logging.getLogger(__name__)

IN_SCOPE = "In Scope"                  # mirrors bidcore.ledger.base.Status
_LEVELS = ("Low", "Medium", "High")    # order of the analytics reference-rate lists
_EPS = 1e-6
Cell = tuple[dict, str]                # (row dict, effort key): one movable sheet cell


@dataclass
class _Sync:
    days_per_month: float
    max_variance: float
    step: float
    slot_fte: float
    min_cell: float
    location: str
    build_phases: frozenset[str]
    start_phase: str
    rng: random.Random
    notes: list[str] = field(default_factory=list)

    def note(self, text: str, warn: bool = False) -> None:
        self.notes.append(text)
        (logger.warning if warn else logger.info)("scope sync: %s", text)


# ---------------------------------------------------------------------------------------- grid side
def row_days(grids: Sequence[WaveResourceGrid], title: str, days_per_month: float) -> float:
    """Person-days the `title` row carries across `grids` (every month)."""
    return round(sum(c.fte for g in grids for r in g.rows if r.role_title == title for c in r.cells)
                 * days_per_month, 2)


def snap_category_rows_to_half_fte(plan: ResourcePlan, titles: Collection[str], slot_fte: float) -> int:
    """Round every off-slot cell of the category rows UP to the next slot. Returns cells changed."""
    changed = 0
    for grid in plan.grids:
        for row in grid.rows:
            if row.role_title not in titles:
                continue
            for cell in row.cells:
                units = cell.fte / slot_fte
                if abs(units - round(units)) > _EPS:
                    cell.fte = math.ceil(units - _EPS) * slot_fte
                    changed += 1
        grid.recompute_totals()
    return changed


def _slot_months(grid: WaveResourceGrid, sync: _Sync) -> list[int]:
    """Months a slot may go in, in fill order: the first Realize month and every build month after it
    (the first build month, or M1, when the wave has no Realize phase)."""
    bands = [(band or "").lower() for band in grid.phase_bands]
    build = [i + 1 for i, band in enumerate(bands) if band in sync.build_phases]
    realize = [i + 1 for i, band in enumerate(bands) if band == sync.start_phase]
    start = realize[0] if realize else (build[0] if build else 1)
    return [i for i in build if i >= start] or [start]


def _add_slot(grid: WaveResourceGrid, title: str, month_index: int, sync: _Sync) -> None:
    """One more slot for `title` in `month_index`, creating the row or the cell when missing."""
    row = next((r for r in grid.rows if r.role_title == title), None)
    if row is None:
        row = GridRow(role_title=title, location=sync.location, entity_kind="technical", entity_name=title,
                      contribution="additive")
        grid.rows.append(row)
    cell = next((c for c in row.cells if c.month_index == month_index), None)
    if cell is None:
        phase = grid.phase_bands[month_index - 1] if 0 < month_index <= len(grid.phase_bands) else ""
        cell = GridCell(month_index=month_index, phase=phase, fte=0.0)
        row.cells.append(cell)
        row.cells.sort(key=lambda c: c.month_index)
    cell.fte = round(cell.fte + sync.slot_fte, 4)
    row.recompute_total()


def _fill_zero_row(grids: Sequence[WaveResourceGrid], title: str, sheet_days: float, sync: _Sync) -> None:
    """Lay out an empty `title` row from its table's total: slot k goes to wave k mod n, month k div n
    of that wave's slot months (stacking on the same months once a wave runs out)."""
    slots = max(1, math.floor(sheet_days / sync.days_per_month / sync.slot_fte + _EPS))
    for k in range(slots):
        grid = grids[k % len(grids)]
        months = _slot_months(grid, sync)
        _add_slot(grid, title, months[(k // len(grids)) % len(months)], sync)
    for grid in grids:
        grid.recompute_totals()
    sync.note(f"{title} showed 0 against a table of {sheet_days:g} PD: laid out as {slots} x "
              f"{sync.slot_fte:g}-FTE month(s) ({slots * sync.slot_fte * sync.days_per_month:g} PD) across "
              + ", ".join(grid.wave_name for grid in grids))


# --------------------------------------------------------------------------------------- table side
def _value(cell: Cell) -> float:
    value = cell[0].get(cell[1])
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _total(cells: Sequence[Cell]) -> float:
    return round(sum(_value(cell) for cell in cells), 2)


def _in_scope(row: dict) -> bool:
    return row.get("status", IN_SCOPE) == IN_SCOPE


def _move_to_band(cells: list[Cell], grid_days: float, cap: float, label: str, sync: _Sync,
                  integer: bool = False) -> None:
    """Move the table total into [grid_days, grid_days + max_variance] one step at a time on randomly
    chosen cells. `integer` stores whole numbers (Basis, Security)."""
    low, high = grid_days, grid_days + sync.max_variance
    before = total = _total(cells)
    added = removed = 0
    cap_lifted = False

    def put(cell: Cell, delta: float) -> None:
        new = _value(cell) + delta
        cell[0][cell[1]] = int(round(new)) if integer else new

    if not cells:
        if before < low - _EPS or before > high + _EPS:
            sync.note(f"{label}: grid carries {grid_days:g} PD but the table has no In Scope effort cell "
                      "to move; left as it is", warn=True)
    else:
        while total < low - _EPS:
            pool = [c for c in cells if _value(c) + sync.step <= cap + _EPS]
            if not pool:
                if not cap_lifted:
                    sync.note(f"{label}: every cell is at its {cap:g} PD cap below the {low:g} PD target; "
                              "cap lifted for this table", warn=True)
                cap_lifted, pool = True, cells
            put(sync.rng.choice(pool), sync.step)
            total += sync.step
            added += 1
        while total > high + _EPS:
            pool = [c for c in cells if _value(c) - sync.step >= sync.min_cell - _EPS]
            if not pool:
                sync.note(f"{label}: every cell is at the {sync.min_cell:g} PD floor; the table stays "
                          f"{total - grid_days:g} PD above the grid's {grid_days:g} PD", warn=True)
                break
            put(sync.rng.choice(pool), -sync.step)
            total -= sync.step
            removed += 1

    after = _total(cells)
    in_band = low - _EPS <= after <= high + _EPS
    sync.note(f"{label}: grid {grid_days:g} PD, table {before:g} -> {after:g} PD (+{added * sync.step:g} / "
              f"-{removed * sync.step:g} PD on random cells)" + ("" if in_band else " - OUT OF BAND"),
              warn=not in_band)


# ------------------------------------------------------------------------------------ orchestration
def _sync_data_migration(plan: ResourcePlan, tables: WorkstreamTables, title: str, sync: _Sync,
                         policy: Policy) -> None:
    """Wave N's Data Migration Consultants row <-> wave N's table."""
    spec = policy.workstreams["data_migration"]
    keys, defaults = list(spec["effort_keys"]), spec["default_effort_days"]
    wave_tables = tables.data_migration
    if not any(wave_tables):
        if row_days(plan.grids, title, sync.days_per_month) > 0:
            sync.note(f"Data Migration: grid carries {row_days(plan.grids, title, sync.days_per_month):g} PD "
                      "but the table has no object; not synced", warn=True)
        return
    if len(wave_tables) != len(plan.grids):
        sync.note(f"Data Migration: {len(plan.grids)} grid wave(s) but {len(wave_tables)} table(s); not synced",
                  warn=True)
        return
    for grid, rows in zip(plan.grids, wave_tables):
        for row in rows:                      # every effort cell filled (the writer's defaults) so it can move
            for key in keys:
                row.setdefault(key, defaults[key])
        cells = [(row, key) for row in rows if _in_scope(row) for key in keys]
        sheet_days = _total(cells)
        grid_days = row_days([grid], title, sync.days_per_month)
        if grid_days <= 0 < sheet_days:
            _fill_zero_row([grid], title, sheet_days, sync)
            grid_days = row_days([grid], title, sync.days_per_month)
        if grid_days <= 0 and sheet_days <= 0:
            continue
        _move_to_band(cells, grid_days, float(max(spec["allowed_effort_days"])), f"Data Migration {grid.wave_name}",
                      sync)


def _sync_combined(plan: ResourcePlan, title: str, label: str, cells: list[Cell], cap: float, sync: _Sync) -> None:
    """A table matched on its all-wave total (Security, Basis); whole-number cells."""
    sheet_days = _total(cells)
    grid_days = row_days(plan.grids, title, sync.days_per_month)
    if grid_days <= 0 < sheet_days:
        _fill_zero_row(plan.grids, title, sheet_days, sync)
        grid_days = row_days(plan.grids, title, sync.days_per_month)
    if grid_days <= 0 and sheet_days <= 0:
        return
    _move_to_band(cells, grid_days, cap, label, sync, integer=True)


def analytics_effort_days(tables: WorkstreamTables, policy: Policy | None = None) -> float:
    """In Scope analytics person-days: each row's computed `total`, else its reference-rate effort
    (no_of_objects x the type's Devlp + Unit + QA rates at its complexity, x the Standard factor)."""
    if tables.analytics_excluded:
        return 0.0
    spec = (policy or get_policy()).workstreams.get("analytics", {})
    rates = spec.get("reference_rates", {})
    total = 0.0
    for row in tables.analytics:
        if not _in_scope(row):
            continue
        value = row.get("total")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += float(value)
            continue
        table = rates.get(row.get("object_type")) or rates.get("Report", {})
        level = _LEVELS.index(row["complexity"]) if row.get("complexity") in _LEVELS else 1
        factor = spec.get("standard_factor", 1) if row.get("build") == "Standard" else 1
        total += float(row.get("no_of_objects") or 0) * sum(metric[level] for metric in table.values()) * factor
    return round(total, 2)


def _sync_analytics(plan: ResourcePlan, tables: WorkstreamTables, title: str, sync: _Sync, policy: Policy) -> None:
    """Grid side only: an empty row is laid out from the table; the table itself is never moved."""
    sheet_days = analytics_effort_days(tables, policy)
    grid_days = row_days(plan.grids, title, sync.days_per_month)
    if grid_days <= 0 < sheet_days:
        _fill_zero_row(plan.grids, title, sheet_days, sync)
        grid_days = row_days(plan.grids, title, sync.days_per_month)
    if grid_days <= 0 and sheet_days <= 0:
        return
    if grid_days - _EPS <= sheet_days <= grid_days + sync.max_variance + _EPS:
        sync.note(f"Analytics: grid {grid_days:g} PD, table {sheet_days:g} PD - in band")
    else:
        sync.note(f"Analytics: grid {grid_days:g} PD, table {sheet_days:g} PD - out of band; the analytics "
                  "table is rate-driven and is not moved", warn=True)


def sync_scope_tables(plan: ResourcePlan, tables: WorkstreamTables, policy: Policy | None = None,
                      seed: str = "") -> list[str]:
    """Tie the four specialist tables to the final grid (module docstring). Mutates the category rows of
    `plan` and the table rows of `tables` in place; deterministic for a given `seed`. Returns notes."""
    policy = policy or get_policy()
    res = policy.resourcing
    cfg = res.scope_sync
    if not cfg.enabled:
        return ["scope sync disabled by policy"]
    days_per_month = float(policy.commercials.working_days_per_month)
    if plan is None or not plan.grids or tables is None or days_per_month <= 0:
        return ["scope sync skipped: no resource plan grid or no scope tables"]

    sync = _Sync(days_per_month=days_per_month, max_variance=float(cfg.max_variance_days), step=float(cfg.step_days),
                 slot_fte=float(cfg.slot_fte), min_cell=float(cfg.min_cell_days),
                 location=res.consultant_profile["location"], build_phases=frozenset(p.lower() for p in res.phases),
                 start_phase=str(cfg.slot_start_phase).lower(), rng=random.Random(seed))
    titles = res.category_consultants
    changed = snap_category_rows_to_half_fte(plan, set(titles.values()), sync.slot_fte)
    if changed:
        sync.note(f"{changed} category consultant cell(s) rounded up to the {sync.slot_fte:g}-FTE grain")

    _sync_data_migration(plan, tables, titles["data_migration"], sync, policy)
    basis_keys = list(policy.workstreams["basis"]["effort_keys"])
    for area, label, rows, keys in (("security", "Security", tables.security, ["effort_days"]),
                                    ("basis", "Basis", tables.basis, basis_keys)):
        cells = [(row, key) for row in rows if _in_scope(row) for key in keys]
        cap = float(policy.workstreams[area]["effort_range"][1])
        _sync_combined(plan, titles[area], label, cells, cap, sync)
    _sync_analytics(plan, tables, titles["analytics"], sync, policy)

    for grid in plan.grids:
        grid.recompute_totals()
    return sync.notes
