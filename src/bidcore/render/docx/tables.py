"""Ledger-driven proposal tables ({{table:<key>}}), ported from the old generator's table builders
(document_generator_layer5: add_module_effort_summary_table, add_functional_scope_tables,
add_effort_estimation_tables, add_resource_plan_tables, add_combined_staffing_table,
add_role_roster_table, add_cost_estimation_table, add_raci_matrix_table).

Every figure comes from the sizing result; no model writes these. Disclosure is applied here per
table the way the old builders did it: a withheld category drops its columns (scope-item counts,
effort, location), replaces the resource grids with a Phase | Skill view (allocation), or withholds
the table (cost without commercial detail, role roster without allocation).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from bidcore.ledger.models import Ledger
from bidcore.policy import get_policy
from bidcore.sizing import SizingResult

SCOPE_ITEMS, EFFORT, ALLOCATION, LOCATION, COMMERCIAL = (
    "scope_item_detail", "effort_detail", "resource_allocation", "resource_location", "commercial_detail")


@dataclass
class TableData:
    title: str                                   # caption ("" = none)
    headers: list[str]
    rows: list[list[str]]
    subheading: str = ""                         # level-3 heading above the table
    intro: str = ""                              # small paragraph before the table
    note: str = ""                               # small italic note after the table
    band_row: list[str] | None = None            # phase band row under the header
    subtotal_rows: set[int] = field(default_factory=set)
    widths: list[float] = field(default_factory=list)   # inches
    landscape: bool = False
    top_header: str = ""                         # merged banner above the header


def _g(value: float) -> str:
    return f"{round(value, 2):g}"


def _usd(value: float) -> str:
    return f"{value:,.2f}"


def _days_per_month() -> int:
    return get_policy().commercials.working_days_per_month


# --------------------------------------------------------------------------- scope

def module_summary(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    """3.1: the workbook's Functional Scope Estimation block (module -> business area)."""
    modules = {lob: m for lob, m in sizing.effort.modules.items() if m.rows}
    if not modules:
        return []
    rows: list[list[str]] = []
    for lob, module in sorted(modules.items()):
        rows.append([lob, "All business areas", str(module.bp_id_count), _g(module.total_effort)])
        areas: dict[str, list] = {}
        for row in module.rows:
            bucket = areas.setdefault(row.business_area or "Other", [0.0, 0])
            bucket[0] += row.total
            bucket[1] += 1
        for area, (days, count) in sorted(areas.items(), key=lambda kv: -kv[1][0]):
            rows.append(["", area, str(count), _g(days)])
    rows.append(["Total", "", str(sum(m.bp_id_count for m in modules.values())), _g(sizing.effort.core_bp_effort)])
    show_count, show_effort = SCOPE_ITEMS not in withheld, EFFORT not in withheld
    keep = [0, 1] + ([2] if show_count else []) + ([3] if show_effort else [])
    headers = [["Module", "Business Area", "SAP Scope Items", "Effort (person-days)"][i] for i in keep]
    has_total = show_count or show_effort
    body = rows if has_total else rows[:-1]
    note = ("Scope-item counts and effort are the approved figures from the effort estimate; the individual "
            "SAP Best Practice scope items behind them are listed in the functional scope section."
            if show_count and show_effort else "")
    return [TableData("", headers, [[r[i] for i in keep] for r in body],
                      subtotal_rows={len(body) - 1} if has_total else set(), note=note)]


