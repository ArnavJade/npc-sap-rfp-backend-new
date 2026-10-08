"""Call 2 - reviewed workbook (+ RFP) -> YASH response .docx, as a LangGraph state machine:

    apply_edits -> rfp -> size -> agents -> verify --(drafts missing, retries left)--> agents
                                                \\-> render -> END

Two sources, one document:
* linked - the workbook's hidden `_bid` sheet names a call-1 bid on this server: the reviewer's edits
  come back as a diff against the render manifest and are applied to the SAME ledger call 1 built;
  sizing re-runs on the edited ledger, so every figure equals the reviewed workbook.
* workbook - anything else in the effort-template layout (no `_bid`, another server's, the old agent's,
  hand-made): the ledger is built from the workbook's sheets and every figure, table and diagram is
  taken from the workbook itself (bidcore.render.workbook.reader) - no call-1 dependency at all.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from bidcore.figures import compute_figures
from bidcore.ledger.sections_proposal import Disclosure, ResponseRequirements
from bidcore.outline import narrative_sections
from bidcore.sizing import size_bid
from harness.context import RunContext
from harness.teams import build_team
from workflows.common import staged, ingest_uploads, last_ai_text, record_sources, sha256_of


class ProposalState(TypedDict, total=False):
    workbook: str
    rfp_uploads: list[str]
    instructions: str
    edits: list[dict]
    attempts: int
    missing: list[str]
    agent_summary: str
    document: str


def build_proposal_workflow(run: RunContext):
    holder: dict[str, Any] = {}


    def sizing(state: ProposalState, ledger):
        """Figures for the document: the workbook itself when the bid was built from it, else the ledger."""
        if getattr(ledger.meta, "source", "") == "workbook":
            from bidcore.render.workbook.reader import read_effort_workbook

            if "snapshot" not in holder:
                holder["snapshot"] = read_effort_workbook(Path(state["workbook"]), ledger.meta.client_name)
            return holder["snapshot"].sizing(run.policy)
        return size_bid(ledger, run.policy)

    def linked(workbook: Path) -> bool:
        """Does the workbook carry a `_bid` render this bid knows (ledger + manifest)?"""
        from bidcore.render.workbook.manifest import WorkbookError, manifest_path, read_bid_sheet

        if not run.ledger.exists():
            return False
        try:
            stamp = read_bid_sheet(workbook)
        except (WorkbookError, ValueError, KeyError):
            return False
        return stamp.get("bid_id") == run.ws.bid_id and manifest_path(run.ws.ledger.dir, stamp["render_id"]).is_file()

    async def apply_edits(state: ProposalState) -> dict:
        from bidcore.render.workbook.manifest import apply_overrides, edits_report, read_edits
        from bidcore.render.workbook.reader import read_effort_workbook

        if not linked(Path(state["workbook"])):      # the workbook is the whole input
            snapshot = read_effort_workbook(Path(state["workbook"]))
            holder["snapshot"] = snapshot
            imported = snapshot.ledger(run.ws.bid_id, run.policy)
            if run.ledger.exists():                  # an existing bid keeps its RFP files and client name
                previous = run.ledger.load()
                imported.meta.files = previous.meta.files
                imported.meta.client_name = previous.meta.client_name or imported.meta.client_name
                imported.meta.version = previous.meta.version          # the store keeps counting up
            run.ledger.save(imported)
            (run.ws.notes / "reviewer-edits.md").write_text(
                f"# Effort workbook\n\nBid built from {snapshot.source_file} (no linked call-1 bid): "
                f"{len(snapshot.lines)} catalogue line(s), {len(snapshot.tech_dev)} Tech Dev row(s), "
                f"{len(snapshot.dm_tables)} data-migration wave table(s), {len(snapshot.grids)} resource grid(s).\n",
                encoding="utf-8")
            run.trace.emit("workbook_imported", "", file=snapshot.source_file, lines=len(snapshot.lines),
                           tech_dev=len(snapshot.tech_dev), waves=len(snapshot.grids))
            return {"edits": [], "attempts": 0}
        manifest, edits = read_edits(Path(state["workbook"]), run.ws.ledger.dir)
        summary = run.ledger.update(lambda led: apply_overrides(led, edits), actor="reviewer",
                                    action=f"apply workbook edits (render {manifest.render_id})",
                                    detail=f"{len(edits)} edit(s)")
        (run.ws.notes / "reviewer-edits.md").write_text(
            f"# Reviewer edits to the effort workbook\n\n{summary}\n\n{edits_report(edits)}\n", encoding="utf-8")
        run.trace.emit("edits", "", count=len(edits), summary=summary)
        return {"edits": [e.model_dump() for e in edits], "attempts": 0}

    async def rfp(state: ProposalState) -> dict:
        uploads = [Path(p) for p in state.get("rfp_uploads", [])]
        known = {f.sha256 for f in run.ledger.load().meta.files}
        fresh = [p for p in uploads if sha256_of(p) not in known]
        if fresh:   # an RFP call 1 never saw: ingest it next to the original
            sources = ingest_uploads(run, fresh)
            run.ledger.update(lambda led: record_sources(led, sources), actor="workflow", action="ingest")
        if state.get("instructions", "").strip():
            (run.ws.notes / "presales-instructions.md").write_text(state["instructions"].strip(), encoding="utf-8")
        return {}

    async def size(state: ProposalState) -> dict:
        ledger = run.ledger.load()
        figures = compute_figures(ledger, sizing(state, ledger))
        run.ledger.update(lambda led: led.figures.update(figures), actor="workflow", action="size (call 2)")
        run.ledger.checkpoint("call2-sized")
        return {}

    async def agents(state: ProposalState) -> dict:
        if "agent" not in holder:
            holder["agent"] = build_team(run, run.ledger.load().meta.client_name, state.get("instructions", ""))
        if state.get("attempts", 0) == 0:
            has_rfp = any(p.name != "index.md" for p in run.ws.rfp.glob("*.md"))
            message = ("The effort workbook is reviewed and applied to the ledger. Draft the YASH response following "
                       "your playbook "
                       + ("(the RFP is under /rfp/, start with /rfp/index.md), then stop." if has_rfp else
                          "and stop. No RFP was supplied with this call: do not spawn requirements-analyst; the "
                          "writers draft from the ledger facts (outline, figures, scope sheets) alone."))
        else:
            message = (f"These narrative sections still have no clean draft: {', '.join(state.get('missing', []))}. "
                       "Spawn section-writers for them, then stop.")
        result = await holder["agent"].ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": f"{run.ws.bid_id}-proposal"},
                    "recursion_limit": int(run.policy.runtime.limits.get("orchestrator_recursion_limit", 600))})
        return {"agent_summary": last_ai_text(result), "attempts": state.get("attempts", 0) + 1}

    async def verify(state: ProposalState) -> dict:
        ledger = run.ledger.load()
        if ledger.response_requirements.state == "pending":
            # Old rule: an RFP we could not classify withholds detail (showing unrequested commercials is worse).
            rr = ResponseRequirements(disclosure=Disclosure.high_level("fallback"))
            def fallback(led):
                led.response_requirements.data, led.response_requirements.state = rr, "written"
            run.ledger.update(fallback, actor="workflow", action="disclosure fallback")
        missing = [s.id for s in narrative_sections(ledger) if not (run.ws.drafts / f"{s.id}.md").is_file()]
        run.trace.emit("coverage", "", missing=missing, attempt=state.get("attempts", 0))
        return {"missing": missing}

    def route(state: ProposalState) -> str:
        retries = int(run.policy.runtime.limits.get("coverage_retries", 2))
        return "agents" if state.get("missing") and state.get("attempts", 0) <= retries else "render"

    async def render(state: ProposalState) -> dict:
        from bidcore.render.docx import render_proposal

        ledger = run.ledger.load()
        safe = "".join(ch if ch.isalnum() else "_" for ch in ledger.meta.client_name).strip("_") or "Client"
        out = run.ws.outputs / f"YASH_SAP_RFP_Response_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        path = render_proposal(ledger, sizing(state, ledger), run.ws.drafts, out, run.policy)
        run.ledger.update(lambda led: setattr(led.meta, "status", "proposal_ready"), actor="workflow",
                          action="render docx", detail=path.name)
        run.trace.emit("output", "", file=path.name)
        return {"document": str(path)}

    graph = StateGraph(ProposalState)
    for name, fn in (("apply_edits", apply_edits), ("rfp", rfp), ("size", size), ("agents", agents),
                     ("verify", verify), ("render", render)):
        graph.add_node(name, staged(run, name, fn))
    graph.add_edge(START, "apply_edits")
    graph.add_edge("apply_edits", "rfp")
    graph.add_edge("rfp", "size")
    graph.add_edge("size", "agents")
    graph.add_edge("agents", "verify")
    graph.add_conditional_edges("verify", route, {"agents": "agents", "render": "render"})
    graph.add_edge("render", END)
    return graph.compile(checkpointer=InMemorySaver())
