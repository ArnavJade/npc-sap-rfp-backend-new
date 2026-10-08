"""The "Summary of Project Effort" ladder: scope totals -> build -> phase add-ons -> risk -> cost.

Ported from write_effort_workbook.stamp_summary_on_result, including its rounding order, so the
Python figures equal what the workbook's formulas show (Final Prep / Go-Live / PM are % of Total Build
Effort; Risk Contingency = Summary of Imp x (risk factor - 1)). Cost bills everything except hypercare
at the blended daily rate and hypercare at the single flat hypercare rate the proposal quotes.
Reviewer edits to the % / rates side table arrive as `pct_overrides`.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from bidcore.policy import Policy, get_policy

OVERRIDE_KEYS = ("final_prep_pct", "go_live_pct", "project_mgmt_pct", "risk_factor",
                 "daily_rate_usd", "hypercare_rate_usd")


class SummaryLadder(BaseModel):
    functional_scope: float           # catalogue + non-catalogue SAP tools
    data_migration: float
    tech_dev: float
    security: float
    basis: float
    analytics: float
    total_build: float                # "Total Build Effort (Upto Realization Phase)"
    final_prep: float
    go_live: float
    project_mgmt: float
    hypercare: float
    summary_of_imp: float
    risk_contingency: float
    total_project_effort: float
    daily_rate_usd: float
    hypercare_rate_usd: float
    total_project_cost_usd: float
    final_prep_pct: float
    go_live_pct: float
    project_mgmt_pct: float
    risk_factor: float


def _settings(policy: Policy, overrides: Mapping[str, object] | None) -> dict[str, float]:
    ladder, commercials = policy.commercials.summary_ladder, policy.commercials
    values = {
        "final_prep_pct": ladder.final_prep_pct, "go_live_pct": ladder.go_live_pct,
        "project_mgmt_pct": ladder.project_mgmt_pct, "risk_factor": ladder.risk_factor,
        "daily_rate_usd": commercials.daily_rate_usd, "hypercare_rate_usd": commercials.hypercare.flat_rate_usd,
    }
    for key, value in (overrides or {}).items():
        if key not in OVERRIDE_KEYS:
            raise ValueError(f"unknown summary override '{key}'; expected one of {list(OVERRIDE_KEYS)}")
        if value is None:
            continue
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"summary override {key}={value!r} is not a number") from None
        if number != number or number < 0:
            raise ValueError(f"summary override {key}={value!r} must be >= 0")
        values[key] = number
    return {k: float(v) for k, v in values.items()}


def compute_summary(functional_scope: float, data_migration: float, tech_dev: float, security: float,
                    basis: float, analytics: float, hypercare: float, policy: Policy | None = None,
                    pct_overrides: Mapping[str, object] | None = None) -> SummaryLadder:
    """The ladder, rounded at each step exactly as the old stamp_summary_on_result did."""
    s = _settings(policy or get_policy(), pct_overrides)
    # The old caller handed functional scope and Tech Dev in already rounded; the four specialist
    # totals entered the build sum raw and were rounded only for display.
    functional = round(functional_scope or 0.0, 2)
    tech = round(tech_dev or 0.0, 2)
    dm, sec, bas, ana = (x or 0.0 for x in (data_migration, security, basis, analytics))
    hypercare_md = round(hypercare or 0.0, 2)

    build = round(functional + tech + dm + sec + bas + ana, 2)
    final_prep = round(build * (s["final_prep_pct"] / 100.0), 2)
    go_live = round(build * (s["go_live_pct"] / 100.0), 2)
    project_mgmt = round(build * (s["project_mgmt_pct"] / 100.0), 2)
    summary_of_imp = round(build + final_prep + go_live + project_mgmt + hypercare_md, 2)
    risk = round(summary_of_imp * (s["risk_factor"] - 1.0), 2)
    total = round(summary_of_imp + risk, 2)
    cost = round((total - hypercare_md) * s["daily_rate_usd"] + hypercare_md * s["hypercare_rate_usd"], 2)

    return SummaryLadder(
        functional_scope=functional, data_migration=round(dm, 2), tech_dev=tech, security=round(sec, 2),
        basis=round(bas, 2), analytics=round(ana, 2), total_build=build, final_prep=final_prep,
        go_live=go_live, project_mgmt=project_mgmt, hypercare=hypercare_md, summary_of_imp=summary_of_imp,
        risk_contingency=risk, total_project_effort=total, daily_rate_usd=s["daily_rate_usd"],
        hypercare_rate_usd=s["hypercare_rate_usd"], total_project_cost_usd=cost,
        final_prep_pct=s["final_prep_pct"], go_live_pct=s["go_live_pct"],
        project_mgmt_pct=s["project_mgmt_pct"], risk_factor=s["risk_factor"],
    )
