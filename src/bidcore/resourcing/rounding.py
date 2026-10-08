"""FTE rounding: every staffing figure the client reads is a multiple of a grain (policy: 0.5 FTE).

Why largest-remainder and not per-cell rounding: a distributive consultant row is sized so that its
months sum to approved catalogue person-days. Rounding twelve cells independently drifts that sum by
up to six months x a quarter FTE. `quantize_row` instead fixes the row TOTAL to the nearest grain
first, then hands those units to the months with the strongest claim, so the row still sums to (very
near) what it was sized to and every printed cell is a clean 0.5. A row of individually tiny but
collectively material cells keeps its effort, concentrated in the months that carried most of it.

`round_all_cells_to_grain` is the rebalance's final, per-cell presentation rounding (Python's
half-to-even `round`, exactly as the old code). It never removes a cell or a row: dropping a role is
a staffing decision, not a rounding side effect.

Ported from resource_grid_layer4.py (`_quantize_half`, `_quantize_row`, `_quantize_grid`,
`_round_all_cells_to_grain`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from bidcore.policy import Policy, get_policy
from bidcore.resourcing.models import GridRow, ResourcePlan, WaveResourceGrid


def _grain(grain: float | None, policy: Policy | None) -> float:
    step = float(grain) if grain is not None else (policy or get_policy()).resourcing.fte_grain
    if step <= 0:
        raise ValueError(f"FTE grain must be positive, got {step}")
    return step


def quantize_half(value: float, grain: float | None = None, policy: Policy | None = None) -> float:
    """Nearest multiple of the grain (default policy fte_grain), half-up, never negative.

    0.05 -> 0.0, 0.3 -> 0.5, 1.2 -> 1.0, 0.25 -> 0.5."""
    step = _grain(grain, policy)
    if value <= 0:
        return 0.0
    return math.floor(value / step + 0.5) * step


def quantize_row(row: GridRow, grain: float | None = None, policy: Policy | None = None) -> None:
    """Round every cell of `row` to the grain in place, keeping the row total on the nearest grain.

    Floors every cell, then gives the shortfall (never more than one unit per cell, since every
    remainder is below one grain) to the cells with the largest remainders; ties go to the earlier
    month."""
    if not row.cells:
        return
    step = _grain(grain, policy)
    target_units = int(math.floor(sum(c.fte for c in row.cells) / step + 0.5))
    if target_units <= 0:
        for cell in row.cells:
            cell.fte = 0.0
        return

    units = [int(math.floor(c.fte / step)) for c in row.cells]
    remainders = [(c.fte / step) - unit for c, unit in zip(row.cells, units)]
    shortfall = target_units - sum(units)
    if shortfall > 0:
        order = sorted(range(len(row.cells)), key=lambda i: -remainders[i])
        for index in order[:shortfall]:
            units[index] += 1
    elif shortfall < 0:
        # Unreachable for non-negative cells; kept from the original as a guard. Takes back from the
        # weakest claims, never below zero.
        excess = -shortfall
        for index in sorted(range(len(row.cells)), key=lambda i: remainders[i]):
            if excess <= 0:
                break
            take = min(units[index], excess)
            units[index] -= take
            excess -= take

    for cell, unit in zip(row.cells, units):
        cell.fte = round(unit * step, 2)


def quantize_grid(grid: WaveResourceGrid, grain: float | None = None, policy: Policy | None = None) -> None:
    """Round every row to the grain, drop cells and rows left at nothing, recompute the totals."""
    step = _grain(grain, policy)
    for row in grid.rows:
        quantize_row(row, step)
        row.cells = [cell for cell in row.cells if cell.fte > 0]
        row.recompute_total()
    grid.rows = [row for row in grid.rows if row.cells]
    grid.recompute_totals()


def round_all_cells_to_grain(
    plan: ResourcePlan,
    default_grain: float | None = None,
    overrides: Mapping[str, float] | None = None,
    policy: Policy | None = None,
) -> None:
    """Round each cell to the nearest multiple of its row's grain (half-to-even), in place.

    `overrides` maps a role title to its own grain (a small category consultant rounds at 0.25 so
    its peak months do not all collapse to zero). A cell that rounds to zero stays in place, so no
    role is ever removed here. Totals are recomputed so Total Man-months match the visible cells."""
    if default_grain is None:
        default_grain = (policy or get_policy()).resourcing.fte_grain
    if default_grain <= 0:
        return
    overrides = overrides or {}
    for grid in plan.grids:
        for row in grid.rows:
            grain = overrides.get(row.role_title, default_grain)
            if grain <= 0:
                continue
            inverse = 1.0 / grain
            for cell in row.cells:
                cell.fte = round(cell.fte * inverse) / inverse
            row.recompute_total()
        grid.recompute_totals()