def functional_scope(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    """3.2: one table per LOB (Scope Item ID only when disclosed) + the non-catalogue items."""
    show_ids = SCOPE_ITEMS not in withheld
    headers = (["Scope Item ID"] if show_ids else []) + ["Business Area", "Description"]
    out = []
    for lob, module in sorted(sizing.effort.modules.items()):
        seen, rows = set(), []
        for r in module.rows:
            key = (r.scope_id or "-", r.description)
            if key in seen:
                continue
            seen.add(key)
            rows.append(([r.scope_id or "-"] if show_ids else []) + [r.business_area, r.description])
        if rows:
            out.append(TableData("", headers, rows, subheading=f"Functional Scope - {lob}"))
    others = list(dict.fromkeys((n.label or "Non-Catalogue", n.name) for n in sizing.effort.non_catalogue))
    if others:
        rows = [(["-"] if show_ids else []) + [label, name] for label, name in others]
        out.append(TableData("", headers, rows,
                             subheading="Functional Scope - Non-Catalogue SAP Modules & Third-Party Integrations"))
    return out


def effort(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    """6.1: Module-Wise Effort Summary (module -> business area, non-catalogue rows folded in)."""
    show_count, show_effort = SCOPE_ITEMS not in withheld, EFFORT not in withheld
    keep = [0, 1] + ([2] if show_count else []) + ([3] if show_effort else [])
    rows: list[list[str]] = []
    for lob, m in sorted(sizing.effort.modules.items()):
        if not m.rows:
            continue
        rows.append([lob, "", str(m.bp_id_count), _g(m.total_effort)])
        areas: dict[str, float] = defaultdict(float)
        ids: dict[str, set] = defaultdict(set)
        for r in m.rows:
            areas[r.business_area or "Other"] += r.total
            ids[r.business_area or "Other"].add(r.scope_id)
        for area in sorted(areas, key=lambda a: -areas[a]):
            rows.append(["", area, str(len(ids[area])), _g(areas[area])])
    tools = sizing.effort.non_catalogue
    if tools:
        total = sizing.effort.non_catalogue_effort
        rows.append(["Non-Catalogue SAP Tools & External Integrations", "", str(len(tools)),
                     f"~{_g(total)} (indicative)" if total else "Not estimated"])
        for t in tools:
            label = f"{t.name} ({t.description})" if t.description else t.name
            rows.append(["", label, "-", f"~{_g(t.effort_days)} (indicative)" if t.effort_days else "Not estimated"])
    headers = [["Module", "Business Area", "BP ID Count", "Total Effort (Person Days)"][i] for i in keep]
    note = ""
    if show_effort and tools and sizing.effort.non_catalogue_effort:
        note = (f"Includes {_g(sizing.effort.non_catalogue_effort)} indicative person-day(s) across {len(tools)} "
                "non-catalogue SAP tool(s)/external integration(s) identified in the RFP (see breakdown in the "
                "module-wise table above); these are estimates subject to refinement during the Prepare phase.")
    return [TableData("", headers, [[r[i] for i in keep] for r in rows], subheading="Module-Wise Effort Summary",
                      note=note)]


def cost(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    """6.2: the Summary of Project Effort's commercial roll-up (withheld without commercial detail)."""
    if COMMERCIAL in withheld:
        return []
    s = sizing.summary
    implementation = round(s.total_project_effort - s.hypercare, 2)
    rows = []
    if EFFORT not in withheld:
        rows.append(["Total Project Effort (Person Days)", _g(s.total_project_effort)])
        if s.hypercare:
            rows.append(["Hypercare Effort (Person Days)", _g(s.hypercare)])
            rows.append(["Implementation Effort (Person Days, ex-Hypercare)", _g(implementation)])
    rows.append(["Implementation Rate (USD/day, blended)", _g(s.daily_rate_usd)])
    if s.hypercare:
        rows.append(["Hypercare Rate (USD/day)", _g(s.hypercare_rate_usd)])
    rows.append(["Total Project Cost (USD)", _usd(s.total_project_cost_usd)])
    note = ""
    if sizing.effort.non_catalogue_effort:
        note = (f"Includes an indicative ${sizing.effort.non_catalogue_effort * s.daily_rate_usd:,.0f} for "
                "non-catalogue SAP tools/external integrations identified in the RFP; subject to refinement "
                "during the Prepare phase.")
    return [TableData("", ["Item", "Value"], rows, subtotal_rows={len(rows) - 1}, note=note)]


# --------------------------------------------------------------------------- resources

def _phase_skills(sizing: SizingResult) -> list[tuple[str, list[str]]]:
    """Old resource_phase_skills: per delivery phase, the skills with FTE in a month of it."""
    order: list[str] = []
    skills: dict[str, list[str]] = {}
    hypercare = get_policy().resourcing.hypercare_phase
    for grid in sizing.plan.grids:
        for month, band in enumerate(grid.phase_bands):
            label = "Hypercare" if band == hypercare else (band or "").strip()
            if not label:
                continue
            if label not in skills:
                order.append(label)
                skills[label] = []
            for row in grid.rows:
                if row.fte_at(month + 1) and row.role_title not in skills[label]:
                    skills[label].append(row.role_title)
    return [(label, skills[label]) for label in order if skills[label]]


def combined_staffing(sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    plan = sizing.plan
    if len(plan.grids) < 2 or ALLOCATION in withheld or not plan.combined_by_month:
        return []
    combined = plan.combined_by_month
    seq = "sequential" if sizing.timeline.is_sequential else "concurrent"
    active = [sum(1 for g in plan.grids if g.start_month <= i < g.start_month + g.months) for i in range(len(combined))]
    width = max(min(7.0 / max(len(combined), 1), 0.5), 0.2)
    return [TableData(
        "", ["Month"] + [f"M{i + 1}" for i in range(len(combined))] + ["Total Man-months"],
        [["Total FTE"] + [_g(v) if v else "" for v in combined] + [_g(plan.grand_total_mm)],
         ["Waves Active"] + [str(a) if a else "" for a in active] + [""]],
        subheading="Combined Programme Staffing",
        intro=(f"All {len(plan.grids)} waves on one calendar ({seq}), peaking at {_g(plan.peak_fte)} FTE across "
               f"{plan.programme_months} months."),
        subtotal_rows={0}, widths=[1.6] + [width] * len(combined) + [1.1], landscape=True)]


def resource_plan(ledger: Ledger, sizing: SizingResult, withheld: set[str],
                  combine_resource_effort: bool = True) -> list[TableData]:
    """4.4: delivery waves, then one Skill x month grid per wave (or Phase | Skill when allocation is
    withheld), the combined programme staffing, and the closing note."""
    plan, timeline = sizing.plan, sizing.timeline
    if not plan.grids:
        return []
    out: list[TableData] = []
    show_effort = EFFORT not in withheld
    if len(timeline.waves) > 1:
        names = sizing.wave_effort.wave_names
        rows = []
        for w in timeline.waves:
            row = [w.name, str(w.sequence), _g(w.total_weeks), _g(w.hypercare_weeks) if w.hypercare_weeks else "-",
                   ", ".join(w.countries) or "-"]
            if show_effort:
                i = names.index(w.name) if w.name in names else -1
                row.append(_g(sizing.wave_effort.wave_total(i)) if i >= 0 else "-")
            rows.append(row)
        span = (f"The programme spans {_g(timeline.programme_weeks)} weeks end to end" if timeline.is_sequential
                else f"The programme spans {_g(timeline.programme_weeks)} weeks, the length of the longest wave")
        out.append(TableData(
            "", ["Wave", "Sequence", "Duration (weeks)", "Hypercare (weeks)", "Countries"]
            + (["Scope Effort (person-days)"] if show_effort else []), rows, subheading="Delivery Waves",
            intro=(f"Delivery is phased into {len(timeline.waves)} waves, running "
                   f"{'back to back' if timeline.is_sequential else 'concurrently'}. {span}."),
            note=("Scope effort is apportioned to each wave by the wave plan; the wave totals therefore sum to the "
                  "approved effort.") if show_effort else ""))
    if ALLOCATION in withheld:
        skills = _phase_skills(sizing)
        if skills:
            out.append(TableData("", ["Phase", "Skill"], [[p, ", ".join(s)] for p, s in skills],
                                 subheading="Resource Plan"))
        return out
    show_location = LOCATION not in withheld
    days = _days_per_month()
    for grid in plan.grids:
        wave = next((w for w in timeline.waves if w.name == grid.wave_name), None)
        intro = ""
        if wave is not None and wave.total_weeks:
            hc = f", including {_g(wave.hypercare_weeks)} weeks of hypercare" if wave.hypercare_weeks else ""
            intro = f"{grid.wave_name}: {_g(wave.total_weeks)} weeks{hc}. One man-month is {days} working days."
        rows: list[list[str]] = []
        subtotals: set[int] = set()
        if show_location:
            headers = ["Skill", "Location"] + [f"M{i + 1}" for i in range(grid.months)] + ["Total Man-months"]
            band = ["Phase", ""] + list(grid.phase_bands) + [""]
            for location, totals, total_mm, label in (
                    ("Onsite", grid.onsite_total_by_month, grid.onsite_total_mm, "Onsite Total"),
                    ("Offshore", grid.offshore_total_by_month, grid.offshore_total_mm, "Offshore Total")):
                for row in grid.rows:
                    if row.location == location:
                        rows.append([row.role_title, row.location]
                                    + [_g(row.fte_at(i + 1)) if row.fte_at(i + 1) else "" for i in range(grid.months)]
                                    + [_g(row.total_man_months)])
                subtotals.add(len(rows))
                rows.append([label, location] + [_g(v) if v else "" for v in totals] + [_g(total_mm)])
        else:
            headers = ["Skill"] + [f"M{i + 1}" for i in range(grid.months)] + ["Total Man-months"]
            band = ["Phase"] + list(grid.phase_bands) + [""]
            merged: dict[str, list[float]] = {}
            for row in grid.rows:
                values = merged.setdefault(row.role_title, [0.0] * (grid.months + 1))
                for i in range(grid.months):
                    values[i] += row.fte_at(i + 1) or 0.0
                values[-1] += row.total_man_months
            for title, values in merged.items():
                rows.append([title] + [_g(v) if v else "" for v in values[:-1]] + [_g(values[-1])])
        subtotals.add(len(rows))
        rows.append(["Grand Total"] + ([""] if show_location else [])
                    + [_g(v) if v else "" for v in grid.grand_total_by_month] + [_g(grid.grand_total_mm)])
        month = max(min(6.0 / max(grid.months, 1), 0.55), 0.22)
        out.append(TableData(
            "", headers, rows, subheading=f"Resource Plan - {grid.wave_name}", intro=intro, band_row=band,
            subtotal_rows=subtotals, widths=([2.6, 0.8] if show_location else [3.4]) + [month] * grid.months + [1.0],
            landscape=True, top_header=f"{grid.wave_name} - Resource Plan (FTE by month)"))
    out += combined_staffing(sizing, withheld)
    total = f"Total resource commitment across all waves: {_g(plan.grand_total_mm)} man-months."
    if not show_effort:
        note = total
    elif combine_resource_effort:
        note = (f"{total} Of this, {_g(plan.additive_effort_days)} person-day(s) of lead and programme-management "
                "effort are additional to the module-level scope effort and are included in the project total; the "
                "remaining consultant capacity delivers that module effort."
                + (f" Hypercare accounts for a further {_g(plan.hypercare_effort_days)} person-day(s), priced at the "
                   "post-go-live support rates." if plan.hypercare_effort_days else ""))
    else:
        note = ("Resource commitment is shown here in man-months; module-level effort in person-days is presented "
                "separately in the effort estimation section.")
    out[-1].note = (out[-1].note + " " + note).strip()
    return out


def role_roster(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    """5.4: man-months per role per wave (withheld without allocation detail)."""
    plan = sizing.plan
    if not plan.grids or ALLOCATION in withheld:
        return []
    show_location = LOCATION not in withheld
    roster: dict[tuple[str, str], list[float]] = {}
    for index, grid in enumerate(plan.grids):
        for row in grid.rows:
            key = (row.role_title, row.location if show_location else "")
            roster.setdefault(key, [0.0] * len(plan.grids))[index] += row.total_man_months
    items = sorted(roster.items(), key=lambda kv: (0 if kv[0][1] == "Onsite" else 1, -sum(kv[1]), kv[0][0]))
    rows = [[title, location] + [_g(v) if v else "-" for v in per_wave] + [_g(sum(per_wave))]
            for (title, location), per_wave in items]
    totals = [sum(v[i] for v in roster.values()) for i in range(len(plan.grids))]
    rows.append(["Total", ""] + [_g(v) for v in totals] + [_g(plan.grand_total_mm)])
    headers = ["Role", "Location"] + [g.wave_name for g in plan.grids] + ["Total Man-months"]
    if not show_location:
        headers = [headers[0]] + headers[2:]
        rows = [[r[0]] + r[2:] for r in rows]
    return [TableData("", headers, rows, subtotal_rows={len(rows) - 1},
                      note=(f"One man-month is {_days_per_month()} working days. The month-by-month loading behind "
                            "these totals is in the project team section."))]


# --------------------------------------------------------------------------- RACI and the rest

# Ported from the old generator (RACI_*): exactly ONE "A" per row; R = Responsible, A = Accountable,
# C = Consulted, I = Informed. Modules are not rows (skills/proposal-outline/sections/4.6-raci-matrix.md).
RACI_ROLES = ["Client Sponsor", "Client SME / Core Team", "YASH Project Manager", "YASH Solution Architect",
              "YASH Consultants"]
RACI_BASE_ACTIVITIES = [
    ("Project Planning & Governance", ["A", "I", "R", "C", "I"]),
    ("Fit-to-Standard / Requirements Workshops", ["C", "R", "A", "R", "C"]),
    ("Solution Design & Blueprint Sign-off", ["A", "C", "R", "R", "C"]),
    ("Configuration & Build", ["I", "C", "A", "C", "R"]),
    ("Custom Development (WRICEF)", ["I", "C", "A", "C", "R"]),
    ("Data Migration", ["C", "R", "A", "C", "R"]),
    ("Integration Setup", ["I", "C", "A", "R", "R"]),
    ("Unit & Integration Testing", ["I", "C", "A", "C", "R"]),
    ("User Acceptance Testing (UAT)", ["A", "R", "C", "C", "C"]),
    ("Training & Organisational Change Mgmt", ["C", "R", "A", "I", "R"]),
    ("Cutover & Go-Live", ["A", "C", "R", "C", "R"]),
    ("Hypercare / Post Go-Live Support", ["I", "C", "A", "C", "R"]),
]


def raci(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    return [TableData("", ["Activity / Deliverable", *RACI_ROLES],
                      [[activity, *letters] for activity, letters in RACI_BASE_ACTIVITIES],
                      note="R = Responsible   A = Accountable   C = Consulted   I = Informed")]


def wave_plan(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    t = sizing.timeline
    rows = [[w.name, ", ".join(w.countries) or "-", f"M{t.wave_start_month(w) + 1}", _g(w.total_weeks),
             _g(w.hypercare_weeks), w.go_live or "-"] for w in t.waves]
    return [TableData("", ["Wave", "Countries", "Starts", "Duration (weeks)", "Hypercare (weeks)", "Go-live"], rows)]


def integrations(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    rows = [[r.system, r.functionality or "-", r.direction, r.middleware or "-", ", ".join(r.sap_modules) or "-"]
            for r in ledger.integrations.rows]
    return [TableData("", ["System", "Purpose", "Direction", "Middleware", "SAP Modules"], rows)] if rows else []


def data_migration(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    rows = [[r.module or "-", r.object, r.sap_module or "-", r.status] for r in ledger.data_migration.rows]
    return [TableData("", ["Area", "Object", "SAP Module", "Scope"], rows)] if rows else []


def tech_dev(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
    rows = [[r.object_name, r.object_type, str(r.no_of_objects), r.complexity] for r in sizing.effort.tech_dev]
    return [TableData("", ["Object", "Type", "Count", "Complexity"], rows)] if rows else []


def _indicative(group: str):
    def build(ledger: Ledger, sizing: SizingResult, withheld: set[str]) -> list[TableData]:
        unit = "Effort (Person Days)"
        if group == "module":
            rows = [[lob, _g(m.total_effort)] for lob, m in sizing.effort.modules.items() if m.total_effort]
            rows += [[n.name, _g(n.effort_days)] for n in sizing.effort.non_catalogue]
            label = "Module"
        elif group == "wave":
            rows = [[name, _g(sizing.wave_effort.wave_total(i))] for i, name in enumerate(sizing.wave_effort.wave_names)]
            label = "Wave"
        elif group == "country":
            by_country: dict[str, float] = defaultdict(float)
            for m in sizing.effort.modules.values():
                for r in m.rows:
                    by_country[r.country or "All countries"] += r.total
            rows, label = [[c, _g(v)] for c, v in sorted(by_country.items())], "Country (functional scope)"
        elif group == "role":
            totals: dict[str, float] = defaultdict(float)
            for g in sizing.plan.grids:
                for r in g.rows:
                    totals[r.role_title] += r.total_man_months
            rows, label, unit = [[role, _g(v)] for role, v in totals.items()], "Role", "Man-months"
        else:
            s = sizing.summary
            rows = [["Functional Scope", _g(s.functional_scope)], ["Data Migration", _g(s.data_migration)],
                    ["Tech Dev Scope", _g(s.tech_dev)], ["Security", _g(s.security)], ["BASIS & SolMan", _g(s.basis)],
                    ["Analytics", _g(s.analytics)], ["Total Build Effort", _g(s.total_build)]]
            return [TableData("", ["Workstream", unit], rows, subtotal_rows={len(rows) - 1})]
        return [TableData("", [label, unit], rows)]
    return build


BUILDERS = {
    "module_summary": module_summary, "functional_scope": functional_scope, "effort": effort, "cost": cost,
    "resource_plan": resource_plan, "role_roster": role_roster, "raci": raci, "wave_plan": wave_plan,
    "integrations": integrations, "data_migration": data_migration, "tech_dev": tech_dev,
    **{f"indicative_breakdown:{g}": _indicative(g) for g in ("module", "wave", "country", "role", "workstream")},
}


def build_tables(key: str, ledger: Ledger, sizing: SizingResult, withheld_categories: list[str],
                 combine_resource_effort: bool = True) -> list[TableData]:
    builder = BUILDERS.get(key)
    if builder is None:
        return []
    if key == "resource_plan":
        return resource_plan(ledger, sizing, set(withheld_categories), combine_resource_effort)
    return builder(ledger, sizing, set(withheld_categories))
