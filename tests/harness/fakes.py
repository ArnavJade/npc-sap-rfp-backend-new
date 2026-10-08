"""Scripted chat models for harness tests: each agent replays its own list of AI turns."""

from __future__ import annotations

import itertools
import shutil
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_ids = itertools.count(1)


def call(name: str, **args: Any) -> dict:
    return {"name": name, "args": args, "id": f"call_{next(_ids)}", "type": "tool_call"}


def turn(*calls: dict, text: str = "") -> AIMessage:
    return AIMessage(content=text, tool_calls=list(calls))


class ScriptedModel(BaseChatModel):
    """Returns the agent's scripted turns in order, then a plain 'done' message forever."""

    agent: str
    script: list[Any]
    seen: list[list[Any]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        message = self.script.pop(0) if self.script else AIMessage(content=f"{self.agent}: done.")
        if isinstance(message, BaseException):
            raise message
        return ChatResult(generations=[ChatGeneration(message=message.model_copy())])


def factory(scripts: dict[str, list[AIMessage]], log: dict[str, ScriptedModel] | None = None):
    def make(role: str, agent: str) -> ScriptedModel:
        model = ScriptedModel(agent=agent, script=scripts.setdefault(agent, []), seen=[])
        if log is not None:
            log[agent] = model
        return model
    return make


STUB = """---
name: {name}
description: Test stub for {name}.
metadata:
  owner: "tests"
  version: "0"
{extra}---

# {name}

Stub skill used by the harness tests.
"""

SCOPE_STUBS = {
    "scope-integrations": "integrations", "scope-ricefw-fiori": "ricefw,fiori",
    "scope-data-migration": "data_migration", "scope-basis": "basis", "scope-security": "security",
    "scope-analytics": "analytics,analytics_scope",
}


def stub_skills(root: Path, real: Path) -> Path:
    """A skills dir with stub SKILL.md files for every skill the teams reference (outline is real)."""
    root.mkdir(parents=True, exist_ok=True)
    names = ["estimating", "rfp-reading", "sap-scope-mapping", "wave-planning", "client-requirements",
             "proposal-writing", "bid-review"]
    for name in names:
        (root / name).mkdir(exist_ok=True)
        (root / name / "SKILL.md").write_text(STUB.format(name=name, extra=""), encoding="utf-8")
    for name, sections in SCOPE_STUBS.items():
        (root / name).mkdir(exist_ok=True)
        (root / name / "SKILL.md").write_text(
            STUB.format(name=name, extra=f'  ledger_sections: "{sections}"\n'), encoding="utf-8")
    shutil.copytree(real / "proposal-outline", root / "proposal-outline", dirs_exist_ok=True)
    return root
