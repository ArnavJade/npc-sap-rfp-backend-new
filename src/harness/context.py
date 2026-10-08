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
    _pages: list[tuple[str, int, int]] | None = field(default=None, init=False, repr=False)
    pages_read: dict[str, set[tuple[str, int]]] = field(default_factory=dict, init=False, repr=False)

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
        self._pages = None

    # ------------------------------------------------------------------ RFP reading coverage
    def rfp_pages(self) -> list[tuple[str, int, int]]:
        """Every (file, page, characters) of the ingested RFP, in document order."""
        if self._pages is None:
            from bidcore.ingest.workspace import split_pages

            pages: list[tuple[str, int, int]] = []
            for path in sorted(self.ws.rfp.glob("*.md")):
                if path.name == "index.md":
                    continue
                for number, body in split_pages(path.read_text(encoding="utf-8", errors="replace")):
                    pages.append((path.name, number, len(body)))
            self._pages = pages
        return self._pages

    def mark_read(self, agent: str, file: str, pages: list[int] | range) -> None:
        name = file.replace("\\", "/").rsplit("/", 1)[-1]
        if not name.endswith(".md"):
            name += ".md"
        seen = self.pages_read.setdefault(agent, set())
        for page in pages:
            seen.add((name, int(page)))

    def unread_pages(self, agent: str) -> list[tuple[str, int]]:
        seen = self.pages_read.get(agent, set())
        return [(f, p) for f, p, _ in self.rfp_pages() if (f, p) not in seen]

    def coverage(self, agent: str) -> float:
        total = len(self.rfp_pages())
        return 1.0 if not total else 1.0 - len(self.unread_pages(agent)) / total

    def full_read_expected(self) -> bool:
        """Small enough to read in full (old pipeline scanned every chunk of the RFP)."""
        limit = int(self.policy.runtime.limits.get("full_read_max_chars", 200_000))
        total = sum(chars for _, _, chars in self.rfp_pages())
        return 0 < total <= limit

    def coverage_gap(self, agent: str) -> str:
        """'' when the agent read enough of the RFP to call a section empty / finish; else what is left."""
        if not self.full_read_expected():
            return ""
        need = float(self.policy.runtime.limits.get("min_page_coverage", 0.9))
        if self.coverage(agent) >= need:
            return ""
        return f"read {self.coverage(agent):.0%} of the RFP pages; unread: {page_ranges(self.unread_pages(agent))}"

    def validation(self, ledger: Ledger) -> ValidationContext:
        return ValidationContext(self.policy, self.catalogue, self.corpus(), ledger)

    @property
    def team_config(self) -> dict[str, Any]:
        return self.policy.runtime.teams[self.team]


def page_ranges(pages: list[tuple[str, int]]) -> str:
    """[('a.md', 1), ('a.md', 2), ('a.md', 5)] -> 'a.md p.1-2, 5'."""
    by_file: dict[str, list[int]] = {}
    for f, p in pages:
        by_file.setdefault(f, []).append(p)
    parts = []
    for f, nums in by_file.items():
        nums = sorted(set(nums))
        runs, start, prev = [], nums[0], nums[0]
        for n in nums[1:]:
            if n != prev + 1:
                runs.append(f"{start}-{prev}" if start != prev else str(start))
                start = n
            prev = n
        runs.append(f"{start}-{prev}" if start != prev else str(start))
        parts.append(f"/rfp/{f} p.{', '.join(runs)}")
    return "; ".join(parts) or "none"
