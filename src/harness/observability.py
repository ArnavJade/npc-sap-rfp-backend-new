"""Logging and run observability.

Three layers, one source of truth per run:

1. Python logging (`configure_logging`): console + rotating `<LOG_DIR>/app.log`, text or JSON lines,
   every record stamped with the bid / agent / stage it happened in (context variables, so parallel
   bids and subagents never mix up their lines). Each bid run also gets its own `trace/run.log`
   (`run_log`), holding only that bid's records.
2. The run trace (`harness.context.Trace`): structured events in `trace/events.jsonl` - stages with
   durations, agent starts/ends with their final output, every model call (latency, tokens, output
   preview, tool calls requested), every tool call (args, result preview), ledger writes with their
   rejections - plus `trace/llm_calls.jsonl` (full model-call records) and `trace/errors.jsonl`
   (every failure with its traceback). Each event is also logged through (1).
3. Analysis (`load_events`, `summarize`): per-agent model calls / tokens / latency / tool errors /
   ledger rejections, stage timings and the failure list - used by `scripts/trace_view.py` and the
   API's `/bids/{id}/trace` routes.

Settings (env): LOG_LEVEL (INFO), LOG_FORMAT (text|json), LOG_DIR (<workspace>/logs),
TRACE_PREVIEW_CHARS (1500: size of output / argument previews in events), TRACE_LLM_CONTENT
(on: write prompts' last message and full responses to llm_calls.jsonl; off: metadata only).
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import logging.handlers
import os
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

BID: contextvars.ContextVar[str] = contextvars.ContextVar("bid", default="-")
AGENT: contextvars.ContextVar[str] = contextvars.ContextVar("agent", default="-")
STAGE: contextvars.ContextVar[str] = contextvars.ContextVar("stage", default="-")

NOISY_LOGGERS = ("httpx", "httpcore", "LiteLLM", "litellm", "openai", "urllib3", "matplotlib", "PIL",
                 "langchain", "langgraph", "multipart", "pymupdf", "fontTools")
_configured = False


def preview_chars() -> int:
    try:
        return max(200, int(os.getenv("TRACE_PREVIEW_CHARS", "1500")))
    except ValueError:
        return 1500


def llm_content_enabled() -> bool:
    return os.getenv("TRACE_LLM_CONTENT", "on").strip().lower() not in ("off", "0", "false", "no")


def preview(value: Any, limit: int | None = None) -> str:
    """Single-line, size-bounded text of any value (for events and log lines)."""
    limit = limit or preview_chars()
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            value = str(value)
    text = " ".join(value.split())
    return text if len(text) <= limit else text[:limit] + f"... [+{len(text) - limit} chars]"


def error_info(exc: BaseException) -> dict[str, Any]:
    """Type, message and the last frames of the traceback - enough to locate the failure point."""
    frames = traceback.format_exception(type(exc), exc, exc.__traceback__)
    return {"error_type": type(exc).__name__, "error": str(exc)[:4000],
            "traceback": "".join(frames)[-6000:]}


@contextlib.contextmanager
def bind(bid: str | None = None, agent: str | None = None, stage: str | None = None) -> Iterator[None]:
    """Set the logging context for the enclosed code (and the asyncio tasks it starts)."""
    tokens = []
    for var, value in ((BID, bid), (AGENT, agent), (STAGE, stage)):
        if value is not None:
            tokens.append((var, var.set(value)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.bid, record.agent, record.stage = BID.get(), AGENT.get(), STAGE.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
                   "logger": record.name, "bid": getattr(record, "bid", "-"), "agent": getattr(record, "agent", "-"),
                   "stage": getattr(record, "stage", "-"), "msg": record.getMessage()}
        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


TEXT_FORMAT = "%(asctime)s %(levelname)-7s [%(bid)s|%(stage)s|%(agent)s] %(name)s: %(message)s"


def _formatter(fmt: str) -> logging.Formatter:
    return JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT, "%H:%M:%S")


def configure_logging(level: str | None = None, fmt: str | None = None, log_dir: Path | None = None,
                      force: bool = False) -> None:
    """Console + rotating file logging with bid/agent/stage context. Idempotent unless `force`."""
    global _configured
    if _configured and not force:
        return
    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    fmt = (fmt or os.getenv("LOG_FORMAT", "text")).strip().lower()
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_sap_rfp", False):
            root.removeHandler(handler)
    console = logging.StreamHandler(sys.stderr)
    handlers: list[logging.Handler] = [console]
    if log_dir is None:
        from bidcore.paths import workspace_dir
        log_dir = Path(os.getenv("LOG_DIR") or workspace_dir() / "logs")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(log_dir / "app.log", maxBytes=20_000_000,
                                                             backupCount=5, encoding="utf-8"))
    except OSError:
        pass                                   # read-only filesystem: console only
    for handler in handlers:
        handler.setFormatter(_formatter(fmt))
        handler.addFilter(ContextFilter())
        handler._sap_rfp = True                # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level_name)
    quiet = logging.DEBUG if level_name == "DEBUG" else logging.WARNING
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(quiet)
    _configured = True


class _BidFilter(logging.Filter):
    def __init__(self, bid: str):
        super().__init__()
        self.bid = bid

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "bid", BID.get()) == self.bid


@contextlib.contextmanager
def run_log(bid: str, trace_dir: Path) -> Iterator[Path]:
    """While active: this bid's log records also go to <trace_dir>/run.log (DEBUG and up)."""
    configure_logging()
    trace_dir.mkdir(parents=True, exist_ok=True)
    path = trace_dir / "run.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_formatter(os.getenv("LOG_FORMAT", "text").strip().lower()))
    handler.addFilter(ContextFilter())
    handler.addFilter(_BidFilter(bid))
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        with bind(bid=bid):
            yield path
    finally:
        root.removeHandler(handler)
        handler.close()


