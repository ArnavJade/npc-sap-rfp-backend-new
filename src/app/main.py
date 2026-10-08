"""FastAPI service: `uvicorn app.main:app` (with `src` on the path, e.g. after `pip install -e .`)."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()      # the platform modules read the environment but never load .env themselves

from app.api import bids, platform  # noqa: E402
from app.jobs.runner import JobRunner  # noqa: E402
from app.jobs.store import JobStore  # noqa: E402
from bidcore.paths import workspace_dir  # noqa: E402
from bidcore.policy import get_policy  # noqa: E402
from harness import llm  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = JobStore(workspace_dir() / "jobs")
    interrupted = store.fail_interrupted()
    if interrupted:
        logging.getLogger(__name__).warning("%d job(s) interrupted by the last shutdown marked failed", interrupted)
    limits = get_policy().runtime.limits
    app.state.runner = JobRunner(store, int(os.getenv("MAX_CONCURRENT_JOBS") or limits.get("max_concurrent_jobs", 2)),
                                 int(os.getenv("MAX_QUEUED_JOBS", "4")))
    yield
    await app.state.runner.shutdown()


app = FastAPI(title="SAP RFP agent", version="0.1.0", lifespan=lifespan)
app.include_router(bids.router)
app.include_router(platform.router)


@app.get("/health")
async def health() -> dict:
    policy = get_policy()
    return {"status": "ok", "policy_version": policy.version, "models": llm.models_in_use()}
