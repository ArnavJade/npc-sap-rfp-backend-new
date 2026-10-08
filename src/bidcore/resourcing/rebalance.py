"""Rebalance the resource plan to the Summary of Project Effort (ported from resource_grid_layer4.py).

Why: the grid is built from role profiles, so on its own it does not add up to the Summary sheet. Four
deterministic passes rescale it so its combined man-days equal Summary of Imp
(= Total Build + Final Prep + Go-Live + Programme Management + Hypercare) to the person-day, before
presentation rounding. Risk contingency is NOT baked in (it is its own reconciliation row), so no
per-role FTE carries a risk uplift.

  1. Management build cells (the policy programme roles, implementation months only) are scaled so
     their combined MD = mgmt_pct_of_build (8%) of Total Build Effort - the Summary's PM row. No cell
     is rounded away and no role is dropped.
  2. Module build cells (every other row except the specialist category consultants) are scaled to
     Total Build minus the category totals: this closes the gap between what the role profiles imply
     and what Core BP + Tech Dev actually priced, without making module consultants also cover work
     the category rows already carry.
  3. Final Prep + Go-Live (fp_gl_pct_of_build, 13%) is added onto module Deploy cells in proportion to
     each row's Deploy FTE. Management and category rows are left alone, and a row with no Deploy
     presence gets nothing (presence outside its window would misstate when it works).
  4. Hypercare (PGLS) cells of ALL rows are scaled to the Hypercare figure.

Every pass is per wave: wave i takes target x its weight for that pass (PassWeights from the wave
plan; without them every pass uses each wave's share of the module build man-months). Specialist
category consultant rows (titles from policy, one per category with effort) are injected per wave at
that category's weight; a category whose weight in a wave is 0 gets no row there. Finally every cell
is rounded to the 0.5 grain, or 0.25 for a category under the small-category threshold so a small
scope (BASIS 45 MD over three 8-month waves) does not round to zero in every month.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping, Sequence

from bidcore.policy import Policy, get_policy
from bidcore.resourcing.models import GridCell, GridRow, PassWeights, ResourcePlan, WaveResourceGrid
from bidcore.resourcing.rounding import round_all_cells_to_grain

logger = logging.getLogger(__name__)


def _category_title(key: str, policy: Policy) -> str:
    """A category consultant title; a policy category key (e.g. "data_migration") maps to its title."""
    return policy.resourcing.category_consultants.get(key, key)


def _phase_month_indices(grid: WaveResourceGrid, phase_names: Collection[str]) -> set[int]:
    wanted = {name.lower() for name in phase_names}
    return {i + 1 for i, band in enumerate(grid.phase_bands) if band and band.lower() in wanted}


def _scale_cells_to_target(rows: Sequence[GridRow], months: set[int], target_days: float, days_per_month: float) -> None:
    """Scale every cell of `rows` in `months` uniformly so they total `target_days`. No-op without a
    target or anything to scale from; never deletes a cell."""
    if target_days <= 0 or not rows or not months:
        return
    current_mm = sum(cell.fte for row in rows for cell in row.cells if cell.month_index in months)
    if current_mm <= 0:
        return
    ratio = (target_days / days_per_month) / current_mm
    for row in rows:
        for cell in row.cells:
            if cell.month_index in months:
                cell.fte = round(cell.fte * ratio, 4)
        row.recompute_total()


def _scale_mgmt_build(grid, target_days, days_per_month, mgmt_titles, build_phases) -> None:
    """Pass 1: management rows' implementation cells -> target (PGLS belongs to pass 4)."""
    rows = [row for row in grid.rows if row.role_title in mgmt_titles]
    _scale_cells_to_target(rows, _phase_month_indices(grid, build_phases), target_days, days_per_month)


def _scale_module_build(grid, target_days, days_per_month, excluded_titles, build_phases) -> None:
    """Pass 2: module rows' (not management, not category) implementation cells -> target."""
    rows = [row for row in grid.rows if row.role_title not in excluded_titles]
    _scale_cells_to_target(rows, _phase_month_indices(grid, build_phases), target_days, days_per_month)


