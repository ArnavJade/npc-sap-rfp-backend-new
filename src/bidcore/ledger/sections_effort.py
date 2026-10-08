"""Call-1 ledger sections (effort team). Field descriptions double as tool-argument docs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bidcore.ledger.base import Complexity, Evidence, Row, Status


# ------------------------------------------------------------------ rfp-analyst
class CountryScope(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str = Field(description="ISO-2 code from the allowed list (catalogue countries).")
    name: str = ""
    scope_type: Literal["in_scope", "optional_scope"] = "in_scope"
    evidence: list[Evidence] = Field(default_factory=list)


class RfpProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    client_name: str = ""
    engagement_type: Literal["greenfield", "brownfield", "bluefield", "unknown"] = "unknown"
    engagement_reason: str = Field("", description="One sentence: why this engagement type.")
    summary: str = Field("", description="3-6 sentences: what the client is buying.")
    countries: list[CountryScope] = Field(default_factory=list)
    unsupported_countries: list[str] = Field(
        default_factory=list, description="Countries the RFP names that are not in the allowed list (names).")
    evidence: list[Evidence] = Field(default_factory=list)


class Capability(Row):
    capability: str = Field(description="The client's own wording of the business capability / module.")
    sap_module_hint: str = Field("", description="SAP module or product named or clearly implied, e.g. 'FI', 'EWM'.")
    countries: list[str] = Field(default_factory=list, description="ISO codes; empty = every in-scope country.")
    scope_type: Literal["in_scope", "optional_scope"] = "in_scope"
    implementation_status: Literal["new_implementation", "existing_change", "existing_no_change"] = "new_implementation"
    confidence: Literal["high", "medium", "low"] = "medium"


class WaveUnit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    kind: Literal["entity", "country", "site", ""] = ""
    iso: str = Field("", description="ISO-2 code, or 'OTHER:<name>'.")
    lobs: list[str] = Field(default_factory=list, description="Catalogue LOBs this unit takes, per the RFP scope matrix.")


class Wave(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = "Wave 1"
    sequence: int = 1
    total_weeks: float = Field(0.0, description="Stated duration INCLUDING hypercare when the RFP says 'including'.")
    hypercare_weeks: float = 0.0
    start: str = Field("", description="Start date/month as stated.")
    go_live: str = Field("", description="Go-live date/month as stated.")
    countries: list[str] = Field(default_factory=list, description="ISO codes delivered in this wave.")
    entities: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list, description="Module wording as the RFP gives it.")
    lobs: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    unit_ids: list[str] = Field(default_factory=list)
    partition_axis: Literal["entity", "country", "module", "site", "mixed", ""] = ""
    kind: Literal["template_build", "rollout", "technical", "full", ""] = ""
    duration_source: Literal["rfp", "agent", "derived", ""] = ""
    evidence: list[Evidence] = Field(default_factory=list)


class Numbering(BaseModel):
    conflict: bool = False
    basis: Literal["scope", "milestone", "undecided", ""] = ""
    alt: str = ""


class Timeline(BaseModel):
    model_config = ConfigDict(extra="ignore")
    waves: list[Wave] = Field(default_factory=list)
    units: list[WaveUnit] = Field(default_factory=list)
    sequencing: Literal["sequential", "parallel", "staggered"] = "parallel"
    hypercare_required: bool = False
    hypercare_mode: Literal["inclusive", "appended", "none"] = "none"
    numbering: Numbering = Field(default_factory=Numbering)
    source: Literal["rfp", "derived"] = "rfp"
    reason: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


# ------------------------------------------------------------------ catalogue-mapper
class ScopeItem(Row):
    scope_item_id: str = Field(description="Catalogue Scope Item ID from catalogue_search, e.g. 'J58'.")
    lob: str = Field("", description="Filled from the catalogue when empty.")
    business_area: str = Field("", description="Filled from the catalogue when empty.")
    description: str = Field("", description="Filled from the catalogue when empty.")
    countries: list[str] = Field(default_factory=list, description="ISO codes this item is delivered in.")
    submodule: str = Field("", description="Cross-mapped module name that produced the match, e.g. 'Controlling (CO)'.")
    capability_refs: list[str] = Field(default_factory=list, description="row_ids of the capabilities it serves.")
    mapping_basis: Literal["cross_map", "catalogue_search", "finance_core", "reviewer"] = "catalogue_search"
    status: Literal["in_scope", "optional", "excluded_existing"] = "in_scope"


class NonCatalogueItem(Row):
    name: str = Field(description="SAP tool / module name, e.g. 'SAP Solution Manager 7.2'.")
    kind: Literal["sap_tool", "sap_module_no_bp"] = "sap_tool"
    label: str = Field("", description="Cross-mapping 'Others' label, e.g. 'SAP Tool'.")
    description: str = ""
    countries: list[str] = Field(default_factory=list)
    is_project_management: bool = False
    effort_days: float = Field(0.0, description="Person-days, inside the chosen policy effort band.")
    effort_band: str = Field("", description="One of: sap_tool_light (5-20 PD), sap_tool_standard (20-60 PD), "
                                             "sap_module_no_best_practice (40-150 PD), third_party_integration "
                                             "(10-60 PD). Never S/M/L.")
    rationale: str = ""


# ------------------------------------------------------------------ scope specialists
class Integration(Row):
    system: str = Field(description="The third-party system name, e.g. 'Kronos'.")
    functionality: str = ""
    sap_modules: list[str] = Field(default_factory=list)
    direction: Literal["inbound", "outbound", "bidirectional", "unknown"] = "unknown"
    data_exchanged: str = ""
    middleware: str = ""
    protocol: str = ""
    interface_count: int = 1
    frequency: str = ""
    complexity_driver: str = ""
    source_system: str = ""
    target_system: str = ""
    complexity: Complexity = "Medium"
    is_project_management: bool = False
    effort_days: float = Field(0.0, description="Person-days for this integration (skill effort guide).")
    rationale: str = ""


class RicefwRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    object_type: str = Field(description="Report | Interface | Conversion | Enhancement | Form | Workflow")
    no_of_objects: int
    complexity: Complexity = "Medium"
    development: float | None = Field(None, description="Man-HOURS for the whole row, only when the RFP states it.")
    configuration: float | None = None
    unit_testing: float | None = None
    qa_testing: float | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class Ricefw(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rows: list[RicefwRow] = Field(default_factory=list, description="Per-component rows when the RFP lists them.")
    development_objects_total: int = Field(0, description="Lump WRICEF total when there are no rows.")
    complexity_split_pct: dict[str, float] = Field(default_factory=dict, description="{complex, medium, simple} %.")
    development_object_type: str = ""
    interface_total_count: int = Field(0, description="Total interfaces the RFP states (3rd-party rows are subtracted).")
    evidence: list[Evidence] = Field(default_factory=list)


class Fiori(BaseModel):
    model_config = ConfigDict(extra="ignore")
    app_count: int = 0
    app_names: list[str] = Field(default_factory=list)
    per_app_hours: dict[str, float] = Field(
        default_factory=dict, description="{development, configuration, unit_testing, qa_testing} man-hours per app.")
    evidence: list[Evidence] = Field(default_factory=list)


class DataMigrationObject(Row):
    object: str = Field(description="Master data object, e.g. 'Material Master'.")
    module: str = Field("", description="The RFP's area name the object is listed under, e.g. 'Order to Cash'.")
    rfp_label: str = Field("", description="The RFP's own wording for it (verbatim).")
    sap_module: str = Field("", description="Standard SAP module short name owning the object, e.g. 'MM'.")
    category: str = Field("Master Data", description="MDG data domain for MDG objects, else 'Master Data'.")
    status: Status = "In Scope"
    func_spec: float = 1.0
    program_dev: float = 1.0
    iteration_1: float = 2.0
    iteration_2: float = 2.0
    iteration_3: float = 2.0
    cutover: float = 1.0
    mm_compulsory: bool = Field(False, description="True only for MM master data included by the compulsory rule.")


class BasisActivity(Row):
    activity: str
    status: Status = "In Scope"
    dev: int | None = Field(None, description="1-5 man-days; null when Out of Scope.")
    qa: int | None = None
    prd: int | None = None


class SecurityActivity(Row):
    activity: str
    sap_product: str = ""
    status: Status = "In Scope"
    complexity: Complexity = "Medium"
    effort_days: int | None = Field(None, description="1-120 whole man-days; null when Out of Scope.")


class AnalyticsObject(Row):
    object: str
    object_type: Literal["Model", "Report", "CDS View"] = "Report"
    build: Literal["Custom", "Standard"] = "Custom"
    sap_product: str = Field("", description="SAP analytics product the RFP names for it; '' when none.")
    no_of_objects: int = 1
    status: Status = "In Scope"
    complexity: Complexity = "Medium"


class AnalyticsScope(BaseModel):
    """Exclusion flag for the analytics workstream as a whole (objects are a row section)."""
    model_config = ConfigDict(extra="ignore")
    excluded: bool = False
    exclusion_evidence: list[Evidence] = Field(default_factory=list)


# ------------------------------------------------------------------ wave-planner
class WaveAllocation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    workstream: str = Field(description="'lob:<LOB>' or one of integrations, non_catalogue, tech_dev, "
                                        "data_migration, basis, security, analytics.")
    shares: dict[str, float] = Field(description="wave name -> share of this workstream's effort; sums to 1.")
    rationale: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class ItemTag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    row_id: str = Field(description="scope_items row_id.")
    country: str = Field("", description="Only this country's line of the item; empty = every country line.")
    wave: str
    rationale: str = ""


class WavePhasePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    wave: str
    phase_split: dict[str, float] = Field(description="Relative weights for Prepare, Explore, Realize, Deploy.")
    total_weeks: float | None = Field(None, description="Only for waves the RFP did not date (incl. hypercare).")
    hypercare_weeks: float | None = None
    rationale: str = ""


class WavePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    allocations: list[WaveAllocation] = Field(default_factory=list)
    item_tags: list[ItemTag] = Field(default_factory=list)
    phases: list[WavePhasePlan] = Field(default_factory=list)
    notes: str = ""
