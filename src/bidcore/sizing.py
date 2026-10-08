"""The deterministic sizing pipeline: ledger -> every number in the workbook and the proposal.

    effort (rate card, Tech Dev, workstreams) -> timeline (durations) -> wave allocation (the
    wave-planner's decisions applied exactly) -> staffing grid -> Summary of Project Effort ladder ->
    four-pass rebalance -> scope-sheet sync -> final ladder + pricing

No LLM anywhere. Call 1 runs it after the agents finish; call 2 re-runs it after the reviewer's edits
are applied, so the Word document's figures always equal the workbook's.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict

from bidcore.effort.catalogue_effort import compute_catalogue_effort
from bidcore.effort.models import PHASE_FIELDS, EffortModel, NonCatalogueEffort, TechDevRow
from bidcore.effort.summary import SummaryLadder, compute_summary
from bidcore.effort.techdev import compute_tech_dev
from bidcore.effort.waves import WaveEffort, allocate_waves
from bidcore.effort.workstreams import build_workstream_tables, workstream_totals
from bidcore.ledger.models import Ledger
from bidcore.policy import Policy, get_policy
from bidcore.resourcing import (
    build_resource_plan, is_project_management, price_plan, rebalance_plan_to_effort_summary, sync_scope_tables,
)
from bidcore.resourcing.models import GridCell, PassWeights, ResourcePlan, WaveSpec
from bidcore.timeline.model import ResolvedTimeline
from bidcore.timeline.resolve import resolve_timeline

CATEGORY_KEYS = ("data_migration", "security", "basis", "analytics")


class SizingResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    effort: EffortModel
    timeline: ResolvedTimeline
    wave_effort: WaveEffort
    weights: PassWeights
    plan: ResourcePlan
    summary: SummaryLadder
    totals: dict[str, float]
    notes: list[str]


def bid_countries(ledger: Ledger) -> list[str]:
    profile = ledger.rfp_profile.data
    return [c.code for c in profile.countries if c.scope_type == "in_scope"] if profile else []


HYPERCARE_SETTING = "hypercare_effort_days"


def _overrides(ledger: Ledger, kind: str, section: str = "scope_items") -> dict[str, Any]:
    """Applied reviewer edits of one field of one section's lines, keyed by row id (call 2)."""
    return {o.row_id: o.new for o in ledger.overrides
            if o.applied and o.kind == "edit" and o.section == section and o.field == kind and o.row_id}


def _deleted(ledger: Ledger, section: str) -> set[str]:
    return {o.row_id for o in ledger.overrides if o.applied and o.kind == "deleted_row" and o.section == section}


def _settings_overrides(ledger: Ledger) -> dict[str, Any]:
    return {o.field: o.new for o in ledger.overrides if o.applied and o.kind == "setting"}


def _apply_line_overrides(ledger: Ledger, effort: EffortModel) -> None:
    """Reviewer edits of catalogue lines (phase cells, deletions) and Tech Dev lines (call 2)."""
    deleted = _deleted(ledger, "scope_items")
    phase_edits = {f: _overrides(ledger, f) for f in PHASE_FIELDS}
    for module in effort.modules.values():
        module.rows = [r for r in module.rows if r.row_id not in deleted]
        for row in module.rows:
            for field, edits in phase_edits.items():
                if row.row_id in edits and edits[row.row_id] is not None:
                    setattr(row, field, float(edits[row.row_id]))
            row.compute_total()
    td_deleted = _deleted(ledger, "tech_dev")
    td_fields = ("no_of_objects", "development", "configuration", "unit_testing", "qa_testing")
    td_edits = {f: _overrides(ledger, f, "tech_dev") for f in td_fields}
    rows = [r for r in effort.tech_dev if r.row_id not in td_deleted]
    for row in rows:
        for field, edits in td_edits.items():
            if row.row_id in edits and edits[row.row_id] is not None:
                value = edits[row.row_id]
                setattr(row, field, int(round(float(value))) if field == "no_of_objects" else round(float(value), 2))
    for n, added in enumerate(o for o in ledger.overrides
                              if o.applied and o.kind == "added_row" and o.section == "tech_dev"):
        data = dict(added.new or {})
        rows.append(TechDevRow(
            row_id=f"reviewer-{n + 1}", source="reviewer", module=str(data.get("module") or "All"),
            object_name=str(data.get("object_name") or "Reviewer addition"),
            object_type=str(data.get("object_type") or ""), middleware=str(data.get("middleware") or ""),
            source_system=str(data.get("source_system") or ""), target_system=str(data.get("target_system") or ""),
            no_of_objects=int(round(float(data.get("no_of_objects") or 1))),
            complexity=str(data.get("complexity") or "Medium"),
            **{f: round(float(data.get(f) or 0.0), 2) for f in td_fields[1:]}))
    effort.tech_dev = rows


