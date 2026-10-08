"""Load and validate policy/*.yaml (numbers and layouts that used to be Python constants).

    from bidcore.policy import get_policy
    p = get_policy()
    p.commercials.daily_rate_usd, p.resourcing.default_phase_split, p.version

`version` is a short hash of every policy file; it is stamped into the ledger and the
workbook's `_bid` sheet so an output always says which numbers produced it.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from bidcore.paths import policy_dir


class _M(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


# ---------------------------------------------------------------- commercials
class Hypercare(_M):
    onsite_rate_usd: float
    offshore_rate_usd: float
    flat_rate_usd: float


class SummaryLadder(_M):
    final_prep_pct: float
    go_live_pct: float
    project_mgmt_pct: float
    risk_factor: float


class Commercials(_M):
    currency: str = "USD"
    daily_rate_usd: float
    working_days_per_month: int
    hypercare: Hypercare
    summary_ladder: SummaryLadder
    programme_overhead: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------- effort
class RateCard(_M):
    default_sheet: str
    multiplication_factor: float
    per_country_fan_out: bool
    zero_effort_comment: str


class TechDev(_M):
    hours_per_day: float
    per_object_hours: dict[str, dict[str, float]]
    fiori: dict[str, Any]
    ricefw_buckets: list[dict[str, str]]
    default_object_types: list[str]
    third_party_split: dict[str, float]


class NonCatalogue(_M):
    catalogue_covered_codes: list[str]
    effort_bands: dict[str, list[float]]


class Effort(_M):
    rate_card: RateCard
    tech_dev: TechDev
    non_catalogue: NonCatalogue


# ---------------------------------------------------------------- resourcing
class Role(_M):
    title: str
    location: str
    fte: float
    window: tuple[float, float]


class LeadProfile(_M):
    location: str
    fte: float
    window: tuple[float, float]


class ScopeSync(_M):
    enabled: bool
    max_variance_days: float
    step_days: float
    slot_fte: float
    min_cell_days: float
    seed_from: str


class Resourcing(_M):
    default_phase_split: dict[str, float]
    hypercare_phase: str
    programme_singular_roles: list[Role]
    programme_per_wave_roles: list[Role]
    lead_profiles: dict[str, LeadProfile]
    lead_fte_bounds: tuple[float, float]
    pools: dict[str, str]
    fte_grain: float
    fte_grain_small: float
    small_category_md_threshold: float
    pgls_retention: dict[str, float]
    wave_role_min_share: float
    max_grid_rows: int
    category_consultants: dict[str, str]
    rebalance: dict[str, float]
    project_management_keywords: list[str]
    scope_sync: ScopeSync

    @property
    def phases(self) -> list[str]:
        return list(self.default_phase_split)

    @property
    def programme_role_titles(self) -> set[str]:
        return {r.title for r in [*self.programme_singular_roles, *self.programme_per_wave_roles]}


# ---------------------------------------------------------------- timeline / catalogue
class Timeline(_M):
    weeks_per_month: float
    max_plausible_weeks: float
    max_waves: int
    max_units: int
    min_wave_weeks: float
    max_wave_weeks: float
    min_implementation_weeks: float
    default_hypercare_weeks: float
    default_sequencing: str
    duration_bands: list[tuple[float, int]]
    duration_above_bands_months: int
    duration_no_effort_months: int
    wave_axes: list[str]
    wave_kinds: list[str]
    unit_kinds: list[str]


class CataloguePolicy(_M):
    allowed_countries: list[str]
    lobs: list[str]
    sensitive_lobs: list[str]
    finance_core_business_areas: list[str]
    scope_types: list[str]
    implementation_statuses: list[str]
    confidence_levels: list[str]


class Runtime(_M):
    models: dict[str, Any]
    limits: dict[str, Any]
    teams: dict[str, dict[str, Any]]


class Policy(_M):
    commercials: Commercials
    effort: Effort
    resourcing: Resourcing
    timeline: Timeline
    catalogue: CataloguePolicy
    workstreams: dict[str, dict[str, Any]]
    workbook: dict[str, Any]
    runtime: Runtime
    version: str


_FILES = ("commercials", "effort", "resourcing", "timeline", "catalogue", "workstreams", "workbook", "runtime")


def load_policy(directory: Path | None = None) -> Policy:
    directory = directory or policy_dir()
    raw: dict[str, Any] = {}
    digest = hashlib.sha256()
    for name in _FILES:
        path = directory / f"{name}.yaml"
        data = path.read_bytes()
        digest.update(name.encode() + b"\0" + data)
        raw[name] = yaml.safe_load(data) or {}
    return Policy(**raw, version=digest.hexdigest()[:12])


@lru_cache(maxsize=1)
def get_policy() -> Policy:
    return load_policy()
