"""Call 1 end to end with scripted models: ingest -> effort team (task-tool spawning, ledger writes) ->
coverage check -> sizing -> workbook. Proves the harness wiring, not model quality."""

from __future__ import annotations

import asyncio
import json

import pytest

from bidcore.paths import PROJECT_ROOT
from harness import llm
from harness.context import RunContext
from harness.workspace import BidWorkspace
from tests.harness.fakes import call, factory, stub_skills, turn

RFP = """Request for Proposal - SAP S/4HANA for ACME Foods

ACME Foods requires SAP S/4HANA Finance for Saudi Arabia, including general ledger and asset accounting.

Wave 1: Saudi Arabia 40 weeks including 8 weeks hypercare.

The solution must integrate with Kronos for time and attendance through SAP CPI.

Data migration of material master is in scope.

Role design and authorizations for S/4HANA are in scope.

The bidder shall provide 12 custom reports.
"""

F = "rfp/acme-rfp.md"


def ev(quote: str) -> list[dict]:
    return [{"quote": quote, "file": F, "page": "1"}]


def effort_scripts() -> dict:
    scopes = ["scope-integrations", "scope-ricefw-fiori", "scope-data-migration", "scope-basis", "scope-security",
              "scope-analytics"]
    return {
        "effort-orchestrator": [
            turn(call("read_file", file_path="/rfp/index.md")),
            turn(call("task", subagent_type="rfp-analyst", description="Read the RFP; write profile, capabilities, timeline."),
                 *(call("task", subagent_type=s, description=f"Write your sections ({s}).") for s in scopes)),
            turn(call("task", subagent_type="catalogue-mapper", description="Map capabilities to scope items.")),
            turn(call("task", subagent_type="wave-planner", description="Plan the waves.")),
            turn(call("ledger_check")),
            turn(text="Ledger complete: profile, 1 capability, 1 wave, integrations, workstreams."),
        ],
        "rfp-analyst": [
            turn(call("ledger_write_rfp_profile", data={
                "client_name": "ACME Foods", "engagement_type": "greenfield", "summary": "S/4HANA Finance.",
                "countries": [{"code": "SA", "name": "Saudi Arabia", "evidence": ev("SAP S/4HANA Finance for Saudi Arabia")}],
                "evidence": ev("ACME Foods requires SAP S/4HANA Finance")}),
                 call("ledger_write_capabilities", rows=[{
                     "capability": "Finance - general ledger and asset accounting", "sap_module_hint": "FI",
                     "countries": ["SA"], "evidence": ev("including general ledger and asset accounting")}]),
                 call("ledger_write_timeline", data={
                     "waves": [{"name": "Wave 1", "total_weeks": 40, "hypercare_weeks": 8, "countries": ["SA"],
                                "duration_source": "rfp", "evidence": ev("Wave 1: Saudi Arabia 40 weeks including 8 weeks hypercare")}],
                     "sequencing": "sequential", "hypercare_required": True, "hypercare_mode": "inclusive",
                     "evidence": ev("40 weeks including 8 weeks hypercare")})),
            turn(text="Wrote rfp_profile, capabilities (cap-1), timeline (1 wave)."),
        ],
        "scope-integrations": [
            turn(call("ledger_write_integrations", rows=[{
                "system": "Kronos", "functionality": "Time and attendance", "middleware": "SAP CPI",
                "effort_days": 20, "evidence": ev("integrate with Kronos for time and attendance")}])),
            turn(text="1 integration."),
        ],
        "scope-ricefw-fiori": [
            turn(call("ledger_write_ricefw", data={"rows": [{"object_type": "Report", "no_of_objects": 12,
                                                             "evidence": ev("provide 12 custom reports")}],
                                                   "evidence": ev("provide 12 custom reports")}),
                 call("ledger_write_fiori", none_reason="The RFP names no custom Fiori apps.")),
            turn(text="RICEFW 12 reports; no Fiori."),
        ],
        "scope-data-migration": [
            turn(call("ledger_write_data_migration", rows=[{
                "object": "Material Master", "sap_module": "MM", "evidence": ev("Data migration of material master")}])),
            turn(text="1 object."),
        ],
        "scope-basis": [turn(call("ledger_write_basis", rows=[], none_reason="RFP is silent on Basis.")),
                        turn(text="none")],
        "scope-security": [
            turn(call("ledger_write_security", rows=[{"activity": "Role design", "effort_days": 15,
                                                      "evidence": ev("Role design and authorizations")}])),
            turn(text="1 activity."),
        ],
        "scope-analytics": [turn(call("ledger_write_analytics", rows=[], none_reason="No analytics asked.")),
                            turn(text="none")],
        "catalogue-mapper": [
            turn(call("ledger_write_scope_items", rows=[{"scope_item_id": "J58", "countries": ["SA"],
                                                         "capability_refs": ["cap-1"]}]),
                 call("ledger_write_non_catalogue", rows=[], none_reason="No SAP tools named.")),
            turn(text="1 scope item."),
        ],
        "wave-planner": [
            turn(call("effort_preview", group_by="workstream")),
            turn(call("ledger_write_wave_plan", data={"phases": [{"wave": "Wave 1", "phase_split": {
                "Prepare": 0.1, "Explore": 0.2, "Realize": 0.5, "Deploy": 0.2}}], "notes": "single wave"})),
            turn(text="Wave plan written."),
        ],
    }


