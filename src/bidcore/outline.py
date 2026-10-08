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


TABLE_KINDS = ("indicative_breakdown", "phase_plan")
DEFAULT_ANCHOR = {"indicative_breakdown": "6.1", "phase_plan": "4.3", "narrative": "6.1"}
CLIENT_WORDS = {"narrative": [80, 150], "indicative_breakdown": [30, 90], "phase_plan": [50, 200]}
ADDITIONAL_ID = "additional"


def merged_outline(ledger: Ledger) -> list[OutlineSection]:
    """Standard outline + client-required sections, by the proposal-outline skill's placement rules:
    a table-shaped requirement always gets its own section (anchor: placement, else mapped section,
    else 4.3 / 6.1); a narrative requirement with a valid mapped section folds into it, otherwise it
    gets its own section after its placement (else 6.1). New sections are level 3, numbered
    <anchor>.<n>, and render right after their anchor. An `additional` presales brief adds a final
    level-1 section."""
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

    def valid(section_id: str) -> str:
        return section_id if section_id in by_id else ""

    extra: dict[str, list[OutlineSection]] = {}
    for req in rr.requirements:
        target = valid(req.maps_to_section_id)
        if req.kind not in TABLE_KINDS and target:
            by_id[target].briefs.append(f"Client requirement '{req.title}': {req.intent}")
            continue
        anchor = (valid(req.placement_after_section_id) or target or DEFAULT_ANCHOR[req.kind])
        anchor = anchor if anchor in by_id else sections[-1].id
        artifact = ""
        if req.kind == "indicative_breakdown":
            artifact = f"table:indicative_breakdown:{req.group_by or 'workstream'}"
        elif req.kind == "phase_plan":
            artifact = "table:wave_plan"
        siblings = extra.setdefault(anchor, [])
        siblings.append(OutlineSection(
            id=f"{anchor}.{len(siblings) + 1}", title=req.title, level=3, narrative=True, artifact=artifact,
            words=list(CLIENT_WORDS[req.kind]), facts=["requirements", "profile", "timeline"]
            if req.kind == "phase_plan" else ["requirements", "profile"], client_required=True, anchor=anchor,
            briefs=[f"Client requirement ({req.kind}{', by ' + req.group_by if req.group_by else ''}): {req.intent}"]))
    out: list[OutlineSection] = []
    for section in sections:
        out.append(section)
        out.extend(extra.get(section.id, []))
    additional = (rr.instructions_briefs.get(ADDITIONAL_ID) or "").strip()
    if additional:
        out.append(OutlineSection(id=ADDITIONAL_ID, title="Additional Client-Requested Notes", level=1,
                                  narrative=True, words=[60, 200], facts=["requirements", "profile"],
                                  briefs=[f"Presales instruction: {additional}"]))
    return out


def narrative_sections(ledger: Ledger) -> list[OutlineSection]:
    return [s for s in merged_outline(ledger) if s.narrative]
