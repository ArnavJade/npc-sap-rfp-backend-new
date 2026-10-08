"""The response outline: skills/proposal-outline/outline.yaml + what the client's RFP requires.

A client requirement either maps onto an existing section (it becomes part of that section's brief)
or needs a new section, which is rendered right after its anchor section. An indicative breakdown or a
phase plan gets a ledger-driven table instead of figures written by a model.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from bidcore.ledger.models import Ledger
from bidcore.paths import skills_dir


class OutlineSection(BaseModel):
    id: str
    title: str
    level: int = 2
    narrative: bool = False
    artifact: str = ""
    words: list[int] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    guidance: str = ""
    combine_resource_effort: bool = False
    client_required: bool = False
    anchor: str = ""            # client-required sections render after this section
    briefs: list[str] = Field(default_factory=list)
    excerpts: list[str] = Field(default_factory=list)


def outline_path() -> Path:
    return skills_dir() / "proposal-outline" / "outline.yaml"


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> list[dict]:
    return (yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}).get("sections", [])


def base_outline(client_name: str = "the client") -> list[OutlineSection]:
    path = outline_path()
    raw = _load(str(path), path.stat().st_mtime) if path.is_file() else []
    sections = []
    for entry in raw:
        entry = dict(entry)
        entry["id"] = str(entry["id"])
        entry["title"] = str(entry.get("title", "")).replace("{client_name}", client_name)
        sections.append(OutlineSection(**{k: v for k, v in entry.items() if k in OutlineSection.model_fields}))
    return sections


def merged_outline(ledger: Ledger) -> list[OutlineSection]:
    sections = base_outline(ledger.meta.client_name)
    by_id = {s.id: s for s in sections}
    rr = ledger.response_requirements.data
    if rr is None:
        return sections
    for e in rr.section_excerpts:
        if e.section_id in by_id:
            by_id[e.section_id].excerpts.append(e.excerpt)
    for sid, brief in rr.instructions_briefs.items():
        if sid in by_id and brief.strip():
            by_id[sid].briefs.append(f"Presales instruction: {brief.strip()}")
    extra: dict[str, list[OutlineSection]] = {}
    for n, req in enumerate(rr.requirements, start=1):
        artifact = ""
        if req.kind == "indicative_breakdown":
            artifact = f"table:indicative_breakdown:{req.group_by or 'workstream'}"
        elif req.kind == "phase_plan":
            artifact = "table:wave_plan"
        target = by_id.get(req.maps_to_section_id)
        if target is not None:
            target.briefs.append(f"Client requirement '{req.title}': {req.intent}")
            if artifact and not target.artifact:
                target.artifact = artifact
            continue
        anchor = req.placement_after_section_id if req.placement_after_section_id in by_id else sections[-1].id
        extra.setdefault(anchor, []).append(OutlineSection(
            id=f"R{n}", title=req.title, level=3, narrative=True, artifact=artifact, words=[150, 400],
            facts=["requirements", "profile"], client_required=True, anchor=anchor,
            briefs=[f"Client requirement: {req.intent}"]))
    out: list[OutlineSection] = []
    for section in sections:
        out.append(section)
        out.extend(extra.get(section.id, []))
    return out


def narrative_sections(ledger: Ledger) -> list[OutlineSection]:
    return [s for s in merged_outline(ledger) if s.narrative]
