"""Ledger-driven proposal tables ({{table:<key>}}): headers + rows, every figure from the sizing result.

No model writes these. Disclosure is applied by the caller (a withheld table is never built), and
within a table a withheld column (e.g. resource location) is dropped here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from bidcore.ledger.models import Ledger
from bidcore.sizing import SizingResult


@dataclass
class TableData:
    title: str
    headers: list[str]
    rows: list[list[str]]
    total_row: bool = False                    # last row is a total (bold)
    widths: list[float] = field(default_factory=list)   # relative column widths


def _pd(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _usd(value: float) -> str:
    return f"{value:,.0f}"


def _module_summary(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    show_effort = "effort_detail" not in withheld
    headers = ["Line of Business", "Business Areas", "Scope Items"] + (["Effort (Person Days)"] if show_effort else [])
    rows = []
    for lob, module in sizing.effort.modules.items():
        if not module.rows:
            continue
        areas = sorted({r.business_area for r in module.rows})
        ids = {r.scope_id for r in module.rows}
        row = [lob, ", ".join(areas), str(len(ids))]
        if show_effort:
            row.append(_pd(module.total_effort))
        rows.append(row)
    for item in sizing.effort.non_catalogue:
        rows.append([item.name, item.label or "SAP tool", "-"] + ([_pd(item.effort_days)] if show_effort else []))
    return TableData("Functional scope by line of business", headers, rows, widths=[3, 5, 1.5, 2][:len(headers)])


def _functional_scope(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    countries_by_item: dict[tuple[str, str], set[str]] = defaultdict(set)
    meta: dict[tuple[str, str], tuple[str, str]] = {}
    for module in sizing.effort.modules.values():
        for r in module.rows:
            key = (r.lob, r.scope_id)
            countries_by_item[key].add(r.country or "All")
            meta[key] = (r.business_area, r.description)
    rows = [[lob, meta[(lob, sid)][0], sid, meta[(lob, sid)][1], ", ".join(sorted(countries_by_item[(lob, sid)]))]
            for (lob, sid) in sorted(meta)]
    return TableData("Best Practice scope items", ["Line of Business", "Business Area", "Scope Item", "Description",
                                                   "Countries"], rows, widths=[2.5, 3, 1.2, 5, 1.5])


def _effort(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    s = sizing.summary
    rows = [["Functional Scope", _pd(s.functional_scope)], ["Data Migration", _pd(s.data_migration)],
            ["Technical Development (RICEFW, Fiori, Integrations)", _pd(s.tech_dev)], ["Security", _pd(s.security)],
            ["Basis & Solution Manager", _pd(s.basis)], ["Analytics", _pd(s.analytics)],
            ["Total Build Effort", _pd(s.total_build)], ["Final Preparation", _pd(s.final_prep)],
            ["Go-Live", _pd(s.go_live)], ["Project Management", _pd(s.project_mgmt)], ["Hypercare", _pd(s.hypercare)],
            ["Risk Contingency", _pd(s.risk_contingency)], ["Total Project Effort", _pd(s.total_project_effort)]]
    return TableData("Effort estimate", ["Effort Category", "Effort (Person Days)"], rows, total_row=True,
                     widths=[5, 2])


def _cost(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    s = sizing.summary
    impl = round(s.total_project_effort - s.hypercare, 2)
    rows = [["Implementation services", _pd(impl), _usd(s.daily_rate_usd), _usd(impl * s.daily_rate_usd)],
            ["Hypercare support", _pd(s.hypercare), _usd(s.hypercare_rate_usd), _usd(s.hypercare * s.hypercare_rate_usd)],
            ["Total", _pd(s.total_project_effort), "", _usd(s.total_project_cost_usd)]]
    return TableData("Cost estimate (USD)", ["Item", "Effort (Person Days)", "Rate (USD per day)", "Cost (USD)"],
                     rows, total_row=True, widths=[4, 2, 2, 2])


def _resource_plan(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    waves = [g.wave_name for g in sizing.plan.grids]
    show_location = "resource_location" not in withheld
    totals: dict[tuple[str, str], list[float]] = {}
    for i, grid in enumerate(sizing.plan.grids):
        for row in grid.rows:
            totals.setdefault((row.role_title, row.location), [0.0] * len(waves))[i] += row.total_man_months
    headers = ["Role"] + (["Location"] if show_location else []) + [f"{w} (MM)" for w in waves] + ["Total (MM)"]
    rows = []
    for (role, location), per_wave in totals.items():
        rows.append([role] + ([location] if show_location else []) + [f"{v:g}" if v else "-" for v in per_wave]
                    + [f"{round(sum(per_wave), 2):g}"])
    grand = [round(g.grand_total_mm, 2) for g in sizing.plan.grids]
    rows.append(["Total"] + ([""] if show_location else []) + [f"{v:g}" for v in grand] + [f"{round(sum(grand), 2):g}"])
    return TableData("Resource plan (man-months per wave)", headers, rows, total_row=True)


def _role_roster(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    show_location = "resource_location" not in withheld
    roles: dict[str, dict] = {}
    for grid in sizing.plan.grids:
        for row in grid.rows:
            entry = roles.setdefault(row.role_title, {"locations": set(), "waves": []})
            entry["locations"].add(row.location)
            if grid.wave_name not in entry["waves"]:
                entry["waves"].append(grid.wave_name)
    headers = ["Role"] + (["Location"] if show_location else []) + ["Waves"]
    rows = [[role] + ([" / ".join(sorted(e["locations"]))] if show_location else []) + [", ".join(e["waves"])]
            for role, e in roles.items()]
    return TableData("Project roles", headers, rows, widths=[4, 2, 3][:len(headers)])


RACI_ROWS = [
    ("Project governance and steering", "A/R", "A/R"),
    ("Project planning and status reporting", "R", "C/I"),
    ("Business requirements and process sign-off", "C", "A/R"),
    ("Solution design (fit-to-standard workshops)", "A/R", "C"),
    ("System configuration and build", "A/R", "I"),
    ("Custom development (RICEFW, Fiori)", "A/R", "C"),
    ("Third-party system changes and interfaces (client side)", "C", "A/R"),
    ("Data cleansing and extraction from legacy systems", "C", "A/R"),
    ("Data transformation and load", "A/R", "C"),
    ("Unit and integration testing", "A/R", "C"),
    ("User acceptance testing", "C", "A/R"),
    ("Key-user training", "A/R", "C"),
    ("End-user training", "C", "A/R"),
    ("Cutover planning and execution", "A/R", "C"),
    ("Infrastructure and hosting provisioning", "C", "A/R"),
    ("Hypercare support", "A/R", "C"),
]


def _raci(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    return TableData("RACI matrix (R = Responsible, A = Accountable, C = Consulted, I = Informed)",
                     ["Activity", "YASH", ledger.meta.client_name or "Client"],
                     [list(r) for r in RACI_ROWS], widths=[6, 1.5, 1.5])


def _wave_plan(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    t = sizing.timeline
    rows = [[w.name, ", ".join(w.countries) or "-", f"M{t.wave_start_month(w) + 1}", f"{w.total_weeks:g}",
             f"{w.hypercare_weeks:g}", w.go_live or "-"] for w in t.waves]
    return TableData("Delivery waves", ["Wave", "Countries", "Starts", "Duration (weeks)", "Hypercare (weeks)",
                                        "Go-live"], rows, widths=[2, 3, 1, 1.5, 1.5, 2])


def _integrations(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    rows = [[r.system, r.functionality or "-", r.direction, r.middleware or "-", ", ".join(r.sap_modules) or "-"]
            for r in ledger.integrations.rows]
    return TableData("Third-party integrations", ["System", "Purpose", "Direction", "Middleware", "SAP Modules"],
                     rows, widths=[2, 4, 1.5, 1.5, 2])


def _data_migration(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    rows = [[r.object, r.category, r.sap_module or "-", r.status] for r in ledger.data_migration.rows]
    return TableData("Data migration objects", ["Object", "Category", "SAP Module", "Scope"], rows)


def _tech_dev(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
    rows = [[r.object_name, r.object_type, str(r.no_of_objects), r.complexity] for r in sizing.effort.tech_dev]
    return TableData("Technical development objects", ["Object", "Type", "Count", "Complexity"], rows)


def _indicative(group: str):
    def build(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> TableData:
        rows: list[list[str]] = []
        unit = "Effort (Person Days)"
        if group == "module":
            rows = [[lob, _pd(m.total_effort)] for lob, m in sizing.effort.modules.items() if m.total_effort]
            rows += [[n.name, _pd(n.effort_days)] for n in sizing.effort.non_catalogue]
            label = "Module"
        elif group == "wave":
            rows = [[name, _pd(sizing.wave_effort.wave_total(i))] for i, name in enumerate(sizing.wave_effort.wave_names)]
            label = "Wave"
        elif group == "country":
            by_country: dict[str, float] = defaultdict(float)
            for m in sizing.effort.modules.values():
                for r in m.rows:
                    by_country[r.country or "All countries"] += r.total
            rows = [[c, _pd(v)] for c, v in sorted(by_country.items())]
            label = "Country (functional scope)"
        elif group == "role":
            totals: dict[str, float] = defaultdict(float)
            for g in sizing.plan.grids:
                for r in g.rows:
                    totals[r.role_title] += r.total_man_months
            rows = [[role, f"{round(v, 2):g}"] for role, v in totals.items()]
            label, unit = "Role", "Man-months"
        else:
            return _effort(ledger, sizing, withheld)
        return TableData(f"Indicative effort by {group}", [label, unit], rows)
    return build


BUILDERS = {
    "module_summary": _module_summary, "functional_scope": _functional_scope, "effort": _effort, "cost": _cost,
    "resource_plan": _resource_plan, "role_roster": _role_roster, "raci": _raci, "wave_plan": _wave_plan,
    "integrations": _integrations, "data_migration": _data_migration, "tech_dev": _tech_dev,
    **{f"indicative_breakdown:{g}": _indicative(g) for g in ("module", "wave", "country", "role", "workstream")},
}


def build_table(key: str, ledger: Ledger, sizing: SizingResult, withheld_categories: list[str]) -> TableData | None:
    builder = BUILDERS.get(key)
    return builder(ledger, sizing, set(withheld_categories)) if builder else None
