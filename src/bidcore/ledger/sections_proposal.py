"""Call-2 ledger sections (proposal team) and reviewer overrides."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bidcore.ledger.base import Evidence, Row

DISCLOSURE_CATEGORIES = ("scope_item_detail", "effort_detail", "resource_allocation",
                         "resource_location", "commercial_detail")


class ClientRequirement(Row):
    title: str
    intent: str = Field(description="What the client asks the response to contain, in a sentence or two.")
    kind: Literal["narrative", "indicative_breakdown", "phase_plan"] = "narrative"
    maps_to_section_id: str = Field("", description="Existing outline section that already covers it (e.g. '4.3').")
    placement_after_section_id: str = Field("", description="Where a NEW section goes when nothing covers it.")
    group_by: Literal["", "module", "wave", "country", "role", "workstream"] = Field(
        "", description="For indicative_breakdown: the dimension of the table.")


class SectionExcerpt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    section_id: str
    excerpt: str = Field(description="Verbatim RFP text (<= 400 chars) the section must answer.")
    evidence: list[Evidence] = Field(default_factory=list)


class Disclosure(BaseModel):
    """Which internal estimation detail the client explicitly asked to see. Withheld -> Excel only.

    Every category defaults to withheld: detail is disclosed only when the RFP asks for it (with the
    wording in `evidence`), so a missing or partial profile can never expose unrequested commercials."""
    model_config = ConfigDict(extra="ignore")
    scope_item_detail: bool = False
    effort_detail: bool = False
    resource_allocation: bool = False
    resource_location: bool = False
    commercial_detail: bool = False
    evidence: dict[str, str] = Field(default_factory=dict, description="category -> RFP wording that justified True.")
    source: Literal["default", "rfp", "fallback"] = "default"

    @classmethod
    def high_level(cls, source: str = "fallback") -> "Disclosure":
        return cls(**{k: False for k in DISCLOSURE_CATEGORIES}, source=source)

    @classmethod
    def full(cls, source: str = "rfp") -> "Disclosure":
        return cls(**{k: True for k in DISCLOSURE_CATEGORIES}, source=source)

    @property
    def withheld(self) -> list[str]:
        return [k for k in DISCLOSURE_CATEGORIES if not getattr(self, k)]


class ResponseRequirements(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requirements: list[ClientRequirement] = Field(default_factory=list)
    section_excerpts: list[SectionExcerpt] = Field(default_factory=list)
    disclosure: Disclosure = Field(default_factory=Disclosure)
    instructions_briefs: dict[str, str] = Field(
        default_factory=dict, description="section_id -> brief derived from the presales instructions.")


class Override(BaseModel):
    """One reviewer edit read back from the workbook (call 2)."""
    model_config = ConfigDict(extra="ignore")
    sheet: str
    cell: str = ""
    section: str = ""
    row_id: str = ""
    field: str = ""
    old: Any = None
    new: Any = None
    kind: Literal["edit", "added_row", "deleted_row", "conflict", "setting"] = "edit"
    applied: bool = False
    note: str = ""
