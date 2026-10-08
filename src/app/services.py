"""The two bid operations the routes queue as jobs, independent of how the files arrived.

effort    RFP files -> ingest -> effort team -> ledger -> sizing -> effort workbook   (call 1)
proposal  reviewed workbook (+ RFP files) -> edits -> proposal team -> YASH .docx      (call 2)

Both run the LangGraph workflow of their call inside the bid's workspace. Models resolve per role
(harness.llm); `ensure_models_configured` lets a route fail fast with 422 before a job is queued.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from bidcore.ledger.models import new_ledger
from bidcore.paths import rate_card_path
from bidcore.policy import get_policy
from bidcore.render.workbook import read_bid_sheet
from harness import llm
from harness.context import RunContext
from harness.observability import error_info, load_events, run_log, summarize
from harness.workspace import BidWorkspace

log = logging.getLogger(__name__)
Sink = Callable[[dict[str, Any]], None]
WORKBOOK_SUFFIXES = (".xlsx", ".xlsm")


class ServiceError(ValueError):
    """A request that cannot run as given (maps to HTTP 422)."""


def ensure_models_configured(team: str, run_model: str | None = None) -> None:
    """Every role the team uses must resolve to a model (tests install a model factory instead)."""
    if llm._factory is not None:      # noqa: SLF001 - test/offline factory installed
        return
    cfg = get_policy().runtime.teams[team]
    roles = {cfg["orchestrator"]["role"], *(s["role"] for s in cfg["subagents"])}
    missing = sorted(r for r in roles if not llm.resolve_model_name(r, run_model))
    if missing:
        raise ServiceError(f"no model configured for role(s) {missing}: set LLM_MODEL (a LiteLLM model string, "
                           "e.g. 'gemini/gemini-3.8-flash' or 'bedrock/<model-id>') or pass a model for the run")


@lru_cache(maxsize=1)
def rate_card_sheets() -> list[str]:
    import pandas as pd

    return [str(s) for s in pd.read_parquet(rate_card_path(), columns=["sheet"])["sheet"].unique()]


def check_rate_card_sheet(sheet: str | None) -> str:
    sheet = (sheet or get_policy().effort.rate_card.default_sheet).strip()
    if sheet not in rate_card_sheets():
        raise ServiceError(f"unknown rate card sheet '{sheet}'; expected one of {rate_card_sheets()}")
    return sheet


def bid_of_workbook(path: Path) -> str:
    """The bid id stamped in a reviewed workbook (WorkbookError -> 422 when it is not ours)."""
    return read_bid_sheet(path)["bid_id"]


def prepare_effort(ws: BidWorkspace, client_name: str, rate_card_sheet: str, models: dict[str, str]) -> None:
    if ws.ledger.exists():
        raise ServiceError(f"bid {ws.bid_id} already has a ledger")
    ws.ledger.save(new_ledger(ws.bid_id, client_name or "Client", policy_version=get_policy().version,
                              rate_card_sheet=rate_card_sheet, models=models))


async def _observed(run: RunContext, call: str, work: Any, **detail: Any) -> dict[str, Any]:
    """Run one call with its own trace/run.log, bracketed by run_start / run_end (duration + the
    trace summary totals) or run_error (with traceback)."""
    started = time.time()
    with run_log(run.ws.bid_id, run.ws.trace):
        run.trace.emit("run_start", "", call=call, models=llm.models_in_use(run.run_model), **detail)
        try:
            state = await work
        except Exception as exc:
            run.trace.emit("run_error", "", call=call, ms=int((time.time() - started) * 1000), **error_info(exc))
            raise
        totals = summarize(load_events(run.ws.trace))["totals"]
        run.trace.emit("run_end", "", call=call, ms=int((time.time() - started) * 1000), **totals)
        log.info("%s call finished in %.1fs: %s", call, time.time() - started, totals)
        return state


async def run_effort(ws: BidWorkspace, client_name: str, uploads: list[Path], run_model: str | None,
                     sink: Sink) -> dict[str, Any]:
    from workflows.effort import build_effort_workflow

    run = RunContext(ws=ws, team="effort", run_model=run_model, sink=sink)
    flow = build_effort_workflow(run)
    state = await _observed(run, "effort", flow.ainvoke(
        {"client_name": client_name, "uploads": [str(p) for p in uploads]},
        config={"configurable": {"thread_id": f"{ws.bid_id}-call1"}, "recursion_limit": 50}),
        files=[p.name for p in uploads])
    workbook = Path(state["workbook"])
    ledger = ws.ledger.load()
    return {"bid_id": ws.bid_id, "workbook": workbook.name, "gaps": state.get("gaps", []),
            "notes": state.get("notes", [])[:50], "summary": ledger.figures.get("summary", {}),
            "agent_summary": state.get("agent_summary", "")}


async def run_proposal(ws: BidWorkspace, workbook: Path, rfp_uploads: list[Path], instructions: str,
                       run_model: str | None, sink: Sink) -> dict[str, Any]:
    from workflows.proposal import build_proposal_workflow

    run = RunContext(ws=ws, team="proposal", run_model=run_model, sink=sink)
    flow = build_proposal_workflow(run)
    state = await _observed(run, "proposal", flow.ainvoke(
        {"workbook": str(workbook), "rfp_uploads": [str(p) for p in rfp_uploads], "instructions": instructions or ""},
        config={"configurable": {"thread_id": f"{ws.bid_id}-call2"}, "recursion_limit": 50}),
        files=[workbook.name, *(p.name for p in rfp_uploads)])
    document = Path(state["document"])
    return {"bid_id": ws.bid_id, "document": document.name, "missing_drafts": state.get("missing", []),
            "edits": len(state.get("edits", [])), "agent_summary": state.get("agent_summary", "")}


def bid_summary(ws: BidWorkspace) -> dict[str, Any]:
    if not ws.ledger.exists():
        return {"bid_id": ws.bid_id, "status": "no ledger"}
    ledger = ws.ledger.load()
    counts = {}
    for name in ("capabilities", "scope_items", "non_catalogue", "integrations", "data_migration", "basis",
                 "security", "analytics"):
        section = ledger.section(name)
        counts[name] = {"state": section.state, "rows": len(section.rows)}
    return {"bid_id": ws.bid_id, "client_name": ledger.meta.client_name, "status": ledger.meta.status,
            "created_at": ledger.meta.created_at, "version": ledger.meta.version,
            "rate_card_sheet": ledger.meta.rate_card_sheet, "files": [f.name for f in ledger.meta.files],
            "outputs": [p.name for p in ws.output_files()], "sections": counts,
            "summary": ledger.figures.get("summary", {}), "overrides": len(ledger.overrides)}
