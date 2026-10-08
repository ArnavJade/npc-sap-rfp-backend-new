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
class _Request:
    messages: list
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
