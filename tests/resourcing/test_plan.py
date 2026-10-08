"""Resource plan invariants: conservation of allocated effort, FTE grain, rebalance targets, seeded sync."""

from __future__ import annotations

import copy

import pytest

from bidcore.effort.waves import allocate
from bidcore.resourcing import price_plan, rebalance_plan_to_effort_summary, sync_scope_tables
from bidcore.sizing import size_bid
from tests.fixtures_bid import build_ledger
from tests.resourcing.builders import DAYS, POLICY, cells_md, make_plan, two_waves  # noqa: F401


@pytest.mark.parametrize("total,weights", [(100.0, [1, 1, 1]), (33.33, [0.7, 0.3]), (0.05, [1, 2, 3]),
                                           (1234.56, [0.12, 0.5, 0.38])])
def test_allocate_conserves_the_total(total, weights):
    parts = allocate(total, weights)
    assert round(sum(parts), 2) == round(total, 2) and all(p >= 0 for p in parts)


def test_every_cell_is_on_the_grain(two_waves):  # noqa: F811
    plan = make_plan(two_waves, [{"Finance": 300.0}, {"Finance": 120.0}], programme_months=12)
    grain = POLICY.resourcing.fte_grain
    for grid in plan.grids:
        for row in grid.rows:
            for cell in row.cells:
                assert abs(cell.fte / grain - round(cell.fte / grain)) < 1e-9, (row.role_title, cell.fte)


def test_rebalance_brings_module_rows_to_the_build_target(two_waves):  # noqa: F811
    plan = make_plan(two_waves, [{"Finance": 600.0}, {"Finance": 400.0}], programme_months=12)
    rebalance_plan_to_effort_summary(plan, total_build_effort=1000.0, hypercare_effort_days=60.0)
    price_plan(plan)
    excluded = POLICY.resourcing.programme_role_titles | set(POLICY.resourcing.category_consultants.values())
    build_phases = set(POLICY.resourcing.phases)
    module = cells_md(plan, lambda row, cell: row.role_title not in excluded and cell.phase in build_phases)
    # module target 1000 PD (no categories) + FP/GL 13 % spread on module Deploy cells, then 0.5-FTE rounding
    assert 1000 <= module <= 1130 + DAYS * 0.5 * sum(g.months for g in plan.grids)


def test_scope_sync_is_deterministic_per_seed():
    ledger = build_ledger()
    a, b = size_bid(ledger), size_bid(copy.deepcopy(ledger))
    assert a.effort.workstreams == b.effort.workstreams and a.summary == b.summary


def test_scope_sync_moves_tables_into_the_grid_band():
    sizing = size_bid(build_ledger())
    notes = " ".join(sizing.notes)
    sec_grid = sum(r.total_man_months for g in sizing.plan.grids for r in g.rows
                   if r.role_title == POLICY.resourcing.category_consultants["security"]) * DAYS
    if "Security:" in notes:
        assert sec_grid <= sizing.totals["security"] <= sec_grid + POLICY.resourcing.scope_sync.max_variance_days


def test_sync_lays_out_missing_category_rows_from_their_tables():
    sizing = size_bid(build_ledger())
    tables = copy.deepcopy(sizing.effort.workstreams)
    plan = copy.deepcopy(sizing.plan)
    titles = set(POLICY.resourcing.category_consultants.values())
    for grid in plan.grids:
        grid.rows = [r for r in grid.rows if r.role_title not in titles]
    before = copy.deepcopy(tables)
    notes = sync_scope_tables(plan, tables, POLICY, seed="x")
    laid_out = {r.role_title for g in plan.grids for r in g.rows if r.role_title in titles}
    assert POLICY.resourcing.category_consultants["security"] in laid_out
    assert any("laid out" in n for n in notes)
    assert tables.analytics == before.analytics            # rate-driven: never moved