def _spread_fp_gl(grid, target_days, days_per_month, excluded_titles, deploy_phase) -> None:
    """Pass 3: add target onto module rows' Deploy cells, proportional to each row's Deploy FTE."""
    if target_days <= 0 or not grid.rows:
        return
    deploy = _phase_month_indices(grid, {deploy_phase})
    if not deploy:
        return
    per_row = [(row, sum(c.fte for c in row.cells if c.month_index in deploy))
               for row in grid.rows if row.role_title not in excluded_titles]
    grand = sum(total for _, total in per_row)
    if grand <= 0:
        return
    extra_mm = target_days / days_per_month
    for row, row_total in per_row:
        if row_total <= 0:
            continue
        row_share = extra_mm * (row_total / grand)
        for cell in row.cells:
            if cell.month_index in deploy:
                cell.fte = round(cell.fte + row_share * (cell.fte / row_total), 4)
        row.recompute_total()


def _scale_pgls(grid, target_days, days_per_month, hypercare_phase) -> None:
    """Pass 4: every row's hypercare cells -> target (the wave's share of the Hypercare row)."""
    _scale_cells_to_target(list(grid.rows), _phase_month_indices(grid, {hypercare_phase}), target_days, days_per_month)


def inject_category_consultant_rows(
    plan: ResourcePlan,
    category_effort_days: Mapping[str, float],
    wave_weights: Sequence[float],
    days_per_month: float | None = None,
    category_weights: Mapping[str, Sequence[float]] | None = None,
    policy: Policy | None = None,
) -> None:
    """One specialist consultant row per (wave, category with effort), sized to the wave's share.

    Share = the category's own weight for the wave (`category_weights`), else `wave_weights`. The wave's
    days are spread evenly over its implementation months with distributive PGLS retention on the
    hypercare months - a starting shape only; the rebalance passes set the totals. A share of 0 means the
    wave does no such work: any existing row for it is removed. Idempotent: an existing row is refreshed
    in place, never duplicated. Rows are Offshore, additive, entity_kind "technical"."""
    policy = policy or get_policy()
    res = policy.resourcing
    days_per_month = days_per_month or policy.commercials.working_days_per_month
    if not category_effort_days:
        return
    if len(wave_weights) != len(plan.grids):
        logger.warning("resourcing: %d wave weight(s) for %d grid(s); category rows not injected",
                       len(wave_weights), len(plan.grids))
        return
    category_weights = {_category_title(k, policy): list(w) for k, w in (category_weights or {}).items()
                        if len(w) == len(plan.grids)}
    build_phases = set(res.phases)
    location = res.consultant_profile["location"]
    retention = res.pgls_retention["distributive"]

    for wave_index, (grid, weight) in enumerate(zip(plan.grids, wave_weights)):
        build_months = sorted(_phase_month_indices(grid, build_phases))
        pgls_months = sorted(_phase_month_indices(grid, {res.hypercare_phase}))
        if not build_months:
            continue
        for key, total_days in category_effort_days.items():
            title = _category_title(key, policy)
            if total_days <= 0:
                continue
            per_category = category_weights.get(title)
            share = per_category[wave_index] if per_category else weight
            if share <= 0:
                grid.rows = [row for row in grid.rows if row.role_title != title]
                continue
            build_fte = (total_days * share / days_per_month) / len(build_months)
            cells = [GridCell(month_index=i, phase=grid.phase_bands[i - 1], fte=build_fte) for i in build_months]
            cells += [GridCell(month_index=i, phase=grid.phase_bands[i - 1], fte=build_fte * retention)
                      for i in pgls_months]
            existing = next((row for row in grid.rows if row.role_title == title), None)
            if existing is not None:
                existing.location, existing.cells = location, cells
                existing.recompute_total()
            else:
                row = GridRow(role_title=title, location=location, entity_kind="technical", entity_name=title,
                              contribution="additive", cells=cells)
                row.recompute_total()
                grid.rows.append(row)


