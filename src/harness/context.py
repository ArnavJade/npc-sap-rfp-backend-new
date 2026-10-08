"""Per-run context shared by every tool and middleware of one job (closures, not globals)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from bidcore.catalogue.store import Catalogue, get_catalogue
from bidcore.evidence import CorpusIndex
from bidcore.ledger.models import Ledger
from bidcore.ledger.store import LedgerStore
from bidcore.ledger.validate import ValidationContext
from bidcore.policy import Policy, get_policy
from harness.workspace import BidWorkspace

_log = logging.getLogger("trace")

ProgressSink = Callable[[dict[str, Any]], None]


class Trace:
    """Append-only run trace + an optional live sink for job progress (see harness.observability).

    trace/events.jsonl     every event (seq, ts, kind, agent, bid, stage, ...)
    trace/errors.jsonl     the failure events only, with tracebacks
    trace/llm_calls.jsonl  one full record per model call (prompt tail + response when enabled)
    Each event is also logged (logger 'trace'), so it reaches the console, app.log and run.log."""

    def __init__(self, ws: BidWorkspace, sink: ProgressSink | None = None):
        self.dir = ws.trace
        self.path = ws.trace / "events.jsonl"
        self.bid = ws.bid_id
        self.sink = sink
        self._lock = threading.Lock()
        self._seq = 0

    def _append(self, name: str, record: dict[str, Any]) -> None:
        line = json.dumps(record, default=str, ensure_ascii=False)
        with (self.dir / name).open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def emit(self, kind: str, agent: str = "", **data: Any) -> dict[str, Any]:
        from harness.observability import STAGE, format_event, is_error

        with self._lock:
            self._seq += 1
            event = {"seq": self._seq, "ts": round(time.time(), 3), "kind": kind, "agent": agent,
                     "bid": self.bid, "stage": data.pop("stage_ctx", None) or STAGE.get(), **data}
            if kind.startswith("stage"):
                event["stage"] = data.get("stage", event["stage"])
            self._append("events.jsonl", event)
            if is_error(event):
                self._append("errors.jsonl", event)
        level = logging.ERROR if kind in ("model_error", "tool_error", "stage_error", "run_error") else (
            logging.WARNING if is_error(event) else logging.INFO)
        if kind in ("model_call", "tool") and level == logging.INFO:
            level = logging.DEBUG if os.getenv("TRACE_LOG_CALLS", "on").lower() in ("off", "0") else logging.INFO
        _log.log(level, format_event({k: v for k, v in event.items() if k != "traceback"}))
        if event.get("traceback") and level >= logging.ERROR:
            _log.debug("traceback:\n%s", event["traceback"])
        if self.sink is not None:
            try:
                self.sink(event)
            except Exception:  # progress reporting must never break a run
                pass
        return event

    def llm_record(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._append("llm_calls.jsonl", {"ts": round(time.time(), 3), "bid": self.bid, **record})


@dataclass
class RunContext:
    ws: BidWorkspace
    team: str                                   # effort | proposal
    run_model: str | None = None                # model chosen for this job (overrides policy/env)
    policy: Policy = field(default_factory=get_policy)
    catalogue: Catalogue = field(default_factory=get_catalogue)
    sink: ProgressSink | None = None
    _corpus: CorpusIndex | None = field(default=None, init=False, repr=False)
    _trace: Trace | None = field(default=None, init=False, repr=False)

    @property
    def ledger(self) -> LedgerStore:
        return self.ws.ledger

    @property
    def trace(self) -> Trace:
        if self._trace is None:
            self._trace = Trace(self.ws, self.sink)
        return self._trace

    def corpus(self) -> CorpusIndex | None:
        """The RFP text for evidence checks; None when no RFP was ingested (checks then pass)."""
        if self._corpus is None and any(p.name != "index.md" for p in self.ws.rfp.glob("*.md")):
            self._corpus = CorpusIndex.from_dir(self.ws.rfp)
        return self._corpus

    def reset_corpus(self) -> None:
        self._corpus = None

    def validation(self, ledger: Ledger) -> ValidationContext:
        return ValidationContext(self.policy, self.catalogue, self.corpus(), ledger)

    @property
    def team_config(self) -> dict[str, Any]:
        return self.policy.runtime.teams[self.team]
