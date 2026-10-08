"""Per-run context shared by every tool and middleware of one job (closures, not globals)."""

from __future__ import annotations

import json
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

ProgressSink = Callable[[dict[str, Any]], None]


class Trace:
    """Append-only run trace (trace/events.jsonl) + an optional live sink for job progress."""

    def __init__(self, ws: BidWorkspace, sink: ProgressSink | None = None):
        self.path = ws.trace / "events.jsonl"
        self.sink = sink
        self._lock = threading.Lock()

    def emit(self, kind: str, agent: str = "", **data: Any) -> None:
        event = {"ts": round(time.time(), 3), "kind": kind, "agent": agent, **data}
        line = json.dumps(event, default=str, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        if self.sink is not None:
            try:
                self.sink(event)
            except Exception:  # progress reporting must never break a run
                pass


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
