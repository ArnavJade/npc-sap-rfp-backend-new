"""One directory per bid; the agents' virtual filesystem is mounted from parts of it.

workspace/<bid_id>/
  uploads/          files exactly as received (call 1: RFP; call 2: reviewed workbook [+ RFP])
  rfp/              ingested, page-marked Markdown + index.md        -> agents: /rfp/ (read-only)
  skills/<agent>/   pinned skill bundle for this run, one folder per agent -> agents: /skills/ (read-only)
  notes/            agent scratch space                                -> agents: /notes/
  drafts/           proposal section drafts (written via write_draft)  -> agents: /drafts/ (read-only)
  review/           reviewer findings
  ledger/           ledger.json + versions/
  outputs/          generated .xlsx / .docx
  trace/            events.jsonl (every agent step and tool call)
  cache/            image-caption cache
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from bidcore.ledger.store import LedgerStore
from bidcore.paths import workspace_dir

_SUBDIRS = ("uploads", "rfp", "skills", "notes", "drafts", "review", "ledger", "outputs", "trace", "cache")


def new_bid_id() -> str:
    return uuid.uuid4().hex[:12]


def safe_name(name: str, default: str = "file") -> str:
    base = re.sub(r"[^\w.\- ]+", "_", Path(str(name).replace("\\", "/")).name, flags=re.UNICODE).strip(" .")
    return base or default


def clean_bid_id(bid_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", bid_id or "")[:64]
    if not cleaned:
        raise ValueError("invalid bid id")
    return cleaned


@dataclass(frozen=True)
class BidWorkspace:
    bid_id: str
    root: Path

    @classmethod
    def open(cls, bid_id: str, base: Path | None = None, create: bool = True) -> "BidWorkspace":
        bid_id = clean_bid_id(bid_id)
        root = (base or workspace_dir()) / "bids" / bid_id
        if create:
            for sub in _SUBDIRS:
                (root / sub).mkdir(parents=True, exist_ok=True)
        elif not root.is_dir():
            raise FileNotFoundError(f"unknown bid '{bid_id}'")
        return cls(bid_id, root)

    def __getattr__(self, item: str) -> Path:   # ws.rfp, ws.outputs, ...
        if item in _SUBDIRS:
            return self.root / item
        raise AttributeError(item)

    @property
    def ledger(self) -> LedgerStore:
        return LedgerStore(self.root / "ledger")

    def save_upload(self, name: str, data: bytes) -> Path:
        path = self.root / "uploads" / safe_name(name, "upload")
        path.write_bytes(data)
        return path

    def output_files(self) -> list[Path]:
        return sorted((p for p in (self.root / "outputs").glob("*") if p.is_file()), key=lambda p: p.stat().st_mtime)

    def latest_output(self, suffix: str) -> Path | None:
        files = [p for p in self.output_files() if p.suffix.lower() == suffix]
        return files[-1] if files else None
