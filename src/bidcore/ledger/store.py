"""Ledger persistence: workspace/<bid_id>/ledger/ledger.json (+ versioned snapshots).

Parallel subagents write through the same store, so every read-modify-write runs under one
lock per ledger file and the JSON is replaced atomically.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Callable, TypeVar

from bidcore.ledger.base import AuditEvent
from bidcore.ledger.models import Ledger

R = TypeVar("R")
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


class LedgerStore:
    def __init__(self, ledger_dir: Path):
        self.dir = ledger_dir
        self.path = ledger_dir / "ledger.json"
        self.versions = ledger_dir / "versions"
        self._lock = _lock_for(self.path)

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> Ledger:
        with self._lock:
            return Ledger.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, ledger: Ledger) -> Ledger:
        with self._lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            ledger.meta.version += 1
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(ledger.model_dump_json(indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
            return ledger

    def update(self, fn: Callable[[Ledger], R], actor: str, action: str, section: str = "",
               detail: str = "") -> R:
        """Load, apply `fn`, append an audit event and save - atomically with respect to other writers."""
        with self._lock:
            ledger = self.load()
            result = fn(ledger)
            ledger.audit.append(AuditEvent(actor=actor, action=action, section=section, detail=detail[:500]))
            self.save(ledger)
            return result

    def checkpoint(self, label: str) -> Path:
        """Snapshot the current ledger as versions/v<N>-<label>.json (milestones only)."""
        with self._lock:
            ledger = self.load()
            self.versions.mkdir(parents=True, exist_ok=True)
            out = self.versions / f"v{ledger.meta.version:03d}-{label}.json"
            out.write_text(ledger.model_dump_json(indent=1), encoding="utf-8")
            return out

    def read_json(self) -> dict:
        with self._lock:
            return json.loads(self.path.read_text(encoding="utf-8"))
