"""Job records: one JSON file per job under <workspace>/jobs/ (survives restarts, readable by any pod
sharing the workspace volume). A job that was queued or running when the process stopped is marked
failed at start-up - nothing resumes a half-finished agent run."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "succeeded", "failed"]
MAX_EVENTS = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobRecord(BaseModel):
    job_id: str
    kind: Literal["effort", "proposal"]
    bid_id: str
    status: JobStatus = "queued"
    stage: str = ""
    created_at: str = Field(default_factory=_now)
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    error_status: int = 0
    error_traceback: str = ""              # last frames of the failure (full trace: trace/errors.jsonl)                  # HTTP status a synchronous caller should see on failure
    result: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)

    @property
    def done(self) -> bool:
        return self.status in ("succeeded", "failed")


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def create(self, kind: str, bid_id: str, params: dict[str, Any] | None = None) -> JobRecord:
        record = JobRecord(job_id=uuid.uuid4().hex[:16], kind=kind, bid_id=bid_id, params=params or {})
        self.save(record)
        return record

    def save(self, record: JobRecord) -> None:
        with self._lock:
            tmp = self._path(record.job_id).with_suffix(".tmp")
            tmp.write_text(record.model_dump_json(indent=1), encoding="utf-8")
            os.replace(tmp, self._path(record.job_id))

    def get(self, job_id: str) -> JobRecord | None:
        path = self._path(job_id)
        if not path.is_file():
            return None
        with self._lock:
            return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def update(self, job_id: str, **changes: Any) -> JobRecord:
        with self._lock:
            record = JobRecord.model_validate_json(self._path(job_id).read_text(encoding="utf-8"))
            for key, value in changes.items():
                setattr(record, key, value)
            tmp = self._path(job_id).with_suffix(".tmp")
            tmp.write_text(record.model_dump_json(indent=1), encoding="utf-8")
            os.replace(tmp, self._path(job_id))
            return record

    def add_event(self, job_id: str, event: dict[str, Any]) -> None:
        """Progress from the run trace: the latest stage plus a bounded tail of agent/tool events."""
        with self._lock:
            path = self._path(job_id)
            record = JobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            if event.get("kind") == "stage":
                record.stage = str(event.get("stage", ""))
            record.events = [*record.events, json.loads(json.dumps(event, default=str))][-MAX_EVENTS:]
            tmp = path.with_suffix(".tmp")
            tmp.write_text(record.model_dump_json(indent=1), encoding="utf-8")
            os.replace(tmp, path)

    def list(self, bid_id: str | None = None) -> list[JobRecord]:
        records = []
        for path in sorted(self.root.glob("*.json")):
            try:
                record = JobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if bid_id is None or record.bid_id == bid_id:
                records.append(record)
        return sorted(records, key=lambda r: r.created_at)

    def fail_interrupted(self) -> int:
        count = 0
        for record in self.list():
            if not record.done:
                self.update(record.job_id, status="failed", finished_at=_now(),
                            error="the service restarted while this job was running; submit it again")
                count += 1
        return count
