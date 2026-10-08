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
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from harness.context import Trace

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
    def __init__(self, agent: str, trace: Trace, retries: int = 2):
        super().__init__()
        self.agent = agent
        self.trace = trace
        self.retries = retries

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

    def _nudged(self, request: Any) -> Any:
        return request.override(messages=[*request.messages, HumanMessage(content=EMPTY_NUDGE)])

    def _fallback(self, response: Any) -> Any:
        ai = self._ai(response)
        if ai is None:
            return response
        return self._replace_ai(response, ai.model_copy(update={"content": EMPTY_FALLBACK.format(n=self.retries + 1)}))

    # ------------------------------------------------------------------ hooks
    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        response = handler(request)
        attempt = 0
        while self._is_empty(response) and attempt < self.retries:
            attempt += 1
            self.trace.emit("model_retry", self.agent, attempt=attempt, reason="empty reply", level="warning")
            response = handler(self._nudged(request))
        if self._is_empty(response):
            return self._fallback(response)
        return self._repair(request, response)

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        response = await handler(request)
        attempt = 0
        while self._is_empty(response) and attempt < self.retries:
            attempt += 1
            self.trace.emit("model_retry", self.agent, attempt=attempt, reason="empty reply", level="warning")
            response = await handler(self._nudged(request))
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
    def __init__(self, rfp_dir: Path):
        super().__init__()
        self.rfp_dir = rfp_dir

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
        return message if message is not None else handler(request)

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        message, request = self._handle(request)
        return message if message is not None else await handler(request)
