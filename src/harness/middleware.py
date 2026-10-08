"""Harness middleware attached to every agent we spawn.

LedgerGuardMiddleware - section-level ledger permissions. Each agent's toolbox already holds only its
  own ledger_write_<section> tools; the guard enforces the same rule at call time, so a tool that ever
  leaks into the wrong toolbox (e.g. inherited) still cannot write another agent's section.
TraceMiddleware - one event per agent start/stop and per tool call into trace/events.jsonl and the
  job's live progress feed (replaces the old [*-TRACE] log tags with a single ordered record).
LedgerBriefMiddleware - a fresh summary of the ledger an agent works from, in its system message.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from harness.context import Trace
from harness.observability import bind, error_info, llm_content_enabled, preview

WRITE_PREFIX = "ledger_write_"


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
    """Observability for one agent: start / end (with its final answer), every model call (latency,
    tokens, finish reason, output preview, tool calls requested; full record in llm_calls.jsonl)
    and every tool call (args, result preview, errors with traceback). Model and tool failures are
    recorded and re-raised - the trace shows exactly which agent, call and input failed."""

    def __init__(self, agent: str, trace: Trace):
        super().__init__()
        self.agent = agent
        self.trace = trace
        self._calls = 0
        self._started = 0.0

    # ------------------------------------------------------------------ agent
    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        self._started = time.time()
        messages = (state or {}).get("messages") or []
        task = getattr(messages[-1], "content", "") if messages else ""
        self.trace.emit("agent_start", self.agent, task=preview(task))
        return None

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        messages = (state or {}).get("messages") or []
        last = messages[-1] if messages else None
        self.trace.emit("agent_end", self.agent, ms=int((time.time() - self._started) * 1000),
                        messages=len(messages), output=preview(_text(getattr(last, "content", ""))))
        return None

    async def abefore_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.before_agent(state, runtime)

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.after_agent(state, runtime)

    # ------------------------------------------------------------------ model
    def _model_name(self, request: Any) -> str:
        model = getattr(request, "model", None)
        return str(getattr(model, "model", "") or getattr(model, "model_name", "") or type(model).__name__)

    def _record_model(self, request: Any, response: Any, started: float) -> None:
        self._calls += 1
        messages = list(getattr(request, "messages", []) or [])
        result = getattr(response, "result", None) or ([response] if isinstance(response, AIMessage) else [])
        ai = next((m for m in result if isinstance(m, AIMessage)), None)
        usage = getattr(ai, "usage_metadata", None) or {}
        meta = getattr(ai, "response_metadata", None) or {}
        calls = [{"name": c.get("name"), "args": preview(c.get("args"), 300)} for c in (getattr(ai, "tool_calls", None) or [])]
        output = _text(getattr(ai, "content", "")) if ai is not None else ""
        ms = int((time.time() - started) * 1000)
        self.trace.emit("model_call", self.agent, call=self._calls, model=self._model_name(request), ms=ms,
                        messages_in=len(messages), input_tokens=usage.get("input_tokens"),
                        output_tokens=usage.get("output_tokens"),
                        finish_reason=meta.get("finish_reason") or meta.get("stop_reason"),
                        tool_calls=calls, output=preview(output, 600))
        if not output and not calls:
            self.trace.emit("model_empty", self.agent, call=self._calls, level="warning",
                            finish_reason=meta.get("finish_reason") or meta.get("stop_reason"),
                            note="model returned neither text nor tool calls")
        record = {"agent": self.agent, "call": self._calls, "model": self._model_name(request), "ms": ms,
                  "usage": usage, "finish_reason": meta.get("finish_reason"), "tool_calls": calls,
                  "tools_offered": [_tool_name(t) for t in getattr(request, "tools", []) or []]}
        if llm_content_enabled():
            record["last_input"] = _text(getattr(messages[-1], "content", "")) if messages else ""
            record["output"] = output
        self.trace.llm_record(record)

    def _model_failed(self, request: Any, exc: BaseException, started: float) -> None:
        messages = list(getattr(request, "messages", []) or [])
        self.trace.emit("model_error", self.agent, call=self._calls + 1, model=self._model_name(request),
                        ms=int((time.time() - started) * 1000), messages_in=len(messages),
                        last_input=preview(_text(getattr(messages[-1], "content", "")) if messages else "", 500),
                        **error_info(exc))

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        started = time.time()
        with bind(agent=self.agent):
            try:
                response = handler(request)
            except Exception as exc:
                self._model_failed(request, exc, started)
                raise
        self._record_model(request, response, started)
        return response

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        started = time.time()
        with bind(agent=self.agent):
            try:
                response = await handler(request)
            except Exception as exc:
                self._model_failed(request, exc, started)
                raise
        self._record_model(request, response, started)
        return response

    # ------------------------------------------------------------------ tools
    def _emit(self, request: Any, result: Any, started: float) -> None:
        call = request.tool_call
        status = getattr(result, "status", "success") if isinstance(result, ToolMessage) else "success"
        content = getattr(result, "content", result)
        self.trace.emit("tool", self.agent, tool=call.get("name"), ok=status != "error",
                        ms=int((time.time() - started) * 1000), args=preview(call.get("args") or {}, 600),
                        result=preview(_text(content), 600 if status != "error" else 2000))

    def _tool_failed(self, request: Any, exc: BaseException, started: float) -> None:
        call = request.tool_call
        self.trace.emit("tool_error", self.agent, tool=call.get("name"), ok=False,
                        ms=int((time.time() - started) * 1000), args=preview(call.get("args") or {}, 1000),
                        **error_info(exc))

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        started = time.time()
        with bind(agent=self.agent):
            try:
                result = handler(request)
            except Exception as exc:
                self._tool_failed(request, exc, started)
                raise
        self._emit(request, result, started)
        return result

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        started = time.time()
        with bind(agent=self.agent):
            try:
                result = await handler(request)
            except Exception as exc:
                self._tool_failed(request, exc, started)
                raise
        self._emit(request, result, started)
        return result


class LedgerBriefMiddleware(AgentMiddleware):
    """Appends a fresh ledger brief to the agent's system message on every model call, so an agent that
    works FROM the ledger (the catalogue-mapper) always has its inputs - the bid's ISO-2 countries and the
    capability ids - instead of depending on whether it thinks to call ledger_read first. The third live
    run's mapper never read the ledger: it invented 'KSA' / 'EGY' and capability ids and mapped nothing."""

    def __init__(self, agent: str, brief: Callable[[], str]):
        super().__init__()
        self.agent = agent
        self.brief = brief

    def _with_brief(self, request: Any) -> Any:
        try:
            brief = self.brief()
        except Exception:          # the brief is an aid: never fail a model call over it
            return request
        if not brief:
            return request
        system = request.system_message
        if system is None:
            new = SystemMessage(content=brief)
        elif isinstance(system.content, str):
            new = SystemMessage(content=f"{system.content}\n\n{brief}")
        else:
            new = SystemMessage(content=[*system.content, {"type": "text", "text": brief}])
        return request.override(system_message=new)

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return handler(self._with_brief(request))

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        return await handler(self._with_brief(request))


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str((tool.get("function") or {}).get("name") or tool.get("name") or "?")
    return str(getattr(tool, "name", "?"))


def _text(content: Any) -> str:
    if isinstance(content, list):
        return " ".join(b if isinstance(b, str) else str(b.get("text", "")) for b in content
                        if isinstance(b, str) or isinstance(b, dict))
    return str(content or "")
