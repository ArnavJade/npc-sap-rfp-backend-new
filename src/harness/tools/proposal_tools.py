"""Proposal-team tools (call 2). Writers see facts and placeholder KEYS, never write figures.

bid_facts gives each writer only the views its section needs; write_draft saves a section's Markdown
and immediately returns draft_check's verdict (typed figures, unknown or withheld placeholders).
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from bidcore.drafts import check_draft
from bidcore.figures import withheld_keys
from bidcore.ledger.models import Ledger
from bidcore.outline import merged_outline
from harness.context import RunContext


def _withheld(ledger: Ledger) -> list[str]:
    rr = ledger.response_requirements.data
    return rr.disclosure.withheld if rr else []


def _facts(ledger: Ledger, view: str) -> dict | list | str:
    figures, withheld = ledger.figures or {}, _withheld(ledger)
    profile = ledger.rfp_profile.data
    if view == "profile":
        return {"client": ledger.meta.client_name, "engagement_type": profile.engagement_type if profile else "",
                "summary": profile.summary if profile else "",
                "countries": [f"{c.name or c.code} ({c.code})" for c in (profile.countries if profile else [])]}
    if view in ("scope", "scope_by_lob"):
        by_lob: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for s in ledger.scope_items.rows:
            if s.status != "excluded_existing":
                label = s.description if "scope_item_detail" in withheld else f"{s.scope_item_id} {s.description}"
                by_lob[s.lob][s.business_area].append(label)
        if view == "scope":
            return {lob: {ba: len(items) for ba, items in bas.items()} for lob, bas in by_lob.items()}
        return {lob: dict(bas) for lob, bas in by_lob.items()}
    if view == "non_catalogue":
        return [{"name": r.name, "kind": r.kind, "description": r.description} for r in ledger.non_catalogue.rows]
    if view == "integrations":
        return [{"system": r.system, "functionality": r.functionality, "direction": r.direction,
                 "middleware": r.middleware, "sap_modules": r.sap_modules} for r in ledger.integrations.rows]
    if view == "tech_dev":
        ricefw, fiori = ledger.ricefw.data, ledger.fiori.data
        return {"ricefw": ricefw.model_dump(exclude={"evidence"}) if ricefw else None,
                "fiori_apps": (fiori.app_names or fiori.app_count) if fiori else None}
    if view == "workstreams":
        return {"data_migration": [f"{r.object} ({r.status})" for r in ledger.data_migration.rows],
                "basis": [f"{r.activity} ({r.status})" for r in ledger.basis.rows],
                "security": [f"{r.activity} ({r.status})" for r in ledger.security.rows],
                "analytics": [f"{r.object} - {r.object_type} ({r.status})" for r in ledger.analytics.rows]}
    if view == "timeline":
        t = ledger.timeline.data
        return {"waves": figures.get("waves", []), "sequencing": t.sequencing if t else "",
                "programme": figures.get("fig", {}).get("programme_months", ""),
                "numbering_note": t.numbering.alt if t and t.numbering.conflict else ""}
    if view == "team":
        roles = figures.get("roles", [])
        if "resource_location" in withheld:
            roles = [{k: v for k, v in r.items() if k != "location"} for r in roles]
        return roles
    if view == "commercials":
        return {"placeholders": [k for k in ("fig:total_project_effort", "fig:total_project_cost", "table:effort",
                                            "table:cost") if k not in withheld_keys(withheld)],
                "withheld_categories": withheld}
    if view == "requirements":
        rr = ledger.response_requirements.data
        return rr.model_dump(include={"requirements", "disclosure", "instructions_briefs"}) if rr else {}
    if view.startswith("excerpts:"):
        sid = view.split(":", 1)[1]
        rr = ledger.response_requirements.data
        return [e.excerpt for e in (rr.section_excerpts if rr else []) if e.section_id == sid]
    if view == "figures":
        blocked = withheld_keys(withheld)
        return {"fig": [f"fig:{k}" for k in figures.get("fig", {}) if f"fig:{k}" not in blocked],
                "tables": [f"table:{k}" for k in figures.get("tables", []) if f"table:{k}" not in blocked],
                "diagrams": [f"diagram:{k}" for k in figures.get("diagrams", [])],
                "bare_numbers_allowed": figures.get("counts", {}), "withheld_categories": withheld}
    raise ToolException("unknown view; use profile, scope, scope_by_lob, non_catalogue, integrations, tech_dev, "
                        "workstreams, timeline, team, commercials, requirements, excerpts:<section_id>, figures")


class _View(BaseModel):
    view: str = Field(description="profile | scope | scope_by_lob | non_catalogue | integrations | tech_dev | "
                                  "workstreams | timeline | team | commercials | requirements | "
                                  "excerpts:<section_id> | figures")


class _Draft(BaseModel):
    section_id: str = Field(description="Outline section id, e.g. '4.3' or 'R1'.")
    markdown: str = Field(description="The section body in Markdown (no top heading).")


class _SectionId(BaseModel):
    section_id: str


class _Finding(BaseModel):
    section_id: str
    severity: Literal["high", "medium", "low"]
    issue: str
    fix: str


class _Review(BaseModel):
    findings: list[_Finding] = Field(default_factory=list)


def make_proposal_tools(run: RunContext, agent: str) -> list[BaseTool]:
    def outline() -> str:
        led = run.ledger.load()
        rows = ["id | title | level | narrative | artifact | words | facts | briefs | excerpts"]
        for s in merged_outline(led):
            rows.append(f"{s.id} | {s.title} | {s.level} | {'yes' if s.narrative else '-'} | {s.artifact or '-'} | "
                        f"{'-'.join(map(str, s.words)) or '-'} | {','.join(s.facts) or '-'} | "
                        f"{' / '.join(b[:120] for b in s.briefs) or '-'} | {len(s.excerpts)}")
        return "\n".join(rows)

    def _check(led: Ledger, section_id: str):
        section = next((s for s in merged_outline(led) if s.id == section_id), None)
        if section is None:
            raise ToolException(f"no outline section '{section_id}' - call outline()")
        path = run.ws.drafts / f"{section_id}.md"
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        return section, check_draft(section_id, text, led.figures or {}, _withheld(led), run.corpus(), section.words)

    def _verdict(report) -> str:
        head = "CLEAN" if report.clean else "NEEDS FIX"
        return "\n".join([f"{head} ({report.words} words)", *[f"- {p}" for p in report.problems],
                          *[f"- (warning) {w}" for w in report.warnings]])

    def write_draft(section_id: str, markdown: str) -> str:
        led = run.ledger.load()
        section = next((s for s in merged_outline(led) if s.id == section_id), None)
        if section is None or not section.narrative:
            raise ToolException(f"'{section_id}' is not a narrative section - call outline()")
        (run.ws.drafts / f"{section_id}.md").write_text(markdown.strip() + "\n", encoding="utf-8")
        _, report = _check(led, section_id)
        run.trace.emit("draft", agent, section_id=section_id, clean=report.clean, words=report.words)
        return f"Saved /drafts/{section_id}.md. " + _verdict(report)

    def draft_check(section_id: str) -> str:
        return _verdict(_check(run.ledger.load(), section_id)[1])

    def drafts_status() -> str:
        led = run.ledger.load()
        findings = _open_findings(run)
        rows = ["id | title | drafted | check | words | open findings"]
        for s in merged_outline(led):
            if not s.narrative:
                continue
            drafted = (run.ws.drafts / f"{s.id}.md").is_file()
            report = _check(led, s.id)[1] if drafted else None
            rows.append(f"{s.id} | {s.title} | {'yes' if drafted else 'NO'} | "
                        f"{'-' if report is None else ('clean' if report.clean else 'NEEDS FIX')} | "
                        f"{report.words if report else 0} | {findings.get(s.id, 0)}")
        return "\n".join(rows)

    def bid_facts(view: str) -> str:
        return json.dumps(_facts(run.ledger.load(), view.strip()), ensure_ascii=False, default=str)[:20000]

    def write_review(findings: list | None = None) -> str:
        items = [f if isinstance(f, dict) else f.model_dump() for f in (findings or [])]
        rounds = sorted(run.ws.review.glob("round-*.json"))
        path = run.ws.review / f"round-{len(rounds) + 1}.json"
        path.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
        severe = sum(1 for f in items if f["severity"] in ("high", "medium"))
        return f"Saved {len(items)} finding(s) as {path.name}; {severe} high/medium."

    tools = {
        "outline": StructuredTool.from_function(func=outline, name="outline",
                                                description="The response outline incl. client-required sections."),
        "drafts_status": StructuredTool.from_function(func=drafts_status, name="drafts_status",
                                                      description="Which narrative sections are drafted and clean."),
        "bid_facts": StructuredTool.from_function(func=bid_facts, name="bid_facts", args_schema=_View,
                                                  handle_tool_error=True,
                                                  description="Facts about the bid for writing (no figures - "
                                                              "figures are placeholder keys)."),
        "write_draft": StructuredTool.from_function(func=write_draft, name="write_draft", args_schema=_Draft,
                                                    handle_tool_error=True,
                                                    description="Save one section's Markdown draft; returns the check."),
        "draft_check": StructuredTool.from_function(func=draft_check, name="draft_check", args_schema=_SectionId,
                                                    handle_tool_error=True,
                                                    description="Re-check a saved draft (figures, placeholders, length)."),
        "write_review": StructuredTool.from_function(func=write_review, name="write_review", args_schema=_Review,
                                                     description="Record review findings for the writers."),
    }
    per_agent = {
        "proposal-orchestrator": ["outline", "drafts_status"],
        "requirements-analyst": ["outline"],
        "section-writer": ["outline", "bid_facts", "write_draft", "draft_check"],
        "reviewer": ["outline", "drafts_status", "bid_facts", "draft_check", "write_review"],
    }
    return [tools[name] for name in per_agent.get(agent, [])]


def _open_findings(run: RunContext) -> dict[str, int]:
    rounds = sorted(run.ws.review.glob("round-*.json"))
    if not rounds:
        return {}
    counts: dict[str, int] = defaultdict(int)
    for f in json.loads(rounds[-1].read_text(encoding="utf-8")):
        if f.get("severity") in ("high", "medium"):
            counts[f.get("section_id", "")] += 1
    return dict(counts)
