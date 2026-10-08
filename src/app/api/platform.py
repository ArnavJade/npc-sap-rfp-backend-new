"""The two platform routes, contract-compatible with the old service.

POST /pipeline/match/effort          user_metadata (+ client_name, effort_sheet, ...) -> effort workbook
POST /pipeline/generate/from-excel   user_metadata (+ instructions)                    -> YASH .docx

Input files come from SharePoint (`attachment_sharepoint_map` in user_metadata); the output is uploaded
to the user_metadata folder and an Activity event is sent. Attachments are downloaded and checked
before the job is queued, so bad input fails with a proper status: 400 invalid user_metadata, 422 no
attachments / a workbook not in the effort-template layout / no model, 502 SharePoint errors. Default response:
202 {job_id, status_url}; `?wait=true` returns the old body {"status": "success", "sharepoint": {...}}.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app import services
from app.api.bids import _submit, job_response, runner
from app.jobs.runner import JobFailed
from app.platform import (
    PlatformHeaders, RequestContext, SharePointError, UserMetadataError, download_attachment_from_sharepoint,
    report_effort_excel_generated, report_proposal_generated, upload_output_to_sharepoint,
)
from harness import llm
from harness.workspace import BidWorkspace, new_bid_id, safe_name

log = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline")


def _context(request: Request, user_metadata: str, **route_inputs: Any) -> RequestContext:
    try:
        return RequestContext.from_user_metadata_string(
            user_metadata, platform_headers=PlatformHeaders.from_request_headers(request.headers),
            authorization=request.headers.get("authorization"), **route_inputs)
    except (UserMetadataError, ValueError) as exc:
        raise HTTPException(400, f"invalid user_metadata: {exc}") from None


async def _download(ctx: RequestContext, ws: BidWorkspace) -> list[Path]:
    attachments = ctx.get_sharepoint_attachments()
    if not attachments:
        raise HTTPException(422, "user_metadata has no attachment_sharepoint_map entries - nothing to process")
    paths = []
    for key, ref in attachments.items():
        drive, item = ref.get("sp_drive_id", ""), ref.get("sp_item_id", "")
        if not drive or not item:
            raise HTTPException(422, f"attachment '{key}' lacks sp_drive_id/sp_item_id")
        try:
            name, data = await download_attachment_from_sharepoint(drive, item)
        except SharePointError as exc:
            raise HTTPException(502, f"SharePoint download failed for '{key}': {exc}") from None
        paths.append(ws.save_upload(safe_name(name or key), data))
    return paths


async def _upload(ctx: RequestContext, path: Path) -> dict[str, Any]:
    drive, folder = ctx.get_sharepoint_upload_target()
    if not drive or not folder:
        return {"filename": path.name, "uploaded": False, "reason": "no sp_drive_id/sp_folder_id in user_metadata"}
    try:
        return await upload_output_to_sharepoint(path, drive, folder, path.name)
    except SharePointError as exc:
        raise JobFailed(f"SharePoint upload failed: {exc}", 502) from None


def _old_body(request: Request, record) -> JSONResponse:
    if record.done and record.status == "succeeded":
        return JSONResponse({"status": "success", "sharepoint": record.result.get("sharepoint"),
                             "job_id": record.job_id, "bid_id": record.bid_id})
    return job_response(request, record)


@router.post("/match/effort", status_code=202)
async def match_effort(request: Request, user_metadata: str = Form(...), client_name: str = Form(""),
                       effort_sheet: str = Form(""), go_live_date: str = Form(""), instructions: str = Form(""),
                       model: str = Form(""), wait: bool = Query(False)) -> JSONResponse:
    ctx = _context(request, user_metadata, client_name=client_name or None, effort_sheet=effort_sheet or None,
                   go_live_date=go_live_date or None, instructions=instructions or None)
    try:
        services.ensure_models_configured("effort", model or None)
        sheet = services.check_rate_card_sheet(effort_sheet)
    except services.ServiceError as exc:
        raise HTTPException(422, str(exc)) from None
    client = (client_name or ctx.user_metadata.company_name or "Client").strip()
    ws = BidWorkspace.open(new_bid_id())
    uploads = await _download(ctx, ws)
    services.prepare_effort(ws, client, sheet, llm.models_in_use(model or None))

    async def work(sink):
        result = await services.run_effort(ws, client, uploads, model or None, sink)
        sp_ref = await _upload(ctx, ws.outputs / result["workbook"])
        await report_effort_excel_generated(ctx, sp_ref, {"bid_id": ws.bid_id})
        return {**result, "sharepoint": sp_ref}

    record = _submit(request, "effort", ws, work, {"client_name": client, "rate_card_sheet": sheet,
                                                    "files": [p.name for p in uploads], "platform": True})
    if wait:
        record = await runner(request).wait(record.job_id)
    return _old_body(request, record)


@router.post("/generate/from-excel", status_code=202)
async def generate_from_excel(request: Request, user_metadata: str = Form(...), instructions: str = Form(""),
                              model: str = Form(""), wait: bool = Query(False)) -> JSONResponse:
    ctx = _context(request, user_metadata, instructions=instructions or None)
    try:
        services.ensure_models_configured("proposal", model or None)
    except services.ServiceError as exc:
        raise HTTPException(422, str(exc)) from None
    staging = BidWorkspace.open("incoming")
    downloaded = await _download(ctx, staging)
    books = [p for p in downloaded if p.suffix.lower() in services.WORKBOOK_SUFFIXES]
    if len(books) != 1:
        raise HTTPException(422, f"expected exactly one reviewed .xlsx/.xlsm attachment, got {len(books)}")
    try:
        services.check_effort_workbook(books[0])
    except services.ServiceError as exc:
        raise HTTPException(422, str(exc)) from None
    ws = services.proposal_workspace(books[0])   # linked call-1 bid, else built from the workbook alone
    moved = []
    for path in downloaded:
        target = ws.uploads / path.name
        path.replace(target)
        moved.append(target)
    book = ws.uploads / books[0].name
    rfp = [p for p in moved if p != book]

    async def work(sink):
        result = await services.run_proposal(ws, book, rfp, instructions, model or None, sink)
        sp_ref = await _upload(ctx, ws.outputs / result["document"])
        await report_proposal_generated(ctx, sp_ref, {"bid_id": ws.bid_id})
        return {**result, "sharepoint": sp_ref}

    record = _submit(request, "proposal", ws, work, {"workbook": book.name, "files": [p.name for p in rfp],
                                                      "platform": True})
    if wait:
        record = await runner(request).wait(record.job_id)
    return _old_body(request, record)
