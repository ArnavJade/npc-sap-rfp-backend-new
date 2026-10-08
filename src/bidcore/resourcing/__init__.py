"""Deterministic staffing engine: role roster -> per-wave FTE grids -> price -> rebalance -> scope sync.

Ported from the old resource_grid_layer4.py / resource_scope_sync.py with the LLM grid dropped. The
wave plan (phase split per wave, per-wave effort, per-pass weights) is an input; every number is
computed here from it and from policy. Typical call order:

    plan = build_resource_plan(waves, sequential, programme_months, wave_lob_effort, wave_pool_effort, ...)
    rebalance_plan_to_effort_summary(plan, total_build_effort, hypercare_days, category_days, weights)
    notes = sync_scope_tables(plan, workstream_tables, seed=bid_id)
    price_plan(plan)                      # refresh plan-level figures after the in-place passes
"""

from bidcore.resourcing.grid import (
    derive_resource_grid,
    distributive_month_weights,
    implementation_man_months,
    implementation_months,
    phase_bands_for_wave,
    phase_weights,
    window_months,
)
from bidcore.resourcing.models import (
    OFFSHORE,
    ONSITE,
    PGLS,
    GridCell,
    GridRow,
    PassWeights,
    ResourcePlan,
    RoleSpec,
    WaveResourceGrid,
    WaveSpec,
)
from bidcore.resourcing.plan import build_resource_plan, split_approved_by_wave
from bidcore.resourcing.pricing import price_plan
from bidcore.resourcing.rebalance import inject_category_consultant_rows, rebalance_plan_to_effort_summary
from bidcore.resourcing.roles import (
    effort_scaled_fte,
    is_project_management,
    pooled_lead_count,
    pooled_roles,
    project_management_names,
    required_roles,
    sort_rows,
    submodules_for,
    third_party_display_name,
)
from bidcore.resourcing.rounding import quantize_grid, quantize_half, quantize_row, round_all_cells_to_grain
from bidcore.resourcing.scope_sync import analytics_effort_days, sync_scope_tables

__all__ = [
    "OFFSHORE", "ONSITE", "PGLS",
    "GridCell", "GridRow", "PassWeights", "ResourcePlan", "RoleSpec", "WaveResourceGrid", "WaveSpec",
    "analytics_effort_days", "build_resource_plan", "derive_resource_grid", "distributive_month_weights",
    "effort_scaled_fte", "implementation_man_months", "implementation_months", "inject_category_consultant_rows",
    "is_project_management", "phase_bands_for_wave", "phase_weights", "pooled_lead_count", "pooled_roles",
    "price_plan", "project_management_names", "quantize_grid", "quantize_half", "quantize_row",
    "rebalance_plan_to_effort_summary", "required_roles", "round_all_cells_to_grain", "sort_rows",
    "split_approved_by_wave", "submodules_for", "sync_scope_tables", "third_party_display_name",
    "window_months",
]
