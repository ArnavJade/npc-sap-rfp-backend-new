"""The bid ledger: one validated JSON document per bid - the only state between the two calls.

Agents write it only through ledger tools; the workbook and the Word response are both views of it.
SECTIONS is the registry the tools, validators and coverage check are driven from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bidcore.ledger.base import AuditEvent, ObjectSection, RowSection, utcnow
from bidcore.ledger.sections_effort import (
    AnalyticsObject, AnalyticsScope, BasisActivity, Capability, DataMigrationObject, Fiori, Integration,
    NonCatalogueItem, RfpProfile, Ricefw, ScopeItem, SecurityActivity, Timeline, WavePlan,
)
from bidcore.ledger.sections_proposal import Override, ResponseRequirements


class SourceFile(BaseModel):
    name: str
    sha256: str
    workspace_md: str = ""          # rfp/<slug>.md produced by ingestion
    pages: int = 0
    kind: Literal["rfp", "workbook", "other"] = "rfp"


class Meta(BaseModel):
    model_config = ConfigDict(extra="allow")
    bid_id: str
    client_name: str = "Client"
    created_at: str = Field(default_factory=utcnow)
    version: int = 0
    policy_version: str = ""
    rate_card_sheet: str = "SAP BP"
    models: dict[str, str] = Field(default_factory=dict)
    files: list[SourceFile] = Field(default_factory=list)
    status: str = "created"


class Ledger(BaseModel):
    model_config = ConfigDict(extra="ignore")
    meta: Meta
    # call 1 - effort team
    rfp_profile: ObjectSection[RfpProfile] = Field(default_factory=ObjectSection[RfpProfile])
    capabilities: RowSection[Capability] = Field(default_factory=RowSection[Capability])
    timeline: ObjectSection[Timeline] = Field(default_factory=ObjectSection[Timeline])
    scope_items: RowSection[ScopeItem] = Field(default_factory=RowSection[ScopeItem])
    non_catalogue: RowSection[NonCatalogueItem] = Field(default_factory=RowSection[NonCatalogueItem])
    integrations: RowSection[Integration] = Field(default_factory=RowSection[Integration])
    ricefw: ObjectSection[Ricefw] = Field(default_factory=ObjectSection[Ricefw])
    fiori: ObjectSection[Fiori] = Field(default_factory=ObjectSection[Fiori])
    data_migration: RowSection[DataMigrationObject] = Field(default_factory=RowSection[DataMigrationObject])
    basis: RowSection[BasisActivity] = Field(default_factory=RowSection[BasisActivity])
    security: RowSection[SecurityActivity] = Field(default_factory=RowSection[SecurityActivity])
    analytics: RowSection[AnalyticsObject] = Field(default_factory=RowSection[AnalyticsObject])
    analytics_scope: ObjectSection[AnalyticsScope] = Field(default_factory=ObjectSection[AnalyticsScope])
    wave_plan: ObjectSection[WavePlan] = Field(default_factory=ObjectSection[WavePlan])
    # call 2 - proposal team + reviewer edits
    response_requirements: ObjectSection[ResponseRequirements] = Field(
        default_factory=ObjectSection[ResponseRequirements])
    overrides: list[Override] = Field(default_factory=list)
    # deterministic outputs (never written by agents)
    figures: dict[str, Any] = Field(default_factory=dict)
    audit: list[AuditEvent] = Field(default_factory=list)

    def section(self, name: str) -> RowSection | ObjectSection:
        spec = SECTIONS[name]
        return getattr(self, spec.attr)


@dataclass(frozen=True)
class SectionSpec:
    name: str
    model: type[BaseModel]
    kind: Literal["rows", "object"]
    team: Literal["effort", "proposal"]
    row_prefix: str = ""
    attr: str = ""
    evidence_required: bool = True

    def __post_init__(self):
        if not self.attr:
            object.__setattr__(self, "attr", self.name)


SECTIONS: dict[str, SectionSpec] = {s.name: s for s in [
    SectionSpec("rfp_profile", RfpProfile, "object", "effort"),
    SectionSpec("capabilities", Capability, "rows", "effort", "cap"),
    SectionSpec("timeline", Timeline, "object", "effort"),
    SectionSpec("scope_items", ScopeItem, "rows", "effort", "si", evidence_required=False),
    SectionSpec("non_catalogue", NonCatalogueItem, "rows", "effort", "nc"),
    SectionSpec("integrations", Integration, "rows", "effort", "int"),
    SectionSpec("ricefw", Ricefw, "object", "effort"),
    SectionSpec("fiori", Fiori, "object", "effort"),
    SectionSpec("data_migration", DataMigrationObject, "rows", "effort", "dm"),
    SectionSpec("basis", BasisActivity, "rows", "effort", "bas"),
    SectionSpec("security", SecurityActivity, "rows", "effort", "sec"),
    SectionSpec("analytics", AnalyticsObject, "rows", "effort", "ana"),
    SectionSpec("analytics_scope", AnalyticsScope, "object", "effort", evidence_required=False),
    SectionSpec("wave_plan", WavePlan, "object", "effort", evidence_required=False),
    SectionSpec("response_requirements", ResponseRequirements, "object", "proposal", evidence_required=False),
]}


def new_ledger(bid_id: str, client_name: str = "Client", **meta: Any) -> Ledger:
    return Ledger(meta=Meta(bid_id=bid_id, client_name=client_name, **meta))
