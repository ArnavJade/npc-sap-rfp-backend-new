"""Model-side robustness for every agent: what the first live Gemini run showed goes wrong.

ModelRecoveryMiddleware
  * Empty turns. Gemini Flash regularly answers a turn with neither text nor a tool call (out=0
    tokens; typically after a long tool result, or when it gives up on a large function call). Deep
    Agents treats that as "done", so the specialist ended with no output and its sections stayed
    pending (40 such turns in one ARASCO run: integrations, security and the timeline were never
    written). The turn is now retried with a nudge, up to `retries` times; a final empty turn is
    replaced by a short text so the orchestrator at least sees what happened.
  * Invented tool names. The model sometimes calls a tool by a name derived from its schema
    (`LedgerWriteScopeItemsRows` for `ledger_write_scope_items`, with a single row as the arguments).
    Calls to unknown tools are mapped to the offered tool whose normalised name they contain, and a
    single row is wrapped into `rows=[...]` for the row-section write tools.

RfpGrepMiddleware
  The harness's `grep` is a literal, case-sensitive search whose `glob` is a file-name filter. Agents
  called it with `glob="/rfp/<file>.md"` (matches nothing, so "RISE" was "not found" in a RISE RFP),
  with invented `file`/`file_path`/`page_from` arguments (ignored, so the search ran over every mount
  and returned other agents' skill files). Searches of the RFP are now answered here: case-insensitive,
  page-aware (`file p.N: ...`), restricted to /rfp/ unless another mount is asked for explicitly, and
  honouring page_from/page_to. Other paths go to the harness's grep with the arguments normalised.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from harness.context import Trace

EMPTY_FORCE = ("Your previous replies were empty. You MUST call one of your tools now: the next read "
               "(read_next_pages / read_section) or your ledger write tool (rows=[] with a none_reason only if you "
               "have read the whole RFP and found nothing).")
EMPTY_NUDGE = (
    "Your previous reply was empty: no text and no tool call. Continue the task now. Call your next tool, "
    "or, if every one of your sections is written (or recorded empty with a none_reason), reply with your "
    "3-6 line summary. If you were about to write many rows, send them in smaller batches (at most 10 rows "
    "per call) with short evidence quotes.")
EMPTY_FALLBACK = ("(no output: the model returned empty replies {n} times in a row; check ledger_status for "
                  "what this specialist wrote)")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str((tool.get("function") or {}).get("name") or tool.get("name") or "")
    return str(getattr(tool, "name", "") or "")


def _tool_params(tool: Any) -> set[str]:
    if isinstance(tool, dict):
        params = (tool.get("function") or tool).get("parameters") or {}
        return set((params.get("properties") or {}).keys())
    try:
        return set((getattr(tool, "args", None) or {}).keys())
    except Exception:
        return set()


def _text(content: Any) -> str:
    if isinstance(content, list):
        return " ".join(b if isinstance(b, str) else str(b.get("text", "")) for b in content
                        if isinstance(b, (str, dict)))
    return str(content or "")


def resolve_tool_name(name: str, offered: list[str]) -> str | None:
    """The offered tool an invented name most plausibly means, or None."""
    if name in offered:
        return name
    key = _norm(name)
    if not key:
        return None
    by_key = {_norm(t): t for t in offered}
    if key in by_key:
        return by_key[key]
    # 'LedgerWriteScopeItemsRows' contains 'ledgerwritescopeitems'; take the longest such tool name.
    contained = [t for k, t in by_key.items() if len(k) >= 6 and k in key]
    if contained:
        return max(contained, key=len)
    # 'write_scope_items' -> 'ledger_write_scope_items'
    containing = [t for k, t in by_key.items() if len(key) >= 6 and key in k]
    return containing[0] if len(containing) == 1 else None


class ModelRecoveryMiddleware(AgentMiddleware):
    """Empty replies are retried on an escalation ladder (the second live run showed a plain nudge alone
    does not help - Gemini Flash answered the same context with nothing three times in a row):

      1. the same request + a nudge to continue;
      2. + thinking switched off (Gemini 2.5 spends its turn thinking and emits nothing);
      3. + tool_choice="any": the provider must return a tool call;
      4. the role's fallback model (LLM_MODEL_FALLBACK / policy models.fallback), when configured.
    """

    def __init__(self, agent: str, trace: Trace, retries: int = 3, fallback: Any = None):
        super().__init__()
        self.agent = agent
        self.trace = trace
        self.retries = retries
        self.fallback = fallback

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _ai(response: Any) -> AIMessage | None:
        if isinstance(response, AIMessage):
            return response
        result = getattr(response, "result", None) or []
        return next((m for m in result if isinstance(m, AIMessage)), None)

    @staticmethod
    def _replace_ai(response: Any, ai: AIMessage) -> Any:
        if isinstance(response, AIMessage):
            return ai
        result = list(getattr(response, "result", None) or [])
        for i, message in enumerate(result):
            if isinstance(message, AIMessage):
                result[i] = ai
                break
        try:
            response.result = result
        except Exception:
            pass
        return response

    @classmethod
    def _is_empty(cls, response: Any) -> bool:
        ai = cls._ai(response)
        return ai is not None and not _text(ai.content).strip() and not (ai.tool_calls or [])

    def _repair(self, request: Any, response: Any) -> Any:
        ai = self._ai(response)
        if ai is None or not ai.tool_calls:
            return response
        tools = list(getattr(request, "tools", None) or [])
        offered = [_tool_name(t) for t in tools]
        params = {_tool_name(t): _tool_params(t) for t in tools}
        changed, calls = False, []
        for call in ai.tool_calls:
            name = call.get("name", "")
            if name in offered:
                calls.append(call)
                continue
            target = resolve_tool_name(name, offered)
            if target is None:
                calls.append(call)
                continue
            args = dict(call.get("args") or {})
            if "rows" in params.get(target, set()) and "rows" not in args and args:
                args = {"rows": [args]}
            self.trace.emit("tool_repaired", self.agent, called=name, mapped_to=target, level="warning")
            calls.append({**call, "name": target, "args": args})
            changed = True
        if not changed:
            return response
        return self._replace_ai(response, ai.model_copy(update={"tool_calls": calls, "invalid_tool_calls": []}))

    def _attempts(self, request: Any) -> list[tuple[str, Any]]:
        """(label, request) for each retry, in escalation order."""
        model_name = str(getattr(request.model, "model", "") or getattr(request.model, "model_name", "")).lower()
        settings = dict(getattr(request, "model_settings", None) or {})
        no_thinking = {**settings, "reasoning_effort": "disable"} if "gemini" in model_name else settings
        ladder = [("nudge", request.override(messages=[*request.messages, HumanMessage(content=EMPTY_NUDGE)])),
                  ("thinking off", request.override(messages=[*request.messages, HumanMessage(content=EMPTY_NUDGE)],
                                                    model_settings=no_thinking)),
                  ("tool call forced", request.override(messages=[*request.messages, HumanMessage(content=EMPTY_FORCE)],
                                                        model_settings=no_thinking, tool_choice="any"))]
        ladder = ladder[:max(self.retries, 0)]
        if self.fallback is not None:
            ladder.append(("fallback model", request.override(
                model=self.fallback, messages=[*request.messages, HumanMessage(content=EMPTY_NUDGE)])))
        return ladder

    def _fallback(self, response: Any) -> Any:
        ai = self._ai(response)
        if ai is None:
            return response
        tries = self.retries + 1 + (1 if self.fallback is not None else 0)
        return self._replace_ai(response, ai.model_copy(update={"content": EMPTY_FALLBACK.format(n=tries)}))

    # ------------------------------------------------------------------ hooks
    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        response = handler(request)
        for attempt, (label, retry) in enumerate(self._attempts(request) if self._is_empty(response) else [], 1):
            self.trace.emit("model_retry", self.agent, attempt=attempt, reason="empty reply", strategy=label,
                            level="warning")
            try:
                response = handler(retry)
            except Exception as exc:     # e.g. a provider that rejects a setting: try the next rung
                self.trace.emit("model_retry_failed", self.agent, attempt=attempt, strategy=label,
                                error=str(exc)[:300], level="warning")
                continue
            if not self._is_empty(response):
                break
        if self._is_empty(response):
            return self._fallback(response)
        return self._repair(request, response)

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        response = await handler(request)
        for attempt, (label, retry) in enumerate(self._attempts(request) if self._is_empty(response) else [], 1):
            self.trace.emit("model_retry", self.agent, attempt=attempt, reason="empty reply", strategy=label,
                            level="warning")
            try:
                response = await handler(retry)
            except Exception as exc:
                self.trace.emit("model_retry_failed", self.agent, attempt=attempt, strategy=label,
                                error=str(exc)[:300], level="warning")
                continue
            if not self._is_empty(response):
                break
        if self._is_empty(response):
            return self._fallback(response)
        return self._repair(request, response)


# ============================================================================ grep
_PAGE_RE = re.compile(r"^<!-- page: (\d+) -->$")
_TAG_RE = re.compile(r"<[^>]{1,40}>")
MAX_MATCHES = 60
WINDOW = 160


def _path_arg(args: dict[str, Any]) -> str:
    for key in ("path", "file", "file_path", "filename", "files"):
        value = args.get(key)
        if isinstance(value, list):
            value = value[0] if value else ""
        if value:
            return str(value).strip()
    glob = str(args.get("glob") or "").strip()
    return glob if glob.startswith("/") else ""


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def search_rfp(rfp_dir: Path, pattern: str, file: str = "", page_from: int | None = None,
               page_to: int | None = None, output_mode: str = "content") -> str:
    """Case-insensitive literal search of the ingested RFP files, reported with page numbers.
    `a|b` searches for either term (models write alternations even though grep is literal)."""
    terms = [t.strip().lower() for t in str(pattern or "").split("|") if t.strip()] or [""]
    if terms == [""]:
        return "Give a pattern to search for."
    name = PurePosixPath(file).name if file and not file.rstrip("/").endswith("rfp") else ""
    files = sorted(p for p in rfp_dir.glob("*.md") if p.name != "index.md" and (not name or p.name == name))
    if name and not files:
        available = ", ".join(sorted(p.name for p in rfp_dir.glob("*.md") if p.name != "index.md"))
        return f"'{file}' is not an RFP file. Available: {available}"
    if page_to is None:
        page_to = page_from
    hits: list[tuple[str, int, str]] = []
    counts: dict[str, int] = {}
    for path in files:
        page = 0
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = _PAGE_RE.match(line.strip())
            if m:
                page = int(m.group(1))
                continue
            if page_from is not None and not (page_from <= page <= (page_to or page_from)):
                continue
            plain = " ".join(_TAG_RE.sub(" ", line).split())
            low = plain.lower()
            at = min((low.find(t) for t in terms if t in low), default=-1)
            if at < 0:
                continue
            counts[path.name] = counts.get(path.name, 0) + 1
            if len(hits) < MAX_MATCHES:
                start = max(0, at - WINDOW)
                snippet = ("..." if start else "") + plain[start:at + WINDOW] + ("..." if at + WINDOW < len(plain) else "")
                hits.append((path.name, page, snippet))
    scope = f" on pages {page_from}-{page_to}" if page_from is not None else ""
    if not counts:
        return (f"No matches for {pattern!r} in /rfp/{scope} (case-insensitive). Try a shorter word, a synonym or "
                "an abbreviation; tables and diagram text are in the same files.")
    total = sum(counts.values())
    if output_mode == "count":
        return "\n".join(f"/rfp/{n}: {c}" for n, c in counts.items())
    if output_mode == "files_with_matches":
        pages: dict[str, list[int]] = {}
        for n, p, _ in hits:
            pages.setdefault(n, [])
            if p not in pages[n]:
                pages[n].append(p)
        return "\n".join(f"/rfp/{n} ({counts[n]} matching lines; pages {', '.join(map(str, pages.get(n, [])))})"
                         for n in counts)
    lines = [f"/rfp/{n} p.{p}: {s}" for n, p, s in hits]
    if total > len(hits):
        lines.append(f"... {total - len(hits)} more matching lines - narrow the pattern or give page_from/page_to")
    return "\n".join(lines)


class RfpGrepMiddleware(AgentMiddleware):
    """Page-aware RFP grep (see module docstring); also records the RFP pages an agent reads with the
    harness's read_file, so reading coverage counts every way of reading."""

    def __init__(self, rfp_dir: Path, on_read: Callable[[str, list[int]], None] | None = None):
        super().__init__()
        self.rfp_dir = rfp_dir
        self.on_read = on_read

    def _record_read(self, request: Any, result: Any) -> None:
        call = request.tool_call
        if self.on_read is None or call.get("name") != "read_file":
            return
        path = str((call.get("args") or {}).get("file_path") or "")
        if not path.startswith("/rfp/") or path.endswith("index.md"):
            return
        try:
            args = call.get("args") or {}
            offset = int(args.get("offset") or 0)
            limit = int(args.get("limit") or 100)
            lines = (self.rfp_dir / PurePosixPath(path).name).read_text(encoding="utf-8").splitlines()
        except Exception:
            return
        page, pages = 0, []
        for index, line in enumerate(lines[:offset + limit]):
            m = _PAGE_RE.match(line.strip())
            if m:
                page = int(m.group(1))
            if index >= offset and page and page not in pages:
                pages.append(page)
        if pages:
            self.on_read(PurePosixPath(path).name, pages)

    def _handle(self, request: Any) -> tuple[ToolMessage | None, Any]:
        call = request.tool_call
        if call.get("name") != "grep":
            return None, request
        args = dict(call.get("args") or {})
        path = _path_arg(args)
        if not path or path.startswith("/rfp") or path in ("/", "."):
            content = search_rfp(self.rfp_dir, str(args.get("pattern") or args.get("query") or ""),
                                 path if path.startswith("/rfp") else "", _int(args.get("page_from")),
                                 _int(args.get("page_to")), str(args.get("output_mode") or "content"))
            return ToolMessage(content=content, tool_call_id=call.get("id", ""), name="grep"), request
        # Another mount (/skills/, /notes/, /drafts/ ...): the harness's grep, with sane arguments.
        fixed = {"pattern": args.get("pattern", ""), "output_mode": args.get("output_mode") or "content"}
        if path.endswith(".md") or "." in PurePosixPath(path).name:
            fixed["path"], fixed["glob"] = str(PurePosixPath(path).parent) + "/", PurePosixPath(path).name
        else:
            fixed["path"] = path
            if args.get("glob") and "/" not in str(args["glob"]):
                fixed["glob"] = args["glob"]
        return None, request.override(tool_call={**call, "args": fixed})

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        message, request = self._handle(request)
        if message is not None:
            return message
        result = handler(request)
        self._record_read(request, result)
        return result

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        message, request = self._handle(request)
        if message is not None:
            return message
        result = await handler(request)
        self._record_read(request, result)
        return result


