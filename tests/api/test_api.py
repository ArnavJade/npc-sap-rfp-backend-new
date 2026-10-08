"""HTTP API: both calls through the job runner with scripted models; platform routes with SharePoint
and Activity mocked; fail-fast and error mapping."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from bidcore.paths import PROJECT_ROOT
from harness import llm
from tests.harness.fakes import factory, stub_skills
from tests.harness.test_effort_e2e import RFP, effort_scripts
from tests.harness.test_proposal_e2e import proposal_scripts


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLS_DIR", str(stub_skills(tmp_path / "skills", PROJECT_ROOT / "skills")))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "ws"))
    scripts = {**effort_scripts(), **proposal_scripts()}
    llm.set_model_factory(factory(scripts))
    from app.main import app

    with TestClient(app) as c:
        yield c
    llm.set_model_factory(None)


def test_effort_then_proposal_over_http(client):
    r = client.post("/bids?wait=true", files=[("files", ("ACME RFP.txt", RFP.encode(), "text/plain"))],
                    data={"client_name": "ACME Foods"})
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["status"] == "succeeded" and job["result"]["workbook"].endswith(".xlsx")
    bid = job["bid_id"]
    status = client.get(f"/jobs/{job['job_id']}").json()
    assert status["stage"] == "done" and any(e["kind"] == "tool" for e in status["events"])
    summary = client.get(f"/bids/{bid}").json()
    assert summary["sections"]["integrations"]["rows"] == 1 and summary["jobs"]
    assert client.get(f"/bids/{bid}/ledger").json()["meta"]["bid_id"] == bid
    book = client.get(f"/bids/{bid}/files/{job['result']['workbook']}")
    assert book.status_code == 200 and book.content[:2] == b"PK"
    assert any(b["bid_id"] == bid for b in client.get("/bids").json())

    r = client.post("/proposals?wait=true", files=[("workbook", ("reviewed.xlsx", book.content, "application/octet-stream"))],
                    data={"instructions": "Keep it short."})
    assert r.status_code == 200, r.text
    doc = r.json()["result"]["document"]
    assert doc.endswith(".docx") and client.get(f"/bids/{bid}/files/{doc}").status_code == 200


def test_async_job_and_polling(client):
    r = client.post("/bids", files=[("files", ("rfp.txt", RFP.encode(), "text/plain"))])
    assert r.status_code == 202 and r.json()["status_url"].endswith(r.json()["job_id"])
    record = client.app.state.runner.store.get(r.json()["job_id"])
    assert record is not None and record.kind == "effort"


def test_rejections(client, monkeypatch):
    r = client.post("/bids", files=[("files", ("rfp.txt", RFP.encode(), "text/plain"))],
                    data={"rate_card_sheet": "Nope"})
    assert r.status_code == 422 and "rate card" in r.text
    from openpyxl import Workbook
    import io
    buf = io.BytesIO()
    Workbook().save(buf)
    r = client.post("/proposals", files=[("workbook", ("old.xlsx", buf.getvalue(), "application/octet-stream"))])
    assert r.status_code == 422 and "_bid" in r.text
    assert client.get("/jobs/nope").status_code == 404
    assert client.get("/bids/nope").status_code == 404
    llm.set_model_factory(None)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    r = client.post("/bids", files=[("files", ("rfp.txt", RFP.encode(), "text/plain"))])
    assert r.status_code == 422 and "LLM_MODEL" in r.text


def test_platform_routes(client, monkeypatch):
    from app.api import platform as routes

    uploaded, activity = [], []

    async def download(drive, item):
        return ("ACME RFP.txt", RFP.encode()) if item == "rfp" else ("reviewed.xlsx", state["book"])

    async def upload(path, drive, folder, name):
        uploaded.append(name)
        return {"sp_file_id": f"id-{len(uploaded)}", "sp_file_web_url": "https://sp/x", "sp_drive_id": drive,
                "sp_folder_id": folder, "filename": name, "size": 1}

    async def report(ctx, sp_ref, extra):
        activity.append((sp_ref["filename"], extra))
        return True

    state = {}
    monkeypatch.setattr(routes, "download_attachment_from_sharepoint", download)
    monkeypatch.setattr(routes, "upload_output_to_sharepoint", upload)
    monkeypatch.setattr(routes, "report_effort_excel_generated", report)
    monkeypatch.setattr(routes, "report_proposal_generated", report)
    meta = {"team_id": "t1", "company_name": "ACME Foods", "sp_drive_id": "d", "sp_folder_id": "f",
            "attachment_sharepoint_map": {"a1": {"sp_item_id": "rfp", "sp_drive_id": "d"}}}
    r = client.post("/pipeline/match/effort?wait=true", data={"user_metadata": json.dumps(meta)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success" and body["sharepoint"]["filename"].startswith("Claude_BP_Effort_Output_ACME")
    state["book"] = client.get(f"/bids/{body['bid_id']}/files/{body['sharepoint']['filename']}").content

    meta["attachment_sharepoint_map"] = {"a1": {"sp_item_id": "book", "sp_drive_id": "d"},
                                         "a2": {"sp_item_id": "rfp", "sp_drive_id": "d"}}
    r = client.post("/pipeline/generate/from-excel?wait=true", data={"user_metadata": json.dumps(meta)})
    assert r.status_code == 200, r.text
    assert r.json()["sharepoint"]["filename"].startswith("YASH_SAP_RFP_Response_ACME")
    assert [a[1]["bid_id"] for a in activity] == [body["bid_id"]] * 2

    assert client.post("/pipeline/match/effort", data={"user_metadata": "{not json"}).status_code == 400
    meta.pop("attachment_sharepoint_map")
    assert client.post("/pipeline/match/effort", data={"user_metadata": json.dumps(meta)}).status_code == 422