# --------------------------------------------------------------------------- analysis

ERROR_KINDS = ("model_error", "tool_error", "stage_error", "run_error", "ledger_rejected")


def load_events(trace_dir: Path, kinds: set[str] | None = None, agent: str | None = None,
                errors_only: bool = False, since: float | None = None) -> list[dict[str, Any]]:
    path = trace_dir / "events.jsonl"
    if not path.is_file():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if kinds and event.get("kind") not in kinds:
                continue
            if agent and event.get("agent") != agent:
                continue
            if errors_only and not is_error(event):
                continue
            if since is not None and event.get("ts", 0) <= since:
                continue
            out.append(event)
    return out


def is_error(event: dict[str, Any]) -> bool:
    if event.get("kind") == "ledger_write":         # its failures are reported as ledger_rejected
        return False
    return event.get("kind") in ERROR_KINDS or event.get("ok") is False or event.get("level") in ("error", "warning")


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-agent and per-stage roll-up of a run's events, plus every failure point."""
    agents: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "runs": 0, "model_calls": 0, "model_ms": 0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0,
        "tool_errors": 0, "model_errors": 0, "ledger_writes": 0, "ledger_rejections": 0, "tools": Counter()})
    stages: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for e in events:
        kind = e.get("kind")
        a = agents[e.get("agent") or "-"]
        if kind == "agent_start":
            a["runs"] += 1
        elif kind == "model_call":
            a["model_calls"] += 1
            a["model_ms"] += e.get("ms", 0) or 0
            a["input_tokens"] += e.get("input_tokens", 0) or 0
            a["output_tokens"] += e.get("output_tokens", 0) or 0
        elif kind in ("tool", "tool_error"):
            a["tool_calls"] += 1
            a["tools"][e.get("tool", "?")] += 1
            if kind == "tool_error" or e.get("ok") is False:
                a["tool_errors"] += 1
        elif kind == "model_error":
            a["model_errors"] += 1
        elif kind == "ledger_write":
            a["ledger_writes"] += 1
            a["ledger_rejections"] += e.get("rejected", 0) or (0 if e.get("ok", True) else 1)
        elif kind in ("stage_end", "stage_error"):
            stages.append({"stage": e.get("stage"), "ms": e.get("ms"), "ok": kind == "stage_end"})
        if is_error(e):
            errors.append({k: e.get(k) for k in ("ts", "kind", "agent", "stage", "tool", "section", "error_type",
                                                 "error", "result") if e.get(k) not in (None, "")})
    for stats in agents.values():
        stats["tools"] = dict(stats["tools"].most_common())
    workflow = agents.get("-")
    if workflow is not None and not (workflow["model_calls"] or workflow["tool_calls"]):
        del agents["-"]                        # workflow-level events only: not an agent
    return {"events": len(events), "agents": dict(agents), "stages": stages, "errors": errors,
            "totals": {k: sum(s[k] for s in agents.values()) for k in
                       ("model_calls", "input_tokens", "output_tokens", "tool_calls", "tool_errors",
                        "model_errors", "ledger_rejections")}}


def format_event(e: dict[str, Any]) -> str:
    """One human-readable line per event (CLI tail / UI)."""
    kind, agent = e.get("kind", "?"), e.get("agent") or ""
    mark = "!!" if is_error(e) else "  "
    if kind == "model_call":
        calls = ", ".join(c.get("name", "?") for c in e.get("tool_calls", []))
        body = (f"{e.get('model', '')} {e.get('ms', 0)}ms in={e.get('input_tokens', '?')} out={e.get('output_tokens', '?')}"
                + (f" -> tools[{calls}]" if calls else "") + (f" | {e['output']}" if e.get("output") else ""))
    elif kind in ("tool", "tool_error"):
        body = f"{e.get('tool')} ({e.get('ms', 0)}ms) args={e.get('args', '')} -> {e.get('result', '')}"
    elif kind == "stage":
        body = f"{e.get('stage')} started"
    elif kind.startswith("stage"):
        body = f"{e.get('stage')} {e.get('ms', '')}ms {e.get('error_type', '')} {e.get('error', '')}".strip()
    elif kind in ("model_error", "run_error"):
        body = f"{e.get('error_type')}: {e.get('error')}"
    else:
        body = preview({k: v for k, v in e.items() if k not in ("ts", "kind", "agent", "seq", "bid")}, 400)
    return f"{mark} {kind:<14} {agent:<22} {body}"
