"""Stable figure keys for the proposal: {{fig:<key>}}, {{table:<key>}}, {{diagram:<key>}}.

Computed once from the sizing result and stored in ledger.figures, so section writers reference a
number by key and the renderer fills it - no figure is ever typed by a model. `counts` are the small
facts (wave count, weeks, countries) a draft may state as bare numbers.
"""

from __future__ import annotations

from typing import Any

from bidcore.ledger.models import Ledger
from bidcore.sizing import SizingResult

TABLE_KEYS = ("module_summary", "functional_scope", "resource_plan", "raci", "role_roster", "effort", "cost",
              "wave_plan", "integrations", "data_migration", "tech_dev")
INDICATIVE_GROUPS = ("module", "wave", "country", "role", "workstream")
DIAGRAM_KEYS = ("timeline", "methodology", "architecture")

# Which disclosure category withholds a placeholder (category names from the Disclosure model).
WITHHELD_BY = {
    "commercial_detail": {"fig:total_project_cost", "fig:daily_rate", "fig:hypercare_rate", "table:cost"},
    "effort_detail": {"fig:total_project_effort", "fig:total_build_effort", "fig:functional_scope_effort",
                      "fig:tech_dev_effort", "fig:data_migration_effort", "fig:security_effort",
                      "fig:basis_effort", "fig:analytics_effort", "fig:hypercare_effort", "fig:final_prep_effort",
                      "fig:go_live_effort", "fig:project_mgmt_effort", "fig:risk_contingency_effort",
                      "fig:summary_of_imp_effort", "table:effort", "table:functional_scope",
                      *(f"table:indicative_breakdown:{g}" for g in INDICATIVE_GROUPS)},
    "resource_allocation": {"table:resource_plan", "fig:peak_fte", "fig:total_man_months"},
    "resource_location": {"table:role_roster"},
    "scope_item_detail": {"fig:scope_item_count", "table:functional_scope"},
}


def _pd(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".") + " person-days"


def _usd(value: float) -> str:
    return f"USD {value:,.0f}"


def compute_figures(ledger: Ledger, sizing: SizingResult) -> dict[str, Any]:
    s, t, plan = sizing.summary, sizing.timeline, sizing.plan
    scope_ids = {r.scope_item_id for r in ledger.scope_items.rows if r.status != "excluded_existing"}
    countries = ledger.rfp_profile.data.countries if ledger.rfp_profile.data else []
    fig = {
        "total_project_effort": _pd(s.total_project_effort),
        "total_project_cost": _usd(s.total_project_cost_usd),
        "total_build_effort": _pd(s.total_build),
        "functional_scope_effort": _pd(s.functional_scope),
        "tech_dev_effort": _pd(s.tech_dev),
        "data_migration_effort": _pd(s.data_migration),
        "security_effort": _pd(s.security),
        "basis_effort": _pd(s.basis),
        "analytics_effort": _pd(s.analytics),
        "hypercare_effort": _pd(s.hypercare),
        "final_prep_effort": _pd(s.final_prep),
        "go_live_effort": _pd(s.go_live),
        "project_mgmt_effort": _pd(s.project_mgmt),
        "risk_contingency_effort": _pd(s.risk_contingency),
        "summary_of_imp_effort": _pd(s.summary_of_imp),
        "daily_rate": f"USD {s.daily_rate_usd:,.0f} per person-day",
        "hypercare_rate": f"USD {s.hypercare_rate_usd:,.0f} per person-day",
        "programme_months": f"{t.programme_months} months",
        "programme_weeks": f"{t.programme_weeks:g} weeks",
        "wave_count": str(len(t.waves)),
        "country_count": str(len(countries)),
        "lob_count": str(len(sizing.effort.modules)),
        "scope_item_count": str(len(scope_ids)),
        "integration_count": str(len(ledger.integrations.rows)),
        "peak_fte": f"{plan.peak_fte:g} FTE",
        "total_man_months": f"{plan.grand_total_mm:g} man-months",
    }
    counts = {
        "waves": len(t.waves), "countries": len(countries), "lobs": len(sizing.effort.modules),
        "integrations": len(ledger.integrations.rows), "programme_months": t.programme_months,
        "wave_weeks": sorted({w.total_weeks for w in t.waves} | {w.hypercare_weeks for w in t.waves}),
        "wave_months": sorted({w.total_months for w in t.waves} | {w.hypercare_months for w in t.waves}),
    }
    roles: dict[str, dict] = {}
    for grid in plan.grids:
        for row in grid.rows:
            entry = roles.setdefault(row.role_title, {"role": row.role_title, "location": row.location,
                                                      "kind": row.entity_kind, "waves": []})
            entry["waves"].append(grid.wave_name)
    return {
        "fig": fig,
        "roles": list(roles.values()),
        "tables": [*TABLE_KEYS, *(f"indicative_breakdown:{g}" for g in INDICATIVE_GROUPS)],
        "diagrams": list(DIAGRAM_KEYS),
        "counts": counts,
        "summary": s.model_dump(),
        "waves": [{"name": w.name, "total_weeks": w.total_weeks, "hypercare_weeks": w.hypercare_weeks,
                   "months": w.total_months, "countries": w.countries, "kind": w.kind,
                   "duration_source": w.duration_source, "go_live": w.go_live} for w in t.waves],
        "notes": sizing.notes,
    }


def withheld_keys(withheld_categories: list[str]) -> set[str]:
    out: set[str] = set()
    for category in withheld_categories:
        out |= WITHHELD_BY.get(category, set())
    return out


def known_placeholder(key: str) -> bool:
    kind, _, name = key.partition(":")
    if kind == "fig":
        return True   # validated against ledger.figures["fig"] by the caller
    if kind == "table":
        return name in TABLE_KEYS or (name.startswith("indicative_breakdown:")
                                      and name.split(":", 1)[1] in INDICATIVE_GROUPS)
    return kind == "diagram" and name in DIAGRAM_KEYS
