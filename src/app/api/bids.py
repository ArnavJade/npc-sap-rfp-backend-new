"""Bid + job routes (used by the Streamlit UI and direct API clients).

POST /bids                      RFP files -> job (call 1)          -> 202 {job_id, bid_id, status_url}
POST /bids/{bid_id}/proposal    reviewed workbook [+ RFP] -> job (call 2)
POST /proposals                 same, bid id read from the workbook's hidden `_bid` sheet
GET  /jobs/{job_id}             job record (status, stage, recent events, result)
GET  /bids, /bids/{id}, /bids/{id}/ledger, /bids/{id}/files/{name}
`?wait=true` on the POSTs blocks until the job ends and returns the job record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app import services
from app.jobs.runner import JobRejected, JobRunner
from app.jobs.store import JobRecord
from bidcore.render.workbook import WorkbookError
from harness import llm
from harness.workspace import BidWorkspace, new_bid_id, safe_name

router = APIRouter()


def runner(request: Request) -> JobRunner:
    return request.app.state.runner


def _open(bid_id: str, create: bool = False) -> BidWorkspace:
    try:
        return BidWorkspace.open(bid_id, create=create)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, f"unknown bid '{bid_id}'") from None


async def _save(ws: BidWorkspace, files: list[UploadFile]) -> list[Path]:
    saved = []
    for f in files:
        data = await f.read()
        if not data:
            raise HTTPException(422, f"'{f.filename}' is empty")
        saved.append(ws.save_upload(safe_name(f.filename or "upload"), data))
    return saved


def job_response(request: Request, record: JobRecord, status_code: int = 202) -> JSONResponse:
    body: dict[str, Any] = {"job_id": record.job_id, "bid_id": record.bid_id, "status": record.status,
                            "status_url": str(request.url_for("get_job", job_id=record.job_id))}
    if record.done:
        body = {**record.model_dump(exclude={"events"}), "status_url": body["status_url"]}
        if record.status == "failed":
            return JSONResponse(body, status_code=record.error_status or 500)
        status_code = 200
    return JSONResponse(body, status_code=status_code)


def _submit(request: Request, kind: str, ws: BidWorkspace, work, params: dict) -> JobRecord:
    try:
        return runner(request).submit(kind, ws.bid_id, work, params)
    except JobRejected as exc:
        raise HTTPException(429, str(exc)) from None


async def _maybe_wait(request: Request, record: JobRecord, wait: bool) -> JSONResponse:
    if wait:
        record = await runner(request).wait(record.job_id)
    return job_response(request, record)


@router.post("/bids", status_code=202)
async def create_bid(request: Request, files: list[UploadFile] = File(..., description="RFP files"),
                     client_name: str = Form("Client"), rate_card_sheet: str = Form(""),
                     model: str = Form(""), wait: bool = Query(False)) -> JSONResponse:
    try:
        services.ensure_models_configured("effort", model or None)
        sheet = services.check_rate_card_sheet(rate_card_sheet)
    except services.ServiceError as exc:
        raise HTTPException(422, str(exc)) from None
    ws = BidWorkspace.open(new_bid_id())
    uploads = await _save(ws, files)
    services.prepare_effort(ws, client_name.strip() or "Client", sheet, llm.models_in_use(model or None))

    async def work(sink):
        return await services.run_effort(ws, client_name.strip() or "Client", uploads, model or None, sink)

    record = _submit(request, "effort", ws, work, {"client_name": client_name, "rate_card_sheet": sheet,
                                                    "files": [p.name for p in uploads], "model": model})
    return await _maybe_wait(request, record, wait)


async def _proposal(request: Request, ws: BidWorkspace, workbook: Path, rfp: list[Path], instructions: str,
                    model: str, wait: bool) -> JSONResponse:
    if not ws.ledger.exists():
        raise HTTPException(409, f"bid {ws.bid_id} has no ledger - run the effort call first")

    async def work(sink):
        return await services.run_proposal(ws, workbook, rfp, instructions, model or None, sink)

    record = _submit(request, "proposal", ws, work, {"workbook": workbook.name, "files": [p.name for p in rfp],
                                                      "instructions": instructions[:2000], "model": model})
    return await _maybe_wait(request, record, wait)


async def _split_proposal_files(ws: BidWorkspace, workbook: UploadFile,
                                rfp_files: list[UploadFile] | None) -> tuple[Path, list[Path]]:
    if not (workbook.filename or "").lower().endswith(services.WORKBOOK_SUFFIXES):
        raise HTTPException(422, "the reviewed workbook must be an .xlsx/.xlsm file")
    book = (await _save(ws, [workbook]))[0]
    return book, await _save(ws, list(rfp_files or []))


@router.post("/bids/{bid_id}/proposal", status_code=202)
async def create_proposal(request: Request, bid_id: str, workbook: UploadFile = File(...),
                          rfp_files: list[UploadFile] | None = File(None), instructions: str = Form(""),
                          model: str = Form(""), wait: bool = Query(False)) -> JSONResponse:
    try:
        services.ensure_models_configured("proposal", model or None)
    except services.ServiceError as exc:
        raise HTTPException(422, str(exc)) from None
    ws = _open(bid_id)
    book, rfp = await _split_proposal_files(ws, workbook, rfp_files)
    try:
        stamped = services.bid_of_workbook(book)
    except WorkbookError as exc:
        raise HTTPException(422, str(exc)) from None
    if stamped != ws.bid_id:
        raise HTTPException(422, f"this workbook belongs to bid {stamped}, not {ws.bid_id}")
    return await _proposal(request, ws, book, rfp, instructions, model, wait)


@router.post("/proposals", status_code=202)
async def create_proposal_from_workbook(request: Request, workbook: UploadFile = File(...),
                                        rfp_files: list[UploadFile] | None = File(None),
                                        instructions: str = Form(""), model: str = Form(""),
                                        wait: bool = Query(False)) -> JSONResponse:
    try:
        services.ensure_models_configured("proposal", model or None)
    except services.ServiceError as exc:
        raise HTTPException(422, str(exc)) from None
    data = await workbook.read()
    scratch = BidWorkspace.open("incoming")
    probe = scratch.save_upload(safe_name(workbook.filename or "workbook.xlsx"), data)
    try:
        bid_id = services.bid_of_workbook(probe)
    except WorkbookError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        probe.unlink(missing_ok=True)
    ws = _open(bid_id)
    await workbook.seek(0)
    book, rfp = await _split_proposal_files(ws, workbook, rfp_files)
    return await _proposal(request, ws, book, rfp, instructions, model, wait)


@router.get("/jobs/{job_id}", name="get_job")
async def get_job(request: Request, job_id: str) -> dict:
    record = runner(request).store.get(job_id)
    if record is None:
        raise HTTPException(404, f"unknown job '{job_id}'")
    return record.model_dump()


@router.get("/bids")
async def list_bids() -> list[dict]:
    root = BidWorkspace.open("incoming").root.parent
    out = []
    for path in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_dir() and path.name != "incoming":
            out.append(services.bid_summary(BidWorkspace.open(path.name, create=False)))
    return out


@router.get("/bids/{bid_id}")
async def get_bid(request: Request, bid_id: str) -> dict:
    ws = _open(bid_id)
    jobs = [r.model_dump(exclude={"events"}) for r in runner(request).store.list(bid_id)]
    return {**services.bid_summary(ws), "jobs": jobs}


@router.get("/bids/{bid_id}/ledger")
async def get_ledger(bid_id: str) -> dict:
    ws = _open(bid_id)
    if not ws.ledger.exists():
        raise HTTPException(404, "no ledger yet")
    return ws.ledger.read_json()


@router.get("/bids/{bid_id}/files/{name}")
async def get_file(bid_id: str, name: str) -> FileResponse:
    ws = _open(bid_id)
    path = ws.outputs / safe_name(name)
    if not path.is_file():
        raise HTTPException(404, f"no output '{name}'")
    return FileResponse(path, filename=path.name)
