"""Computed effort picture (deterministic output of bidcore.effort, input to resourcing and rendering).

Nothing here is written by an agent: it is derived from the ledger + rate card + policy, and every
client-facing number in the workbook and the proposal comes from these objects.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

PHASE_FIELDS = ("workshops_configuration", "unit_testing", "integration_testing",
                "documentation_training", "user_acceptance_testing")


class EffortRow(BaseModel):
    """One catalogue line: a scope item in one country (rate-card person-days)."""
    row_id: str                       # "<scope_items row_id>@<country>" (stable across calls)
    item_row_id: str                  # ledger scope_items row_id
    lob: str
    business_area: str
    country: str = ""                 # ISO-2; "" for a single global line
    scope_id: str
    description: str
    complexity: str = ""
    workshops_configuration: float = 0.0
    unit_testing: float = 0.0
    integration_testing: float = 0.0
    documentation_training: float = 0.0
    user_acceptance_testing: float = 0.0
    multiplication_factor: float = 1.0
    total: float = 0.0
    wave: str = ""                    # explicit wave tag (agent or reviewer); "" = spread by allocation
    submodule: str = ""
    comments: str = ""

    def compute_total(self) -> float:
        base = sum(getattr(self, f) for f in PHASE_FIELDS)
        self.total = round(base * self.multiplication_factor, 2)
        return self.total


class ModuleEffort(BaseModel):
    lob: str
    rows: list[EffortRow] = Field(default_factory=list)
    unmatched_scope_ids: list[str] = Field(default_factory=list)   # no rate-card row -> zero-effort lines
    excluded_scope_ids: list[str] = Field(default_factory=list)    # existing, no change -> not costed
    submodules: list[str] = Field(default_factory=list)            # cross-mapped module names (Summary label)

    @property
    def total_effort(self) -> float:
        return round(sum(r.total for r in self.rows), 2)

    @property
    def bp_id_count(self) -> int:
        return len(self.rows)


class NonCatalogueEffort(BaseModel):
    row_id: str
    name: str
    description: str = ""
    label: str = ""
    effort_days: float = 0.0
    is_project_management: bool = False
    rationale: str = ""


class TechDevRow(BaseModel):
    """A Tech Dev Scope line in PERSON-DAYS (hour-based estimates already divided by 8)."""
    row_id: str
    source: str                       # ricefw | fiori | third_party | interface
    module: str = "All"
    object_name: str = ""
    object_type: str = ""
    middleware: str = ""
    source_system: str = ""
    target_system: str = ""
    no_of_objects: int = 0
    complexity: str = "Medium"
    development: float = 0.0
    configuration: float = 0.0
    unit_testing: float = 0.0
    qa_testing: float = 0.0

    @property
    def total(self) -> float:
        # The sheet's Total is =SUM of the four ROUNDED cells; mirror that exactly.
        return round(sum(round(v, 2) for v in (self.development, self.configuration,
                                                self.unit_testing, self.qa_testing)), 2)


class WorkstreamTables(BaseModel):
    """Rows of the four specialist sheets, as dicts in the shape the sheet writers and scope sync use.

    data_migration: one table per delivery wave (rows repeated per wave, each table its own total);
      row keys: row_id, object, status, func_spec, program_dev, iteration_1, iteration_2, iteration_3, cutover
    basis:     row_id, activity, status, dev, qa, prd
    security:  row_id, activity, status, complexity, effort_days
    analytics: row_id, object, object_type, build, no_of_objects, status, complexity (+ computed devlp,
               unit_testing, qa_testing, total in person-days)
    """
    data_migration: list[list[dict]] = Field(default_factory=list)
    basis: list[dict] = Field(default_factory=list)
    security: list[dict] = Field(default_factory=list)
    analytics: list[dict] = Field(default_factory=list)
    analytics_excluded: bool = False


class EffortModel(BaseModel):
    rate_card_sheet: str
    modules: dict[str, ModuleEffort] = Field(default_factory=dict)
    non_catalogue: list[NonCatalogueEffort] = Field(default_factory=list)
    tech_dev: list[TechDevRow] = Field(default_factory=list)
    workstreams: WorkstreamTables = Field(default_factory=WorkstreamTables)

    @property
    def core_bp_effort(self) -> float:
        return round(sum(m.total_effort for m in self.modules.values()), 2)

    @property
    def non_catalogue_effort(self) -> float:
        return round(sum(n.effort_days for n in self.non_catalogue), 2)

    @property
    def tech_dev_effort(self) -> float:
        return round(sum(r.total for r in self.tech_dev), 2)

    @property
    def third_party_effort(self) -> float:
        return round(sum(r.total for r in self.tech_dev if r.source == "third_party"), 2)
