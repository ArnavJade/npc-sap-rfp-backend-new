"""Call 1 - RFP -> bid ledger -> effort workbook, as a deterministic LangGraph state machine:

    ingest -> agents -> verify --(sections missing, retries left)--> agents
                           \\-> size -> render -> END

Only the `agents` node is agentic: the effort orchestrator (Deep Agents) spawns its specialists with the
harness's task tool. Everything before and after it is plain Python, so the order of work is fixed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from bidcore.figures import compute_figures
from bidcore.ledger.models import new_ledger
from bidcore.sizing import size_bid
from harness.context import RunContext
from harness.teams import build_team
from harness.tools.ledger_tools import coverage_gaps
from workflows.common import ingest_uploads, last_ai_text, record_sources


class EffortState(TypedDict, total=False):
    client_name: str
    uploads: list[str]
    attempts: int
    gaps: list[str]
    agent_summary: str
    workbook: str
    notes: list[str]


def build_effort_workflow(run: RunContext):
    agent_holder: dict[str, Any] = {}

    def stage(name: str) -> None:
        run.trace.emit("stage", "", stage=name)

    async def ingest(state: EffortState) -> dict:
        stage("ingest")
        store = run.ledger
        if not store.exists():
            store.save(new_ledger(run.ws.bid_id, state.get("client_name") or "Client",
                                  policy_version=run.policy.version,
                                  rate_card_sheet=run.policy.effort.rate_card.default_sheet))
        sources = ingest_uploads(run, [Path(p) for p in state.get("uploads", [])])
        store.update(lambda led: record_sources(led, sources), actor="workflow", action="ingest",
                     detail=", ".join(s.name for s in sources))
        return {"attempts": 0}

    async def agents(state: EffortState) -> dict:
        stage("agents")
        if "agent" not in agent_holder:
            agent_holder["agent"] = build_team(run, state.get("client_name") or "Client")
        agent = agent_holder["agent"]
        if state.get("attempts", 0) == 0:
            message = (f"New SAP bid for {state.get('client_name') or 'the client'} (bid {run.ws.bid_id}). The RFP is "
                       "ingested under /rfp/ (start with /rfp/index.md). Build the bid ledger with your specialists "
                       "following your playbook, then stop.")
        else:
            message = (f"These ledger sections are still pending: {', '.join(state.get('gaps', []))}. Spawn the "
                       "responsible specialists with a precise brief so each is written or recorded as empty with "
                       "a reason, then call ledger_check and stop.")
        limits = run.policy.runtime.limits
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": f"{run.ws.bid_id}-effort"},
                    "recursion_limit": int(limits.get("orchestrator_recursion_limit", 600))})
        return {"agent_summary": last_ai_text(result), "attempts": state.get("attempts", 0) + 1}

    async def verify(state: EffortState) -> dict:
        stage("verify")
        gaps = coverage_gaps(run)
        run.trace.emit("coverage", "", gaps=gaps, attempt=state.get("attempts", 0))
        return {"gaps": gaps}

    def route(state: EffortState) -> str:
        retries = int(run.policy.runtime.limits.get("coverage_retries", 2))
        return "agents" if state.get("gaps") and state.get("attempts", 0) <= retries else "size"

    async def size(state: EffortState) -> dict:
        stage("size")
        ledger = run.ledger.load()
        sizing = size_bid(ledger, run.policy)
        figures = compute_figures(ledger, sizing)
        if state.get("gaps"):
            figures["notes"] = [*figures["notes"], f"sections not produced by the agents: {state['gaps']}"]
        run.ledger.update(lambda led: led.figures.update(figures), actor="workflow", action="size")
        run.ledger.checkpoint("sized")
        return {"notes": figures["notes"]}

    async def render(state: EffortState) -> dict:
        stage("render")
        from bidcore.render.workbook import render_workbook

        ledger = run.ledger.load()
        sizing = size_bid(ledger, run.policy)      # deterministic: identical to the sized figures
        safe = "".join(ch if ch.isalnum() else "_" for ch in ledger.meta.client_name).strip("_") or "Client"
        name = run.policy.workbook["file_name"].format(client=safe, timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"))
        path = render_workbook(ledger, sizing, run.ws.outputs / name, run.policy, manifest_dir=run.ws.ledger.dir)
        run.ledger.update(lambda led: setattr(led.meta, "status", "effort_workbook_ready"), actor="workflow",
                          action="render", detail=path.name)
        run.trace.emit("output", "", file=path.name)
        return {"workbook": str(path)}

    graph = StateGraph(EffortState)
    for name, fn in (("ingest", ingest), ("agents", agents), ("verify", verify), ("size", size), ("render", render)):
        graph.add_node(name, fn)
    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "agents")
    graph.add_edge("agents", "verify")
    graph.add_conditional_edges("verify", route, {"agents": "agents", "size": "size"})
    graph.add_edge("size", "render")
    graph.add_edge("render", END)
    return graph.compile(checkpointer=InMemorySaver())
