"""Shared builders for the resourcing tests: small hand-made waves and plans (no ledger, no network)."""

from __future__ import annotations

import pytest

from bidcore.policy import get_policy
from bidcore.resourcing import GridCell, GridRow, ResourcePlan, WaveResourceGrid, WaveSpec, build_resource_plan

POLICY = get_policy()
DAYS = POLICY.commercials.working_days_per_month
TITLES = POLICY.resourcing.category_consultants          # data_migration / security / basis / analytics


def make_plan(
    waves: list[WaveSpec],
    wave_lob_effort: list[dict[str, float]],
    *,
    sequential: bool = False,
    programme_months: float = 12.0,
    wave_pool_effort: list[dict[str, float]] | None = None,
    approved_by_lob: dict[str, float] | None = None,
    submodules_by_lob: dict[str, list[str]] | None = None,
    submodule_effort_by_lob: dict[str, dict[str, float]] | None = None,
    non_catalogue_names: list[str] | None = None,
    third_party_names: list[str] | None = None,
    pm_names: set[str] | None = None,
) -> ResourcePlan:
    """build_resource_plan with everything not under test defaulted."""
    if approved_by_lob is None:
        approved_by_lob = {}
        for wave_map in wave_lob_effort:
            for lob, days in wave_map.items():
                approved_by_lob[lob] = approved_by_lob.get(lob, 0.0) + days
    return build_resource_plan(
        waves, sequential, programme_months, wave_lob_effort, wave_pool_effort or [], approved_by_lob,
        submodules_by_lob or {}, submodule_effort_by_lob or {}, non_catalogue_names or [],
        third_party_names or [], pm_names or set(),
    )


def make_grid(name: str, bands: list[str], rows: dict[str, list[float]], start_month: int = 0) -> WaveResourceGrid:
    """A grid with one Offshore additive row per title, cells taken from the FTE lists (0 = no cell)."""
    grid = WaveResourceGrid(wave_name=name, months=len(bands), start_month=start_month, phase_bands=bands)
    for title, ftes in rows.items():
        grid.rows.append(GridRow(
            role_title=title, location="Offshore", entity_kind="technical", entity_name=title,
            contribution="additive",
            cells=[GridCell(month_index=i + 1, phase=bands[i], fte=fte) for i, fte in enumerate(ftes) if fte > 0],
        ))
    grid.recompute_totals()
    return grid


def cells_md(plan: ResourcePlan, keep=lambda row, cell: True) -> float:
    """Person-days of the cells `keep` selects, summed from the cells themselves (not rounded totals)."""
    return sum(cell.fte for grid in plan.grids for row in grid.rows for cell in row.cells if keep(row, cell)) * DAYS


@pytest.fixture
def two_waves() -> list[WaveSpec]:
    return [WaveSpec(name="W1", total_months=10, hypercare_months=3),
            WaveSpec(name="W2", total_months=12, hypercare_months=3)]
