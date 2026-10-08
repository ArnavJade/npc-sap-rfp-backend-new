"""Building blocks shared by every ledger section."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["In Scope", "Out of Scope"]
Complexity = Literal["Low", "Medium", "High"]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Evidence(BaseModel):
    """A verbatim quote from the RFP and where it is. ledger_write checks the quote exists."""
    model_config = ConfigDict(extra="ignore")
    quote: str = Field(description="Exact words copied from the RFP (max ~300 characters).")
    file: str = Field("", description="RFP workspace file, e.g. 'rfp/main-rfp.md'.")
    page: str = Field("", description="Page / slide / block marker the quote sits under, e.g. '12'.")


class Row(BaseModel):
    """Every ledger row: stable id, evidence, author. row_id is assigned by ledger_write when empty."""
    model_config = ConfigDict(extra="ignore")
    row_id: str = Field("", description="Leave empty for new rows; give the existing id to update a row.")
    evidence: list[Evidence] = Field(default_factory=list)
    note: str = ""
    written_by: str = Field("", description="Set by the tool, not by the agent.")


T = TypeVar("T")

SectionState = Literal["pending", "written", "empty"]


class RowSection(BaseModel, Generic[T]):
    """A list section. `empty` + none_reason means the agent looked and found nothing - which is
    different from `pending` (nobody looked yet); the coverage check only accepts the former."""
    state: SectionState = "pending"
    rows: list[T] = Field(default_factory=list)
    none_reason: str = ""
    written_by: list[str] = Field(default_factory=list)
    updated_at: str = ""


class ObjectSection(BaseModel, Generic[T]):
    state: SectionState = "pending"
    data: T | None = None
    none_reason: str = ""
    written_by: list[str] = Field(default_factory=list)
    updated_at: str = ""


class AuditEvent(BaseModel):
    ts: str = Field(default_factory=utcnow)
    actor: str
    action: str
    section: str = ""
    detail: str = ""