@pytest.fixture()
def harness_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLS_DIR", str(stub_skills(tmp_path / "skills", PROJECT_ROOT / "skills")))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "ws"))
    log: dict = {}
    yield tmp_path, log
    llm.set_model_factory(None)


def test_effort_call_end_to_end(harness_env):
    tmp, log = harness_env
    from workflows.effort import build_effort_workflow

    llm.set_model_factory(factory(effort_scripts(), log))
    ws = BidWorkspace.open("e2e1", base=tmp / "ws")
    upload = ws.save_upload("ACME RFP.txt", RFP.encode())
    run = RunContext(ws=ws, team="effort")
    flow = build_effort_workflow(run)
    state = asyncio.run(flow.ainvoke({"client_name": "ACME Foods", "uploads": [str(upload)]},
                                     config={"configurable": {"thread_id": "t"}}))

    ledger = ws.ledger.load()
    assert state["gaps"] == [], state["gaps"]
    assert ledger.rfp_profile.data.countries[0].code == "SA"
    assert ledger.scope_items.rows[0].scope_item_id == "J58" and ledger.scope_items.rows[0].mapping_basis != "finance_core"
    # the Finance core is completed deterministically after the agents (old Layer 2 rule)
    core = [r for r in ledger.scope_items.rows[1:]]
    assert core and all(r.mapping_basis == "finance_core" and r.lob == "Finance" for r in core)
    assert {r.business_area for r in core} <= set(run.policy.catalogue.finance_core_business_areas)
    assert len({r.scope_item_id for r in ledger.scope_items.rows}) == len(ledger.scope_items.rows)
    assert ledger.integrations.rows[0].system == "Kronos" and ledger.integrations.rows[0].written_by == "scope-integrations"
    assert ledger.basis.state == "empty" and ledger.basis.none_reason
    assert ledger.figures["fig"]["total_project_effort"].endswith("person-days")
    assert state["workbook"].endswith(".xlsx") and (ws.outputs / state["workbook"].split("/")[-1]).is_file()
    assert list(ws.ledger.dir.glob("manifest-*.json"))
    # isolation: each specialist got its own bundle and only its own write tools
    assert (ws.skills / "scope-security" / "scope-security" / "SKILL.md").is_file()
    events = [json.loads(line) for line in (ws.trace / "events.jsonl").read_text().splitlines()]
    tools = {(e["agent"], e.get("tool")) for e in events if e["kind"] == "tool"}
    assert ("effort-orchestrator", "task") in tools and ("scope-security", "ledger_write_security") in tools
    assert all(e.get("ok", True) for e in events if e["kind"] == "tool" and e.get("tool", "").startswith("ledger_write"))


def test_specialist_cannot_write_another_section(harness_env):
    tmp, log = harness_env
    from harness.teams import build_team
    from langchain_core.messages import HumanMessage

    scripts = {"effort-orchestrator": [turn(call("task", subagent_type="scope-basis", description="go")),
                                       turn(text="done")],
               "scope-basis": [turn(call("ledger_write_security", rows=[])), turn(text="tried")]}
    llm.set_model_factory(factory(scripts, log))
    ws = BidWorkspace.open("e2e2", base=tmp / "ws")
    from bidcore.ledger.models import new_ledger
    ws.ledger.save(new_ledger("e2e2"))
    run = RunContext(ws=ws, team="effort")
    agent = build_team(run, "ACME")
    asyncio.run(agent.ainvoke({"messages": [HumanMessage(content="go")]}, config={"configurable": {"thread_id": "x"}}))
    assert ws.ledger.load().security.state == "pending"
    replies = [m for msgs in log["scope-basis"].seen for m in msgs if getattr(m, "type", "") == "tool"]
    assert replies and ("not a valid tool" in replies[-1].content.lower() or "DENIED" in replies[-1].content
                        or "not found" in replies[-1].content.lower() or "error" in replies[-1].content.lower())
