"""SharePoint download / upload against httpx.MockTransport (no real Graph calls)."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest

from app.platform.settings import SharePointConfig
from app.platform.sharepoint import (
    DEFAULT_CHUNK_SIZE,
    SIMPLE_UPLOAD_MAX_BYTES,
    UPLOAD_CHUNK_ALIGNMENT,
    MsalTokenProvider,
    SharePointAuthError,
    SharePointClient,
    SharePointError,
    SharePointHTTPError,
    SharePointNotConfiguredError,
    download_attachment_from_sharepoint,
    upload_output_to_sharepoint,
)

DRIVE = "b!Y_rgDRIVE-1"
FOLDER = "01I3FOLDER"
TOKEN = "fake-graph-token"
DOWNLOAD_URL = "https://tenant.sharepoint.com/_layouts/15/download.aspx?UniqueId=abc&tempauth=DLSECRET"
UPLOAD_URL = "https://tenant.sharepoint.com/_api/v2.0/drives/x/items/y/uploadSession?guid=g1&tempauth=ULSECRET"


class FakeTokenProvider:
    def __init__(self, token: str = TOKEN):
        self.token = token
        self.calls = 0

    async def get_token(self) -> str:
        self.calls += 1
        return self.token


def _payload(size: int) -> bytes:
    return (bytes(range(256)) * (size // 256 + 1))[:size]


def _write(tmp_path: Path, name: str, size: int) -> tuple[Path, bytes]:
    data = _payload(size)
    path = tmp_path / name
    path.write_bytes(data)
    return path, data


def _item(name: str, size: int) -> dict:
    return {"id": "NEWITEM01", "name": name, "size": size,
            "webUrl": f"https://tenant.sharepoint.com/sites/presales/Shared%20Documents/{name}"}


def _no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected request: {request.method} {request.url}")


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def test_download_attachment():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "graph.microsoft.com":
            assert request.method == "GET"
            assert request.url.path == f"/v1.0/drives/{DRIVE}/items/01ITEM"
            return httpx.Response(200, json={
                "id": "01ITEM", "name": "Client RFP.pdf", "size": 8, "file": {},
                "@microsoft.graph.downloadUrl": DOWNLOAD_URL,
            })
        assert str(request.url) == DOWNLOAD_URL
        return httpx.Response(200, content=b"%PDF-1.7")

    tokens = FakeTokenProvider()
    filename, content = asyncio.run(download_attachment_from_sharepoint(
        DRIVE, "01ITEM", token_provider=tokens, transport=httpx.MockTransport(handler)))

    assert (filename, content) == ("Client RFP.pdf", b"%PDF-1.7")
    graph_req, download_req = seen
    assert graph_req.headers["Authorization"] == f"Bearer {TOKEN}"
    assert "Authorization" not in download_req.headers  # pre-authenticated URL
    assert tokens.calls == 1


def test_download_errors_are_clear_and_do_not_leak_download_url():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "graph.microsoft.com":
            return httpx.Response(200, json={"id": "01ITEM", "name": "a.pdf",
                                             "@microsoft.graph.downloadUrl": DOWNLOAD_URL})
        return httpx.Response(403, text="forbidden")

    with pytest.raises(SharePointHTTPError) as excinfo:
        asyncio.run(download_attachment_from_sharepoint(
            DRIVE, "01ITEM", token_provider=FakeTokenProvider(), transport=httpx.MockTransport(handler)))
    assert excinfo.value.status_code == 403
    assert "DLSECRET" not in str(excinfo.value)
    assert "'a.pdf'" in str(excinfo.value)


def test_download_missing_item_maps_graph_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "itemNotFound", "message": "The resource could not be found."}})

    with pytest.raises(SharePointHTTPError, match="HTTP 404 itemNotFound: The resource could not be found") as excinfo:
        asyncio.run(download_attachment_from_sharepoint(
            DRIVE, "MISSING", token_provider=FakeTokenProvider(), transport=httpx.MockTransport(handler)))
    assert excinfo.value.code == "itemNotFound"


def test_download_folder_item_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "F1", "name": "Inputs", "folder": {"childCount": 2}})

    with pytest.raises(SharePointError, match="is a folder"):
        asyncio.run(download_attachment_from_sharepoint(
            DRIVE, "F1", token_provider=FakeTokenProvider(), transport=httpx.MockTransport(handler)))


def test_not_configured_raises_before_any_request():
    with pytest.raises(SharePointNotConfiguredError, match="AZ_TENANT_ID, AZ_CLIENT_ID, AZ_CLIENT_SECRET") as excinfo:
        asyncio.run(download_attachment_from_sharepoint(
            DRIVE, "01ITEM", config=SharePointConfig(), transport=httpx.MockTransport(_no_network)))
    assert isinstance(excinfo.value, RuntimeError)  # old code raised RuntimeError here


def test_graph_throttling_is_retried_with_retry_after():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json={"id": "01ITEM", "name": "x.docx"})

    async def run() -> dict:
        async with SharePointClient(token_provider=FakeTokenProvider(),
                                    transport=httpx.MockTransport(handler), sleep=fake_sleep) as sp:
            return await sp.get_item(DRIVE, "01ITEM")

    assert asyncio.run(run())["name"] == "x.docx"
    assert len(calls) == 2
    assert sleeps == [3.0]


# ---------------------------------------------------------------------------
# Upload: simple PUT (<= 4 MB)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [0, 1234, SIMPLE_UPLOAD_MAX_BYTES])
def test_simple_upload_up_to_4mb(tmp_path, size):
    name = "YASH SAP RFP Response Acme.docx"
    path, data = _write(tmp_path, name, size)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json=_item(name, size))

    sp_ref = asyncio.run(upload_output_to_sharepoint(
        str(path), DRIVE, FOLDER, token_provider=FakeTokenProvider(),
        transport=httpx.MockTransport(handler)))

    assert len(seen) == 1
    req = seen[0]
    assert req.method == "PUT"
    assert req.url.path == f"/v1.0/drives/{DRIVE}/items/{FOLDER}:/{name}:/content"
    assert b"YASH%20SAP%20RFP%20Response%20Acme.docx" in req.url.raw_path
    assert req.headers["Authorization"] == f"Bearer {TOKEN}"
    assert req.headers["Content-Type"] == "application/octet-stream"
    assert req.content == data
    assert sp_ref == {
        "sp_file_id": "NEWITEM01",
        "sp_file_web_url": _item(name, size)["webUrl"],
        "sp_drive_id": DRIVE,
        "sp_folder_id": FOLDER,
        "filename": name,
        "size": size,
    }


def test_upload_rejects_bad_input(tmp_path):
    path, _ = _write(tmp_path, "out.xlsx", 10)
    transport = httpx.MockTransport(_no_network)
    with pytest.raises(ValueError, match="bare file name"):
        asyncio.run(upload_output_to_sharepoint(path, DRIVE, FOLDER, "sub/out.xlsx",
                                                token_provider=FakeTokenProvider(), transport=transport))
    with pytest.raises(ValueError, match="folder_id"):
        asyncio.run(upload_output_to_sharepoint(path, DRIVE, " ", token_provider=FakeTokenProvider(),
                                                transport=transport))
    with pytest.raises(FileNotFoundError):
        asyncio.run(upload_output_to_sharepoint(tmp_path / "nope.xlsx", DRIVE, FOLDER,
                                                token_provider=FakeTokenProvider(), transport=transport))
    with pytest.raises(ValueError, match="320 KiB"):
        SharePointClient(token_provider=FakeTokenProvider(), chunk_size=5_000_000)


# ---------------------------------------------------------------------------
# Upload: upload session (> 4 MB)
# ---------------------------------------------------------------------------


class FakeUploadSession:
    """Graph createUploadSession + chunk endpoint that enforces contiguous Content-Range."""

    def __init__(self, name: str, total: int, fail_on_chunk: int | None = None):
        self.name, self.total, self.fail_on_chunk = name, total, fail_on_chunk
        self.received = bytearray()
        self.requests: list[httpx.Request] = []
        self.chunks: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "graph.microsoft.com":
            assert request.method == "POST"
            assert request.url.path == f"/v1.0/drives/{DRIVE}/items/{FOLDER}:/{self.name}:/createUploadSession"
            return httpx.Response(200, json={"uploadUrl": UPLOAD_URL, "nextExpectedRanges": ["0-"],
                                             "expirationDateTime": "2026-10-09T00:00:00Z"})
        assert str(request.url) == UPLOAD_URL
        if request.method == "DELETE":
            return httpx.Response(204)
        assert request.method == "PUT"
        self.chunks.append(request)
        if self.fail_on_chunk == len(self.chunks):
            return httpx.Response(400, json={"error": {"code": "invalidRange", "message": "bad range"}})
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", request.headers["Content-Range"])
        assert match, request.headers["Content-Range"]
        start, end, total = map(int, match.groups())
        assert (start, total) == (len(self.received), self.total)
        assert len(request.content) == end - start + 1 == int(request.headers["Content-Length"])
        self.received.extend(request.content)
        if len(self.received) < total:
            return httpx.Response(202, json={"nextExpectedRanges": [f"{len(self.received)}-"],
                                             "expirationDateTime": "2026-10-09T00:00:00Z"})
        return httpx.Response(201, json=_item(self.name, total))


@pytest.mark.parametrize("size", [SIMPLE_UPLOAD_MAX_BYTES + 1, 2 * DEFAULT_CHUNK_SIZE + 12_345])
def test_upload_session_above_4mb(tmp_path, size):
    name = "Claude_BP_Effort_Output_Acme.xlsx"
    path, data = _write(tmp_path, name, size)
    server = FakeUploadSession(name, size)

    tokens = FakeTokenProvider()
    sp_ref = asyncio.run(upload_output_to_sharepoint(
        path, DRIVE, FOLDER, name, token_provider=tokens, transport=httpx.MockTransport(server)))

    create = server.requests[0]
    assert create.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(create.content) == {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
    assert tokens.calls == 1  # only the createUploadSession call is authenticated

    expected_ranges = []
    for start in range(0, size, DEFAULT_CHUNK_SIZE):
        end = min(start + DEFAULT_CHUNK_SIZE, size) - 1
        expected_ranges.append(f"bytes {start}-{end}/{size}")
    assert [c.headers["Content-Range"] for c in server.chunks] == expected_ranges
    for chunk in server.chunks:
        assert "Authorization" not in chunk.headers
    for chunk in server.chunks[:-1]:
        assert len(chunk.content) == DEFAULT_CHUNK_SIZE
        assert len(chunk.content) % UPLOAD_CHUNK_ALIGNMENT == 0

    assert bytes(server.received) == data
    assert sp_ref == {
        "sp_file_id": "NEWITEM01",
        "sp_file_web_url": _item(name, size)["webUrl"],
        "sp_drive_id": DRIVE,
        "sp_folder_id": FOLDER,
        "filename": name,
        "size": size,
    }
    assert DEFAULT_CHUNK_SIZE == 5 * 1024 * 1024


def test_upload_session_failure_cancels_session_without_leaking_url(tmp_path):
    name = "big.docx"
    size = 2 * DEFAULT_CHUNK_SIZE + 1
    path, _ = _write(tmp_path, name, size)
    server = FakeUploadSession(name, size, fail_on_chunk=2)

    with pytest.raises(SharePointHTTPError) as excinfo:
        asyncio.run(upload_output_to_sharepoint(path, DRIVE, FOLDER, token_provider=FakeTokenProvider(),
                                                transport=httpx.MockTransport(server)))

    assert excinfo.value.status_code == 400
    assert "bytes 5242880-10485759" in str(excinfo.value)
    assert "ULSECRET" not in str(excinfo.value)
    assert server.requests[-1].method == "DELETE"


# ---------------------------------------------------------------------------
# msal token provider (fake msal app, no network)
# ---------------------------------------------------------------------------


class FakeMsalApp:
    def __init__(self, results: list[dict]):
        self.results = results
        self.calls = 0

    def acquire_token_for_client(self, scopes: list[str]) -> dict:
        assert scopes == ["https://graph.microsoft.com/.default"]
        self.calls += 1
        return self.results.pop(0)


CONFIG = SharePointConfig(tenant_id="t", client_id="c", client_secret="s3cr3t")


def test_msal_token_is_cached_until_near_expiry():
    app = FakeMsalApp([{"access_token": "tok-1", "expires_in": 3599},
                       {"access_token": "tok-2", "expires_in": 3599}])
    provider = MsalTokenProvider(CONFIG, app_factory=lambda: app)

    async def run() -> list[str]:
        return [await provider.get_token(), await provider.get_token()]

    assert asyncio.run(run()) == ["tok-1", "tok-1"]
    assert app.calls == 1

    expiring = MsalTokenProvider(CONFIG, app_factory=lambda: app)
    app.results = [{"access_token": "short", "expires_in": 30}, {"access_token": "fresh", "expires_in": 3599}]
    assert asyncio.run(expiring.get_token()) == "short"
    assert asyncio.run(expiring.get_token()) == "fresh"  # inside the refresh margin -> re-acquired


def test_msal_token_error_is_clear():
    app = FakeMsalApp([{"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret."}])
    provider = MsalTokenProvider(CONFIG, app_factory=lambda: app)
    with pytest.raises(SharePointAuthError, match="invalid_client: AADSTS7000215") as excinfo:
        asyncio.run(provider.get_token())
    assert "s3cr3t" not in str(excinfo.value)
    with pytest.raises(SharePointNotConfiguredError):
        MsalTokenProvider(SharePointConfig(tenant_id="t"))