def _apply_grid_overrides(ledger: Ledger, plan: ResourcePlan, policy: Policy) -> list[str]:
    """Reviewer FTE edits on the resource grids: row id 'wave||role||location', field 'M<k>'."""
    notes: list[str] = []
    grids = {g.wave_name: g for g in plan.grids}
    for o in ledger.overrides:
        if not (o.applied and o.kind == "edit" and o.section == "grid"):
            continue
        wave, _, rest = o.row_id.partition("||")
        role, _, location = rest.partition("||")
        grid = grids.get(wave)
        row = next((r for r in grid.rows if r.role_title == role and r.location == location), None) if grid else None
        try:
            month = int(o.field.lstrip("M"))
        except ValueError:
            month = 0
        if row is None or not 1 <= month <= grid.months:
            notes.append(f"grid edit {o.row_id} {o.field} no longer matches the plan; ignored")
            continue
        fte = max(float(o.new or 0.0), 0.0)
        cell = next((c for c in row.cells if c.month_index == month), None)
        if cell is None:
            row.cells.append(GridCell(month_index=month, phase=grid.phase_bands[month - 1], fte=fte))
            row.cells.sort(key=lambda c: c.month_index)
        else:
            cell.fte = fte
    return notes


def _wave_tags(ledger: Ledger, countries: list[str]) -> dict[str, str]:
    """EffortRow.row_id -> wave, from the wave plan's tags and the reviewer's Wave-column edits."""
    tags: dict[str, str] = {}
    plan = ledger.wave_plan.data
    items = {s.row_id: s for s in ledger.scope_items.rows}
    for tag in plan.item_tags if plan else []:
        item = items.get(tag.row_id)
        if item is None:
            continue
        for country in ([tag.country] if tag.country else (item.countries or countries or [""])):
            tags[f"{item.row_id}@{country or 'ALL'}"] = tag.wave
    tags.update({k: str(v) for k, v in _overrides(ledger, "wave").items() if v})
    return tags


def compute_effort(ledger: Ledger, wave_count: int, policy: Policy | None = None) -> EffortModel:
    policy = policy or get_policy()
    countries = bid_countries(ledger)
    factors = {k: float(v) for k, v in _overrides(ledger, "multiplication_factor").items()}
    modules = compute_catalogue_effort(
        ledger.scope_items.rows, countries, ledger.meta.rate_card_sheet, policy, factors,
        _wave_tags(ledger, countries))
    keywords = policy.resourcing.project_management_keywords
    non_catalogue = [
        NonCatalogueEffort(row_id=r.row_id, name=r.name, description=r.description, label=r.label,
                           effort_days=float(r.effort_days or 0.0), rationale=r.rationale,
                           is_project_management=r.is_project_management or any(k in r.name.lower() for k in keywords))
        for r in ledger.non_catalogue.rows
    ]
    tech_dev = compute_tech_dev(ledger.ricefw.data, ledger.fiori.data, ledger.integrations.rows, policy)
    tables = build_workstream_tables(
        ledger.data_migration.rows, ledger.basis.rows, ledger.security.rows, ledger.analytics.rows,
        ledger.analytics_scope.data, max(wave_count, 1), policy)
    effort = EffortModel(rate_card_sheet=ledger.meta.rate_card_sheet, modules=modules,
                         non_catalogue=non_catalogue, tech_dev=tech_dev, workstreams=tables)
    _apply_line_overrides(ledger, effort)
    return effort


