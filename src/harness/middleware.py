"""Harness middleware attached to every agent we spawn.

LedgerGuardMiddleware - section-level ledger permissions. Each agent's toolbox already holds only its
  own ledger_write_<section> tools; the guard enforces the same rule at call time, so a tool that ever
  leaks into the wrong toolbox (e.g. inherited) still cannot write another agent's section.
TraceMiddleware - one event per agent start/stop and per tool call into trace/events.jsonl and the
  job's live progress feed (replaces the old [*-TRACE] log tags with a single ordered record).
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from harness.context import Trace

WRITE_PREFIX = "ledger_write_"


def _short(value: Any, limit: int = 160) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


class LedgerGuardMiddleware(AgentMiddleware):
    def __init__(self, agent: str, allowed_sections: list[str]):
        super().__init__()
        self.agent = agent
        self.allowed = set(allowed_sections)

    def _denied(self, request: Any) -> ToolMessage | None:
        call = request.tool_call
        name, args = call.get("name", ""), call.get("args") or {}
        section = name[len(WRITE_PREFIX):] if name.startswith(WRITE_PREFIX) else (
            args.get("section") if name == "delete_rows" else None)
        if section is None or section in self.allowed:
            return None
        return ToolMessage(
            content=f"DENIED: {self.agent} may only write {sorted(self.allowed) or 'nothing'}; '{section}' "
                    "belongs to another specialist.",
            tool_call_id=call.get("id", ""), name=name, status="error")

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return self._denied(request) or handler(request)

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        denied = self._denied(request)
        return denied if denied is not None else await handler(request)


class TraceMiddleware(AgentMiddleware):
    def __init__(self, agent: str, trace: Trace):
        super().__init__()
        self.agent = agent
        self.trace = trace

    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        self.trace.emit("agent_start", self.agent)
        return None

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        messages = (state or {}).get("messages") or []
        last = messages[-1] if messages else None
        self.trace.emit("agent_end", self.agent, summary=_short(getattr(last, "content", ""), 300))
        return None

    async def abefore_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.before_agent(state, runtime)

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.after_agent(state, runtime)

    def _emit(self, request: Any, result: Any, started: float) -> None:
        call = request.tool_call
        status = getattr(result, "status", "success") if isinstance(result, ToolMessage) else "success"
        args = call.get("args") or {}
        brief = {k: _short(v, 80) for k, v in args.items() if k in ("subagent_type", "description", "file_path",
                                                                     "pattern", "file", "page_from", "query",
                                                                     "module_name", "section", "section_id")}
        self.trace.emit("tool", self.agent, tool=call.get("name"), ok=status != "error",
                        ms=int((time.time() - started) * 1000), args=brief,
                        result=_short(getattr(result, "content", ""), 240) if status == "error" else "")

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        started = time.time()
        result = handler(request)
        self._emit(request, result, started)
        return result

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        started = time.time()
        result = await handler(request)
        self._emit(request, result, started)
        return result
