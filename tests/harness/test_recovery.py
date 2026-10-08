"""Fixes from the first live Gemini run (app.log of the ARASCO effort call): empty replies, invented
tool names, the literal/case-sensitive grep, rejected verbatim table quotes, catalogue limits."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from bidcore.evidence import CorpusIndex
from harness.recovery import ModelRecoveryMiddleware, RfpGrepMiddleware, resolve_tool_name, search_rfp

TOOLS = ["ls", "read_file", "grep", "ledger_write_scope_items", "ledger_write_non_catalogue", "catalogue_search"]


class _Trace:
    def __init__(self):
        self.events = []

    def emit(self, kind, agent="", **data):
        self.events.append((kind, data))


@dataclass
class _Model:
    model: str = "gemini/gemini-2.5-flash"


@dataclass
class _Request:
    messages: list
    model: Any = field(default_factory=_Model)
    model_settings: dict = field(default_factory=dict)
    tool_choice: Any = None
    tools: list = field(default_factory=lambda: [{"type": "function", "function": {
        "name": n, "parameters": {"properties": {"rows": {}} if n.startswith("ledger_write") else {"pattern": {}}}}}
        for n in TOOLS])

    def override(self, **kw):
        return replace(self, **kw)


@dataclass
class _Response:
    result: list


def test_resolve_invented_tool_names():
    assert resolve_tool_name("LedgerWriteScopeItemsRows", TOOLS) == "ledger_write_scope_items"
    assert resolve_tool_name("write_non_catalogue", TOOLS) == "ledger_write_non_catalogue"
    assert resolve_tool_name("ledger_write_security", TOOLS) is None        # another agent's section stays invalid
    assert resolve_tool_name("grep", TOOLS) == "grep"


def test_empty_reply_is_retried_with_a_nudge():
    trace, seen = _Trace(), []
    replies = [AIMessage(content=""), AIMessage(content="", tool_calls=[
        {"name": "LedgerWriteScopeItemsRows", "args": {"scope_item_id": "J58"}, "id": "c1", "type": "tool_call"}])]

    def handler(request):
        seen.append(request.messages)
        return _Response([replies.pop(0)])

    mw = ModelRecoveryMiddleware("catalogue-mapper", trace, retries=2)
    out = mw.wrap_model_call(_Request([HumanMessage(content="go")]), handler)
    call = out.result[0].tool_calls[0]
    assert call["name"] == "ledger_write_scope_items" and call["args"] == {"rows": [{"scope_item_id": "J58"}]}
    assert len(seen) == 2 and "previous reply was empty" in seen[1][-1].content
    assert [k for k, _ in trace.events] == ["model_retry", "tool_repaired"]


def test_persistent_empty_reply_becomes_a_visible_message():
    mw = ModelRecoveryMiddleware("scope-integrations", _Trace(), retries=1)
    out = mw.wrap_model_call(_Request([HumanMessage(content="go")]), lambda r: _Response([AIMessage(content="")]))
    assert "no output" in out.result[0].content


def _rfp(tmp: Path) -> Path:
    (tmp / "index.md").write_text("# RFP index\nRISE everywhere\n")
    (tmp / "main.md").write_text("<!-- page: 1 -->\nThe SAP S/4HANA RISE programme.\n<!-- page: 2 -->\n"
                                 "|Bank Communication Man-<br>agement:|Single Sign-On|\n<!-- page: 3 -->\nKPI dashboards\n")
    return tmp


def test_rfp_grep_is_case_insensitive_and_page_aware(tmp_path):
    rfp = _rfp(tmp_path)
    assert "/rfp/main.md p.1:" in search_rfp(rfp, "rise")
    assert "index.md" not in search_rfp(rfp, "rise")
    assert "p.2" in search_rfp(rfp, "single sign-on|kpi", page_from=2, page_to=2)
    assert "p.3" not in search_rfp(rfp, "single sign-on|kpi", page_from=2, page_to=2)
    assert "No matches" in search_rfp(rfp, "Datasphere")


@dataclass
class _ToolRequest:
    tool_call: dict
    tool: Any = None

    def override(self, **kw):
        return replace(self, **kw)


def test_grep_middleware_answers_rfp_searches_and_normalises_others(tmp_path):
    mw = RfpGrepMiddleware(_rfp(tmp_path))
    # the call shapes Gemini sent: glob = a full path, invented file / page_from arguments
    for args in ({"pattern": "RISE", "glob": "/rfp/main.md"}, {"pattern": "rise", "file": "/rfp/main.md"},
                 {"pattern": "RISE", "file_path": "/rfp/main.md", "page_from": 1}):
        out = mw.wrap_tool_call(_ToolRequest({"name": "grep", "args": args, "id": "g"}), lambda r: None)
        assert isinstance(out, ToolMessage) and "p.1" in out.content
    passed = {}
    mw.wrap_tool_call(_ToolRequest({"name": "grep", "args": {"pattern": "x", "path": "/skills/a/SKILL.md"}, "id": "g"}),
                      lambda r: passed.update(r.tool_call["args"]))
    assert passed == {"pattern": "x", "output_mode": "content", "path": "/skills/a/", "glob": "SKILL.md"}


def test_evidence_survives_table_markup():
    corpus = CorpusIndex("<!-- page: 29 -->\n|**Treasury &**<br>**Risk**|Bank Communication Man-<br>agement:|\n"
                         "Output set-up File &amp; Output.\nThe Bank Communication management module will be used to "
                         "process the Payment Batching, Payment approval, payment monitoring and bank Statement monitoring.")
    assert corpus.contains("Bank Communication Management")
    assert corpus.contains("File & Output") and corpus.contains("Treasury and Risk")
    assert corpus.contains("Bank Communication management module is used to process the Payment Batching, "
                           "Payment approval, payment monitoring and bank Statement monitoring")   # 1 word differs
    assert not corpus.contains("Payroll for Germany is handled by an external provider")


def test_empty_reply_escalates_thinking_off_then_forced_tool_call():
    seen = []

    def handler(request):
        seen.append(request)
        return _Response([AIMessage(content="")] if len(seen) < 4 else [AIMessage(content="", tool_calls=[
            {"name": "grep", "args": {"pattern": "x"}, "id": "c", "type": "tool_call"}])])

    out = ModelRecoveryMiddleware("scope-basis", _Trace(), retries=3).wrap_model_call(
        _Request([HumanMessage(content="go")]), handler)
    assert out.result[0].tool_calls[0]["name"] == "grep"
    assert seen[1].model_settings == {} and seen[2].model_settings == {"reasoning_effort": "disable"}
    assert seen[3].tool_choice == "any" and seen[3].model_settings == {"reasoning_effort": "disable"}


def test_fallback_model_is_the_last_rung():
    seen = []
    fallback = _Model("bedrock/claude")

    def handler(request):
        seen.append(request.model)
        return _Response([AIMessage(content="done" if request.model is fallback else "")])

    out = ModelRecoveryMiddleware("x", _Trace(), retries=1, fallback=fallback).wrap_model_call(
        _Request([HumanMessage(content="go")]), handler)
    assert out.result[0].content == "done" and seen[-1] is fallback and len(seen) == 3


def test_completion_guard_sends_the_agent_back_until_its_sections_are_written():
    from harness.recovery import GUARD_MARK, SectionCompletionMiddleware

    state = {"basis": "pending"}
    trace = _Trace()
    guard = SectionCompletionMiddleware("scope-basis", ["basis"], lambda: state, lambda: "", trace, max_nudges=2)
    msgs = [HumanMessage(content="go"), AIMessage(content="I am done.")]
    out = guard.after_model({"messages": msgs}, None)
    assert out["jump_to"] == "model" and GUARD_MARK in out["messages"][0].content and "basis" in out["messages"][0].content
    msgs += out["messages"] + [AIMessage(content="still done")]
    assert guard.after_model({"messages": msgs}, None)["jump_to"] == "model"
    msgs += [HumanMessage(content=GUARD_MARK), AIMessage(content="done")]
    assert guard.after_model({"messages": msgs}, None) is None            # nudge budget spent
    state["basis"] = "empty"
    assert guard.after_model({"messages": [AIMessage(content="done")]}, None) is None
    calling = AIMessage(content="", tool_calls=[{"name": "grep", "args": {}, "id": "c", "type": "tool_call"}])
    state["basis"] = "pending"
    assert guard.after_model({"messages": [calling]}, None) is None        # still working


def test_empty_section_needs_the_rfp_read_first(tmp_path):
    import pytest
    from langchain_core.tools import ToolException

    from bidcore.ledger.models import new_ledger
    from harness.context import RunContext
    from harness.tools.ledger_tools import write_rows
    from harness.tools.rfp_tools import make_rfp_tools
    from harness.workspace import BidWorkspace

    ws = BidWorkspace.open("gate1", base=tmp_path / "ws")
    ws.ledger.save(new_ledger("gate1"))
    (ws.rfp / "main.md").write_text("".join(f"<!-- page: {n} -->\nPage {n} text.\n" for n in range(1, 13)))
    run = RunContext(ws=ws, team="effort")
    with pytest.raises(ToolException, match="read the whole RFP"):
        write_rows(run, "scope-basis", "basis", [], "append", "nothing")
    nxt = next(t for t in make_rfp_tools(run, "scope-basis") if t.name == "read_next_pages")
    first = nxt.invoke({})
    assert "p.1-8" in first and "4 page(s) still unread" in first
    assert "whole RFP" in nxt.invoke({}) and run.coverage("scope-basis") == 1.0
    assert write_rows(run, "scope-basis", "basis", [], "append", "nothing").startswith("Recorded basis as empty")


def test_integration_candidates_collects_diagram_text_and_legacy_lists(tmp_path):
    import json

    from bidcore.ledger.models import new_ledger
    from harness.context import RunContext
    from harness.tools.integration_tools import make_integration_tools, uncovered_candidates
    from harness.workspace import BidWorkspace

    ws = BidWorkspace.open("int1", base=tmp_path / "ws")
    ws.ledger.save(new_ledger("int1"))
    (ws.rfp / "main.md").write_text(
        "<!-- page: 16 -->\n## Integrations required\n<!-- Start of picture text -->\nSD DB HHT - MIRNA Wincos Brill "
        "REST CPI Qlik ZATCA\n<!-- End of picture text -->\n<!-- page: 30 -->\nNothing here.\n"
        "<!-- page: 52 -->\n### 13.1 Legacy Applications details & Integrations required\n- MTech poultry system\n"
        "- LIMS laboratory system\n")
    (ws.cache / "prescan.json").write_text(json.dumps({"third_party_candidates": [
        {"name": "Afaqy", "file": "main.md", "page": 52}, {"name": "Qlik", "file": "main.md", "page": 16}]}))
    run = RunContext(ws=ws, team="effort")
    [tool] = make_integration_tools(run)
    out = tool.invoke({})
    assert "Wincos" in out and "p.16" in out and "MTech poultry system" in out and "Afaqy" in out
    assert "Nothing here" not in out
    assert uncovered_candidates(run, ["Qlik Sense"]) == ["Afaqy (p.52)"]