def rebalance_plan_to_effort_summary(
    plan: ResourcePlan,
    total_build_effort: float,
    hypercare_effort_days: float = 0.0,
    category_effort_days: Mapping[str, float] | None = None,
    weights: PassWeights | None = None,
    policy: Policy | None = None,
) -> None:
    """Rescale `plan` in place so it reconciles with the Summary of Project Effort (module docstring).

    `total_build_effort` = Functional Scope + Data Migration + Tech Dev + Security + BASIS + Analytics.
    `category_effort_days` maps a category consultant title (or policy category key) to its programme
    total MD. `weights` gives each pass its own per-wave shares; a list of the wrong length or with no
    positive weight falls back to the grid's build share for that pass. Plan-level price fields are not
    refreshed: call `price_plan` again if you need them for the rebalanced grid."""
    if plan is None or not plan.grids or total_build_effort <= 0:
        return
    policy = policy or get_policy()
    res = policy.resourcing
    days_per_month = policy.commercials.working_days_per_month
    if days_per_month <= 0:
        return
    n = len(plan.grids)

    categories: dict[str, float] = {}
    for key, days in (category_effort_days or {}).items():
        title = _category_title(key, policy)
        categories[title] = categories.get(title, 0.0) + max(0.0, float(days or 0.0))
    mgmt_titles = res.programme_role_titles
    category_titles = set(res.category_consultants.values()) | set(categories)
    excluded = mgmt_titles | category_titles

    build_mm = [sum(r.total_man_months for r in g.rows if r.role_title not in excluded) for g in plan.grids]
    if sum(build_mm) <= 0:
        build_mm = [1.0] * n
    grid_weights = [mm / sum(build_mm) for mm in build_mm]

    def pass_weights(label: str) -> list[float]:
        if weights is None:
            return grid_weights
        clipped = [max(float(v), 0.0) for v in getattr(weights, label)]
        if len(clipped) != n or sum(clipped) <= 0:
            logger.warning("resourcing: %d %s weight(s) for %d grid(s); using the grid's build share",
                           len(clipped), label, n)
            return grid_weights
        return [v / sum(clipped) for v in clipped]

    mgmt_w, build_w, fp_gl_w, hc_w = (pass_weights(label) for label in ("mgmt", "build", "fp_gl", "hypercare"))
    category_w: dict[str, list[float]] = {}
    for key, values in (weights.category if weights is not None else {}).items():
        clipped = [max(float(v), 0.0) for v in values]
        if len(clipped) == n:        # all zeros stays all zeros: the category is in no wave
            category_w[_category_title(key, policy)] = [v / sum(clipped) for v in clipped] if sum(clipped) > 0 else clipped

    if any(days > 0 for days in categories.values()):
        inject_category_consultant_rows(plan, categories, build_w, days_per_month, category_w, policy)

    mgmt_target = total_build_effort * res.rebalance["mgmt_pct_of_build"]
    module_target = max(0.0, total_build_effort - sum(categories.values()))
    fp_gl_target = total_build_effort * res.rebalance["fp_gl_pct_of_build"]
    hypercare_target = max(0.0, float(hypercare_effort_days or 0.0))
    build_phases = set(res.phases)
    deploy_phase = res.phases[-1]          # the go-live phase: last implementation phase

    for index, grid in enumerate(plan.grids):
        _scale_mgmt_build(grid, mgmt_target * mgmt_w[index], days_per_month, mgmt_titles, build_phases)
        _scale_module_build(grid, module_target * build_w[index], days_per_month, excluded, build_phases)
        _spread_fp_gl(grid, fp_gl_target * fp_gl_w[index], days_per_month, excluded, deploy_phase)
        _scale_pgls(grid, hypercare_target * hc_w[index], days_per_month, res.hypercare_phase)
        grid.recompute_totals()

    small = {title: res.fte_grain_small for title, days in categories.items()
             if 0 < days < res.small_category_md_threshold}
    round_all_cells_to_grain(plan, res.fte_grain, small, policy)
    logger.info("resourcing: rebalanced - build %.2f PD, mgmt %.2f, module %.2f, FP+GL %.2f, hypercare %.2f; "
                "small-grain categories: %s", total_build_effort, mgmt_target, module_target, fp_gl_target,
                hypercare_target, ", ".join(sorted(small)) or "none")
