"""Activity API client: payload contract, retries, disabled mode, never-raises."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.platform.activity import (
    ActivityClient,
    report_effort_excel_generated,
    report_proposal_generated,
    send_activity,
)
from app.platform.request_context import RequestContext
from app.platform.settings import ActivityConfig

BASE_URL = "https://activity.example.com/"
SP_REF = {"sp_file_id": "01ITEM-OUT", "sp_file_web_url": "https://x", "filename": "out.xlsx"}


def _ctx(**overrides) -> RequestContext:
    meta = {
        "team_id": "team-1",
        "workspace_id": "ws-1",
        "organization_id": "org-1",
        "user_id": "user-1",
        "agent_ids": ["agent-1"],
        "company_name": "Acme Corp",
        **overrides,
    }
    return RequestContext.from_user_metadata_string(
        json.dumps(meta), authorization="Bearer header.payload.sig$YashUnified2025$neupac-extra")


class Recorder:
    """MockTransport handler that replays scripted responses / exceptions."""

    def __init__(self, *script):
        self.script = list(script)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def _client(recorder: Recorder, sleeps: list[float], **config) -> ActivityClient:
    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    cfg = ActivityConfig(base_url=config.pop("base_url", BASE_URL), **config)
    return ActivityClient(cfg, transport=httpx.MockTransport(recorder), sleep=fake_sleep)


def test_retry_then_success_sends_the_old_payload():
    recorder = Recorder(
        httpx.ConnectError("connection refused"),
        httpx.Response(503, text="busy"),
        httpx.Response(201, json={"ok": True}),
    )
    sleeps: list[float] = []

    ok = asyncio.run(report_effort_excel_generated(_ctx(), SP_REF, client=_client(recorder, sleeps)))

    assert ok is True
    assert len(recorder.requests) == 3
    assert sleeps == [1, 2]  # exponential backoff
    req = recorder.requests[-1]
    assert req.method == "POST"
    assert str(req.url) == "https://activity.example.com/api/v1/workspaces/ws-1/agents/activity"
    assert req.headers["Authorization"] == "Bearer header.payload.sig"  # prefix + NEUPAC suffix stripped
    assert req.headers["organization-id"] == "org-1"
    assert req.headers["accept"] == "application/json"
    assert req.headers["Content-Type"] == "application/json"
    assert json.loads(req.content) == {
        "agent_id": "agent-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "origin": "model_generated",
        "details": {
            "document_keys": ["01ITEM-OUT"],
            "repo_link": [],
            "group_name": "Acme Corp",
            "title": "Excel Generated for Review",
            "message": "Excel with the efforts and modules for review",
        },
    }


def test_proposal_event_with_additive_extra():
    recorder = Recorder(httpx.Response(200))
    ok = asyncio.run(report_proposal_generated(
        _ctx(), SP_REF, extra={"job_id": "job-42", "title": "ignored override"},
        client=_client(recorder, [])))

    assert ok is True
    details = json.loads(recorder.requests[0].content)["details"]
    assert details["title"] == "Generated final RFP response"
    assert details["message"] == "Response with modules and efforts finalized."
    assert details["job_id"] == "job-42"


def test_disabled_when_base_url_empty(monkeypatch):
    recorder = Recorder()  # any request would fail (empty script)
    assert asyncio.run(report_effort_excel_generated(
        _ctx(), SP_REF, client=_client(recorder, [], base_url=""))) is False
    assert recorder.requests == []

    # Default client reads the environment at call time
    monkeypatch.setenv("ACTIVITY_API_BASE_URL", "")
    assert asyncio.run(report_proposal_generated(_ctx(), SP_REF)) is False


def test_skipped_without_workspace_id():
    recorder = Recorder()
    assert asyncio.run(report_effort_excel_generated(
        _ctx(workspace_id=None), SP_REF, client=_client(recorder, []))) is False
    assert recorder.requests == []


def test_non_retryable_client_error_gives_up_immediately():
    recorder = Recorder(httpx.Response(401, text="bad token"))
    sleeps: list[float] = []
    assert asyncio.run(report_effort_excel_generated(
        _ctx(), SP_REF, client=_client(recorder, sleeps))) is False
    assert len(recorder.requests) == 1
    assert sleeps == []


def test_exhausted_retries_return_false():
    recorder = Recorder(httpx.Response(500), httpx.Response(429), httpx.Response(502))
    sleeps: list[float] = []
    assert asyncio.run(report_proposal_generated(
        _ctx(), None, client=_client(recorder, sleeps, max_retries=3))) is False
    assert len(recorder.requests) == 3
    assert sleeps == [1, 2]
    assert json.loads(recorder.requests[0].content)["details"]["document_keys"] == []


@pytest.mark.parametrize("bad_ctx", [None, object()])
def test_never_raises_on_bad_context(bad_ctx):
    recorder = Recorder()
    assert asyncio.run(report_effort_excel_generated(bad_ctx, SP_REF, client=_client(recorder, []))) is False
    assert recorder.requests == []


def test_never_raises_on_unserialisable_extra():
    recorder = Recorder(httpx.Response(200))
    sleeps: list[float] = []
    assert asyncio.run(report_effort_excel_generated(
        _ctx(), SP_REF, extra={"blob": object()}, client=_client(recorder, sleeps))) is False
    assert recorder.requests == [] and sleeps == []


def test_send_activity_module_function():
    recorder = Recorder(httpx.Response(204))
    ok = asyncio.run(send_activity("ws/../x", None, None, None, None, "model_generated", {"title": "t"},
                                   client=_client(recorder, [])))
    assert ok is True
    req = recorder.requests[0]
    assert req.url.raw_path == b"/api/v1/workspaces/ws%2F..%2Fx/agents/activity"  # one path segment
    assert "Authorization" not in req.headers and "organization-id" not in req.headers
    assert json.loads(req.content)["agent_id"] == ""
