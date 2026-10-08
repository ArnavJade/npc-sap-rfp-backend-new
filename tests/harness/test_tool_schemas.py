"""Tool schemas sent to the model provider must be Gemini-safe (no empty enum values).

Regression: Gemini answered every effort run with HTTP 400 "...enum[3]: cannot be empty" because
ledger fields such as Wave.kind use "" as their unset enum value.
"""

from __future__ import annotations

import pytest

from bidcore.ledger.models import new_ledger
from harness import llm
from harness.context import RunContext
from harness.tool_schema import clean_schema, safe_tools
from harness.workspace import BidWorkspace


def _enums(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "enum":
                yield path, value
            else:
                yield from _enums(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _enums(item, f"{path}[{i}]")


def _all_tools(tmp_path, team):
    from harness.teams import _extra_tools, team_roster
    from harness.tools.ledger_tools import make_orchestrator_tools, make_read_tools, make_write_tools
    from harness.tools.rfp_tools import make_rfp_tools

    ws = BidWorkspace.open(f"schema-{team}", base=tmp_path)
    ws.ledger.save(new_ledger(ws.bid_id))
    run = RunContext(ws=ws, team=team)
    tools = [*make_read_tools(run), *make_orchestrator_tools(run), *make_rfp_tools(run)]
    for entry in team_roster(run):
        writes = [s for s in entry["writes"] if s not in ("drafts", "review")]
        tools += make_write_tools(run, entry["name"], writes) + _extra_tools(run, entry["name"])
    return tools


def test_clean_schema_drops_empty_enum_values():
    schema = {"properties": {"kind": {"enum": ["a", "", "b"]}, "only": {"enum": [""], "type": "string"}}}
    assert clean_schema(schema) == {"properties": {"kind": {"enum": ["a", "b"]}, "only": {"type": "string"}}}


@pytest.mark.parametrize("team", ["effort", "proposal"])
def test_every_team_tool_schema_is_gemini_safe(tmp_path, team):
    tools = _all_tools(tmp_path, team)
    names = {t.name for t in tools}
    if team == "effort":
        assert "ledger_write_timeline" in names
    cleaned = safe_tools(tools)
    bad = [(t["function"]["name"], path) for t in cleaned for path, values in _enums(t)
           if any(v in ("", None) for v in values) or not values]
    assert bad == []


def test_litellm_model_binds_cleaned_schemas(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-3.8-flash")
    llm.set_model_factory(None)
    model = llm.chat_model("analyst", "rfp-analyst")
    tools = [t for t in _all_tools(tmp_path, "effort") if t.name == "ledger_write_timeline"]
    bound = model.bind_tools(tools)
    sent = bound.kwargs["tools"]
    assert sent and all(v not in ("", None) for _, values in _enums(sent) for v in values)