def _submodule_effort(effort: EffortModel) -> tuple[dict[str, list[str]], dict[str, dict[str, float]]]:
    """Per LOB: the cross-mapped sub-modules and the effort each carries (rows without one are spread
    in proportion to what the named sub-modules already hold, as the old split did)."""
    names: dict[str, list[str]] = {}
    split: dict[str, dict[str, float]] = {}
    for lob, module in effort.modules.items():
        subs = [s for s in module.submodules if s]
        if not subs:
            continue
        carried: dict[str, float] = defaultdict(float)
        loose = 0.0
        for row in module.rows:
            if row.submodule in subs:
                carried[row.submodule] += row.total
            else:
                loose += row.total
        claimed = sum(carried.values())
        names[lob] = subs
        split[lob] = {s: round(carried[s] + (loose * carried[s] / claimed if claimed else loose / len(subs)), 2)
                      for s in subs}
    return names, split


def size_bid(ledger: Ledger, policy: Policy | None = None) -> SizingResult:
    policy = policy or get_policy()
    settings = _settings_overrides(ledger)
    hypercare_override = settings.pop(HYPERCARE_SETTING, None)
    countries = bid_countries(ledger)
    notes: list[str] = []

    # Timeline first needs a sizing effort; the DM table count then follows the resolved waves.
    provisional = compute_effort(ledger, 1, policy)
    sizing_effort = provisional.core_bp_effort + provisional.non_catalogue_effort + provisional.third_party_effort
    timeline = resolve_timeline(ledger.timeline.data, ledger.wave_plan.data, sizing_effort, countries, policy)
    notes += timeline.notes
    effort = compute_effort(ledger, len(timeline.waves), policy)

    wave_effort, weights = allocate_waves(effort, timeline, ledger.wave_plan.data, policy)
    notes += wave_effort.flags
    specs = [WaveSpec(name=w.name, total_months=w.total_months, hypercare_months=w.hypercare_months,
                      start_month=timeline.wave_start_month(w), phase_split=w.phase_split) for w in timeline.waves]
    submodules, submodule_effort = _submodule_effort(effort)
    integration_names = [r.system for r in ledger.integrations.rows]
    pm_names = {n.name for n in effort.non_catalogue if n.is_project_management}
    pm_names |= {r.system for r in ledger.integrations.rows
                 if r.is_project_management or is_project_management(r.system, policy)}
    plan = build_resource_plan(
        specs, timeline.is_sequential, timeline.programme_weeks / policy.timeline.weeks_per_month,
        wave_effort.lob, wave_effort.pools, {lob: m.total_effort for lob, m in effort.modules.items()},
        submodules, submodule_effort, [n.name for n in effort.non_catalogue], integration_names, pm_names, policy)

    def ladder(totals: dict[str, float]) -> SummaryLadder:
        hypercare = plan.hypercare_effort_days if hypercare_override is None else float(hypercare_override)
        return compute_summary(
            effort.core_bp_effort + effort.non_catalogue_effort, totals["data_migration"], effort.tech_dev_effort,
            totals["security"], totals["basis"], totals["analytics"], hypercare, policy, settings)

    totals = workstream_totals(effort.workstreams, policy)
    summary = ladder(totals)
    titles = policy.resourcing.category_consultants
    rebalance_plan_to_effort_summary(plan, summary.total_build, plan.hypercare_effort_days,
                                     {titles[k]: totals[k] for k in CATEGORY_KEYS}, weights, policy)
    if policy.resourcing.scope_sync.enabled:
        notes += sync_scope_tables(plan, effort.workstreams, policy, seed=ledger.meta.bid_id)
        totals = workstream_totals(effort.workstreams, policy)
    hypercare = plan.hypercare_effort_days
    notes += _apply_grid_overrides(ledger, plan, policy)
    price_plan(plan, policy, daily_rate=settings.get("daily_rate_usd"))
    plan.hypercare_effort_days = hypercare   # the Summary's Hypercare row stays the pre-rebalance figure
    summary = ladder(totals)
    return SizingResult(effort=effort, timeline=timeline, wave_effort=wave_effort, weights=weights, plan=plan,
                        summary=summary, totals=totals, notes=notes)
