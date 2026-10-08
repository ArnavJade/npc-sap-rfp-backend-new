"""In-process job runner: asyncio tasks behind a concurrency semaphore, progress from the run trace.

A job is a coroutine factory `work(sink) -> result dict`. The runner records queued -> running ->
succeeded/failed, feeds every trace event into the job record (stage + recent events), and refuses new
work with JobRejected when the pod already holds `max_active` jobs (the API maps it to 429).
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Awaitable, Callable

from app.jobs.store import JobRecord, JobStore, _now

log = logging.getLogger(__name__)

Work = Callable[[Callable[[dict[str, Any]], None]], Awaitable[dict[str, Any]]]


class JobRejected(RuntimeError):
    """Too many jobs on this pod."""


class JobFailed(RuntimeError):
    """Raised by work to fail a job with a specific HTTP status for synchronous callers."""

    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


class JobRunner:
    def __init__(self, store: JobStore, max_concurrent: int = 2, max_queued: int = 4):
        self.store = store
        self.semaphore = asyncio.Semaphore(max(1, max_concurrent))
        self.max_active = max(1, max_concurrent) + max(0, max_queued)
        self.tasks: dict[str, asyncio.Task] = {}

    @property
    def active(self) -> int:
        return sum(1 for t in self.tasks.values() if not t.done())

    def submit(self, kind: str, bid_id: str, work: Work, params: dict[str, Any] | None = None) -> JobRecord:
        if self.active >= self.max_active:
            raise JobRejected(f"{self.active} jobs already queued or running on this server; retry later")
        record = self.store.create(kind, bid_id, params)
        self.tasks[record.job_id] = asyncio.create_task(self._run(record.job_id, work), name=f"job-{record.job_id}")
        return record

    async def _run(self, job_id: str, work: Work) -> None:
        async with self.semaphore:
            self.store.update(job_id, status="running", started_at=_now())

            def sink(event: dict[str, Any]) -> None:
                try:
                    self.store.add_event(job_id, event)
                except Exception:      # progress must never break a run
                    log.debug("progress event dropped", exc_info=True)

            try:
                result = await work(sink)
            except JobFailed as exc:
                self.store.update(job_id, status="failed", finished_at=_now(), error=str(exc), error_status=exc.status)
                return
            except Exception as exc:
                log.error("job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
                self.store.update(job_id, status="failed", finished_at=_now(),
                                  error=f"{type(exc).__name__}: {exc}"[:2000], error_status=500)
                return
            self.store.update(job_id, status="succeeded", finished_at=_now(), result=result, stage="done")

    async def wait(self, job_id: str, timeout: float | None = None) -> JobRecord:
        task = self.tasks.get(job_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout)
        record = self.store.get(job_id)
        assert record is not None
        return record

    async def shutdown(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
