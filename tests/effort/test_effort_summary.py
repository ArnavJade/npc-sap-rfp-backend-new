"""Summary of Project Effort ladder (stamp_summary_on_result): percentages, risk, cost, rounding order."""

from __future__ import annotations

import pytest

from bidcore.effort.summary import compute_summary


def test_the_reference_ladder():
    s = compute_summary(1000.0, 0, 0, 0, 0, 0, hypercare=100.0)
    assert (s.total_build, s.final_prep, s.go_live, s.project_mgmt) == (1000.0, 80.0, 50.0, 80.0)
    assert (s.summary_of_imp, s.risk_contingency, s.total_project_effort) == (1310.0, 131.0, 1441.0)
    assert s.total_project_cost_usd == (1441 - 100) * 320 + 100 * 360
    assert (s.daily_rate_usd, s.hypercare_rate_usd) == (320.0, 360.0)
    assert (s.final_prep_pct, s.go_live_pct, s.project_mgmt_pct, s.risk_factor) == (8.0, 5.0, 8.0, 1.1)


def test_build_sums_the_six_scope_rows():
    s = compute_summary(600.0, 39.0, 396.2, 20.0, 4.0, 56.0, hypercare=0.0)
    assert s.total_build == 1115.2
    assert (s.functional_scope, s.data_migration, s.tech_dev, s.security, s.basis, s.analytics) == (
        600.0, 39.0, 396.2, 20.0, 4.0, 56.0)


def test_each_step_is_rounded_before_the_next():
    # Unrounded steps would give fp = pm = 98.752 and a 1752.99 total; the workbook gives 1752.98.
    s = compute_summary(1234.4, 0, 0, 0, 0, 0, hypercare=100.0)
    assert (s.final_prep, s.go_live, s.project_mgmt) == (98.75, 61.72, 98.75)
    assert (s.summary_of_imp, s.risk_contingency, s.total_project_effort) == (1593.62, 159.36, 1752.98)
    assert s.total_project_cost_usd == 564953.6


def test_reviewer_overrides_replace_the_policy_side_table():
    s = compute_summary(1000.0, 0, 0, 0, 0, 0, hypercare=0.0,
                        pct_overrides={"final_prep_pct": 10, "go_live_pct": None, "risk_factor": 1.2,
                                       "daily_rate_usd": 300})
    assert (s.final_prep, s.go_live, s.project_mgmt) == (100.0, 50.0, 80.0)
    assert (s.summary_of_imp, s.risk_contingency, s.total_project_effort) == (1230.0, 246.0, 1476.0)
    assert s.total_project_cost_usd == 1476.0 * 300 and s.final_prep_pct == 10.0


@pytest.mark.parametrize("overrides", [{"risk": 1.2}, {"final_prep_pct": "ten"}, {"daily_rate_usd": -1}])
def test_bad_overrides_are_rejected(overrides):
    with pytest.raises(ValueError):
        compute_summary(1000.0, 0, 0, 0, 0, 0, 0, pct_overrides=overrides)