# ============================================================================ completion guard
GUARD_MARK = "[section-guard]"


class SectionCompletionMiddleware(AgentMiddleware):
    """A specialist may not stop while one of its ledger sections is still `pending`, nor - when the RFP
    is small enough to read in full - before it has read the RFP. When its model answers without a
    tool call in that state, the agent is sent back to the model with what is missing (up to
    `max_nudges` times per run of the agent), so every section ends `written` or `empty` with a reason
    written by the agent itself."""

    def __init__(self, agent: str, sections: list[str], ledger_state: Callable[[], dict[str, str]],
                 coverage_gap: Callable[[], str], trace: Trace, max_nudges: int = 3):
        super().__init__()
        self.agent = agent
        self.sections = [s for s in sections if s not in ("drafts", "review")]
        self.ledger_state = ledger_state
        self.coverage_gap = coverage_gap
        self.trace = trace
        self.max_nudges = max_nudges

    def _check(self, state: Any) -> dict[str, Any] | None:
        messages = (state or {}).get("messages") or []
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or last.tool_calls or not self.sections:
            return None
        nudges = sum(1 for m in messages if isinstance(m, HumanMessage) and GUARD_MARK in _text(m.content))
        if nudges >= self.max_nudges:
            return None
        states = self.ledger_state()
        pending = [s for s in self.sections if states.get(s) == "pending"]
        gap = self.coverage_gap()
        if not pending and not gap:
            return None
        parts = [GUARD_MARK + " You are not finished."]
        if gap:
            parts.append(f"You {gap}. Call read_next_pages until the whole RFP is read - tables, annexures, "
                         "appendices and diagram text often hold this scope - and write every row you find.")
        if pending:
            parts.append(f"Still pending: {', '.join(pending)}. Write each with its ledger_write_<section> tool: "
                         "the rows you found, or rows=[] (data omitted) with a none_reason naming the pages and "
                         "searches you checked when the RFP truly has nothing.")
        self.trace.emit("completion_guard", self.agent, pending=pending, coverage_gap=gap, nudge=nudges + 1,
                        level="warning")
        return {"messages": [HumanMessage(content=" ".join(parts))], "jump_to": "model"}

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self._check(state)

    @hook_config(can_jump_to=["model"])
    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self._check(state)
