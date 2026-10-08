"""Observability: a run leaves events / llm_calls / errors / run.log, failures are traced with
tracebacks at the agent, stage and run level, and the summary rolls everything up."""

from __future__ import annotations

import asyncio
import json

import pytest

from app import services
from harness import llm
from harness.observability import format_event, load_events, summarize
from harness.workspace import BidWorkspace
from tests.harness.fakes import call, factory, turn
from tests.harness.test_effort_e2e import RFP, effort_scripts, harness_env  # noqa: F401  (fixture)


def _run(tmp, scripts, bid):
    llm.set_model_factory(factory(scripts))
    ws = BidWorkspace.open(bid, base=tmp / "ws")
    upload = ws.save_upload("ACME RFP.txt", RFP.encode())
    services.prepare_effort(ws, "ACME Foods", "SAP BP", {})
    return ws, asyncio.run(services.run_effort(ws, "ACME Foods", [upload], None, lambda e: None))


def test_successful_run_leaves_a_complete_trace(harness_env):  # noqa: F811
    tmp, _ = harness_env
    scripts = effort_scripts()
    scripts["scope-security"].insert(0, turn(call("ledger_write_security", rows=[{
        "activity": "Invented activity", "effort_days": 5,
        "evidence": [{"quote": "this sentence is not in the RFP", "file": "rfp/acme-rfp.md", "page": "1"}]}])))
    ws, result = _run(tmp, scripts, "obs1")
    assert result["workbook"].endswith(".xlsx")
    kinds = {e["kind"] for e in load_events(ws.trace)}
    assert {"run_start", "stage", "stage_end", "agent_start", "agent_end", "model_call", "tool",
            "ledger_write", "ledger_rejected", "run_end"} <= kinds
    events = load_events(ws.trace)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["bid"] == "obs1" for e in events)
    model_calls = load_events(ws.trace, kinds={"model_call"})
    assert any(c["tool_calls"] and c["agent"] == "rfp-analyst" for c in model_calls)
    assert all(c["stage"] == "agents" for c in model_calls)              # stage context reaches agents
    llm_lines = [json.loads(x) for x in (ws.trace / "llm_calls.jsonl").read_text().splitlines()]
    assert len(llm_lines) == len(model_calls) and "tools_offered" in llm_lines[0]
    rejected = load_events(ws.trace, kinds={"ledger_rejected"})
    assert rejected[0]["agent"] == "scope-security" and "not found" in rejected[0]["reasons"][0]
    assert (ws.trace / "errors.jsonl").is_file()
    run_log = (ws.trace / "run.log").read_text()
    assert "obs1" in run_log and "model_call" in run_log and "|agents|rfp-analyst]" in run_log
    summary = summarize(load_events(ws.trace))
    assert summary["agents"]["rfp-analyst"]["model_calls"] >= 2
    assert summary["agents"]["scope-security"]["ledger_rejections"] == 1
    assert {s["stage"] for s in summary["stages"]} >= {"ingest", "agents", "verify", "size", "render"}
    assert all(format_event(e) for e in events)


def test_model_failure_is_traced_at_every_level(harness_env):  # noqa: F811
    tmp, _ = harness_env
    scripts = effort_scripts()
    scripts["scope-basis"] = [RuntimeError("GeminiException BadRequestError - enum[3]: cannot be empty")]
    with pytest.raises(RuntimeError):
        _run(tmp, scripts, "obs2")
    ws = BidWorkspace.open("obs2", base=tmp / "ws", create=False)
    errors = [json.loads(x) for x in (ws.trace / "errors.jsonl").read_text().splitlines()]
    kinds = [e["kind"] for e in errors]
    assert "model_error" in kinds and "stage_error" in kinds and "run_error" in kinds
    model_error = next(e for e in errors if e["kind"] == "model_error")
    assert model_error["agent"] == "scope-basis" and "enum[3]" in model_error["error"]
    assert "Traceback" in model_error["traceback"]
    stage_error = next(e for e in errors if e["kind"] == "stage_error")
    assert stage_error["stage"] == "agents"
    assert "ERROR" in (ws.trace / "run.log").read_text()
    assert summarize(load_events(ws.trace))["totals"]["model_errors"] == 1
