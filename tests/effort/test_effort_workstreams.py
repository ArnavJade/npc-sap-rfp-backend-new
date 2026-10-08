"""Specialist workstreams: per-wave DM tables, Basis/Security/Analytics totals, snap helpers.

Snap tables, the 13 -> 39 PD per-wave Data Migration total and the analytics 56 / 11 / 0 figures are
ported from the old unit tests (test_data_migration_scope, test_basis_scope,
test_security_analytics_scope).
"""

from __future__ import annotations

import pytest

from bidcore.effort.workstreams import (
    EXCLUDED_ANALYTICS_ROW_ID, analytics_object_effort, basis_snap, build_workstream_tables, dm_snap_effort,
    security_snap, workstream_totals,
)
from bidcore.ledger.sections_effort import (
    AnalyticsObject, AnalyticsScope, BasisActivity, DataMigrationObject, SecurityActivity,
)
from bidcore.policy import get_policy

MATERIAL = DataMigrationObject(row_id="dm-1", object="Material Master", sap_module="MM", func_spec=2,
                               program_dev=1, iteration_1=3, iteration_2=3, iteration_3=3, cutover=1)


def _tables(dm=(), basis=(), security=(), analytics=(), scope=None, waves=1):
    return build_workstream_tables(list(dm), list(basis), list(security), list(analytics), scope, waves)


def test_dm_snap_matches_the_old_table():
    values = (0, 0.2, 0.5, 0.8, 1.5, 2.4, 3, 7, "2")
    assert tuple(dm_snap_effort(v, 9.0) for v in values) == (0.5, 0.5, 0.5, 1.0, 2.0, 2.0, 3.0, 4.0, 2.0)
    assert dm_snap_effort(-2, 1.0) == 1.0 and dm_snap_effort("x", 2.0) == 2.0 and dm_snap_effort(None) is None


def test_basis_snap_matches_the_old_table():
    values = (0, 0.4, 1.6, 3, "4", 9, -2)
    assert tuple(basis_snap(v) for v in values) == (1, 1, 2, 3, 4, 5, 1)
    default = get_policy().workstreams["basis"]["default_effort_days"]
    assert basis_snap("x", default) == default and basis_snap(float("nan")) is None


def test_security_snap_clamps_whole_days():
    assert [security_snap(v) for v in (0, 10.4, 150, "30")] == [1, 10, 120, 30]
    assert security_snap("n/a", 10) == 10


def test_data_migration_has_one_table_per_wave_and_counts_every_table():
    tables = _tables(dm=[MATERIAL], waves=3)
    assert len(tables.data_migration) == 3
    tables.data_migration[0][0]["cutover"] = 4.0                # tables are independent copies
    assert tables.data_migration[1][0]["cutover"] == 1.0
    assert workstream_totals(_tables(dm=[MATERIAL]))["data_migration"] == 13.0
    assert workstream_totals(_tables(dm=[MATERIAL], waves=3))["data_migration"] == 39.0
    assert len(_tables(dm=[MATERIAL], waves=0).data_migration) == 1


def test_data_migration_row_shape_and_status_is_not_consulted():
    out = MATERIAL.model_copy(update={"row_id": "dm-2", "status": "Out of Scope", "category": "Sales data"})
    tables = _tables(dm=[MATERIAL, out])
    row = tables.data_migration[0][1]
    assert {"row_id", "object", "status", "func_spec", "program_dev", "iteration_1", "iteration_2",
            "iteration_3", "cutover"} <= set(row)
    assert row["label"] == "Sales data - Material Master" and tables.data_migration[0][0]["label"] == "Material Master"
    # The sheet's row formula is =SUM(C:H) whatever the status says, so the total does the same.
    assert workstream_totals(tables)["data_migration"] == 26.0


def test_basis_out_of_scope_rows_carry_no_effort():
    tables = _tables(basis=[BasisActivity(row_id="b1", activity="Transports", dev=2, qa=1, prd=1),
                            BasisActivity(row_id="b2", activity="DR", status="Out of Scope", dev=3, qa=3, prd=3)])
    assert tables.basis[1] == {"row_id": "b2", "activity": "DR", "status": "Out of Scope",
                               "dev": None, "qa": None, "prd": None}
    assert workstream_totals(tables)["basis"] == 4.0


def test_security_counts_in_scope_man_days_only():
    tables = _tables(security=[SecurityActivity(row_id="s1", activity="Roles", effort_days=20, complexity="High"),
                               SecurityActivity(row_id="s2", activity="GRC", status="Out of Scope", effort_days=30)])
    assert tables.security[1]["effort_days"] is None
    assert workstream_totals(tables)["security"] == 20.0


def _obj(**kw) -> AnalyticsObject:
    return AnalyticsObject(**{"row_id": "a1", "object": "x", **kw})


def test_analytics_object_effort_uses_template_rates():
    model = analytics_object_effort(_obj(object_type="Model", complexity="High", no_of_objects=2))
    assert model == {"devlp": 40.0, "unit_testing": 10.0, "qa_testing": 6.0, "total": 56.0}
    assert analytics_object_effort(_obj(object_type="CDS View", complexity="Low"))["total"] == 11.0
    assert analytics_object_effort(_obj(status="Out of Scope"))["total"] == 0.0
    assert analytics_object_effort({"status": "In Scope", "object_type": "Odd", "complexity": "?",
                                    "no_of_objects": 1})["total"] == 16.0      # Report / Medium fallback


def test_analytics_standard_factor_applies_to_standard_content_only():
    p = get_policy()
    p = p.model_copy(update={"workstreams": {**p.workstreams,
                                             "analytics": {**p.workstreams["analytics"], "standard_factor": 0.5}}})
    standard = analytics_object_effort(_obj(build="Standard", complexity="Medium"), p)
    assert standard["total"] == 8.0
    assert analytics_object_effort(_obj(build="Custom", complexity="Medium"), p)["total"] == 16.0


def test_analytics_rows_carry_computed_effort_and_total():
    tables = _tables(analytics=[_obj(object_type="Model", complexity="High", no_of_objects=2)])
    row = tables.analytics[0]
    assert (row["row_id"], row["total"], row["devlp"]) == ("a1", 56.0, 40.0)
    assert workstream_totals(tables)["analytics"] == 56.0 and not tables.analytics_excluded


def test_excluded_analytics_forces_every_row_out_of_scope():
    tables = _tables(analytics=[_obj(complexity="High")], scope=AnalyticsScope(excluded=True))
    assert tables.analytics_excluded and tables.analytics[0]["status"] == "Out of Scope"
    assert workstream_totals(tables)["analytics"] == 0.0


def test_excluded_analytics_without_objects_writes_a_marker_row():
    tables = _tables(scope=AnalyticsScope(excluded=True))
    (row,) = tables.analytics
    assert row["row_id"] == EXCLUDED_ANALYTICS_ROW_ID and row["object"] == "Analytics (entire scope)"
    assert row["status"] == "Out of Scope" and row["total"] == 0.0


def test_empty_workstreams_total_zero():
    assert workstream_totals(_tables()) == {"data_migration": 0.0, "basis": 0.0, "security": 0.0, "analytics": 0.0}


@pytest.mark.parametrize("value", [0.5, 1, 2.0, 3, 4])
def test_allowed_dm_values_are_fixed_points(value):
    assert dm_snap_effort(value) == float(value)
