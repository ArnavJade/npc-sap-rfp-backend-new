"""SharePoint (Microsoft Graph) attachment download and output upload.

Ported from the old ``utils/sharepoint_client.py`` (the drive/item-addressed flow the
two public routes use): ``download_attachment_from_sharepoint(drive_id, item_id) ->
(filename, bytes)`` and ``upload_output_to_sharepoint(local_path, drive_id, folder_id,
filename) -> sp_ref`` (old keys: sp_file_id, sp_file_web_url, sp_drive_id,
sp_folder_id, filename, size).

Changes from the old code:
- Fixes the latent > 4 MB bug: simple ``PUT .../content`` is limited to 4 MB, so larger
  files use an upload session (``createUploadSession`` + sequential ``PUT`` chunks with
  ``Content-Range``; chunks are multiples of 320 KiB, 5 MiB by default). Chunk requests
  carry no ``Authorization`` header: the session URL is pre-authenticated.
- App-only Graph token (msal client credentials) cached until shortly before expiry;
  msal's blocking HTTP (tenant discovery, token requests) runs in a worker thread.
- One ``httpx.AsyncClient`` per call / ``async with SharePointClient(...)`` block, so
  nothing is bound to one event loop. Transport, token provider and retry sleep are
  injectable for tests.
- Typed ``SharePointError`` subclasses; pre-authenticated download/upload URLs never
  appear in exception messages or logs. Ids are URL-encoded as single path segments;
  a filename containing a path separator raises ValueError.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

import httpx

from .settings import SharePointConfig, load_sharepoint_config

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPES = ("https://graph.microsoft.com/.default",)

# Simple PUT is documented for files up to 4 MB. Decimal 4 MB is used as the cut-off, so a
# file is never sent by simple PUT under either reading of "MB". Upload sessions have no minimum.
SIMPLE_UPLOAD_MAX_BYTES = 4_000_000
UPLOAD_CHUNK_ALIGNMENT = 320 * 1024  # Graph: session chunk sizes must be multiples of 320 KiB
DEFAULT_CHUNK_SIZE = 16 * UPLOAD_CHUNK_ALIGNMENT  # 5 MiB
MAX_CHUNK_SIZE = 60 * 1024 * 1024  # Graph: at most 60 MiB per chunk request

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_DELAY = 60.0  # seconds; caps Retry-After and backoff
_TOKEN_REFRESH_MARGIN = 120.0  # seconds before expiry at which a cached token is refreshed

Sleep = Callable[[float], Awaitable[None]]


# --- Exceptions --------------------------------------------------------------
class SharePointError(RuntimeError):
    """Base class for SharePoint / Microsoft Graph failures."""


class SharePointNotConfiguredError(SharePointError):
    """Required AZ_* credentials are not set."""

    def __init__(self, missing: Sequence[str]):
        self.missing = list(missing)
        super().__init__(
            "SharePoint is not configured: set " + ", ".join(self.missing or ["AZ_* credentials"])
        )


class SharePointAuthError(SharePointError):
    """An app-only Microsoft Graph token could not be acquired."""


class SharePointHTTPError(SharePointError):
    """Graph (or a pre-authenticated SharePoint URL) answered with an error status."""

    def __init__(self, action: str, status_code: int, code: str | None = None,
                 detail: str | None = None):
        self.action, self.status_code, self.code, self.detail = action, status_code, code, detail
        super().__init__(f"{action} failed: HTTP {status_code}"
                         + (f" {code}" if code else "") + (f": {detail}" if detail else ""))

    @classmethod
    def from_response(cls, action: str, resp: httpx.Response) -> SharePointHTTPError:
        code: str | None = None
        detail: str | None = None
        try:
            error = resp.json().get("error")
            if isinstance(error, dict):
                code, detail = error.get("code"), error.get("message")
        except Exception:
            pass
        if not code and not detail:
            detail = resp.text[:200].strip() or None
        return cls(action, resp.status_code, code, detail)


# --- Token providers ---------------------------------------------------------
@runtime_checkable
class TokenProvider(Protocol):
    """Supplies a bearer token for Microsoft Graph."""

    async def get_token(self) -> str: ...


class MsalTokenProvider:
    """App-only (client-credentials) Graph token from msal, cached until near expiry.

    A threading.Lock (not asyncio.Lock) guards the refresh, so one provider can be
    shared by several event loops and threads.
    """

    def __init__(self, config: SharePointConfig, *, scopes: Sequence[str] = GRAPH_SCOPES,
                 app_factory: Callable[[], Any] | None = None) -> None:
        if not config.configured:
            raise SharePointNotConfiguredError(config.missing)
        self._config = config
        self._scopes = list(scopes)
        self._app_factory = app_factory or self._build_app
        self._app: Any = None
        self._lock = threading.Lock()
        self._cached: tuple[str, float] | None = None  # (token, monotonic expiry)

    async def get_token(self) -> str:
        return self._fresh_cached_token() or await asyncio.to_thread(self._refresh)

    def _fresh_cached_token(self) -> str | None:
        cached = self._cached
        if cached and time.monotonic() < cached[1] - _TOKEN_REFRESH_MARGIN:
            return cached[0]
        return None

    def _refresh(self) -> str:
        with self._lock:
            token = self._fresh_cached_token()
            if token:
                return token
            try:
                if self._app is None:
                    self._app = self._app_factory()
                result = self._app.acquire_token_for_client(scopes=self._scopes) or {}
            except Exception as exc:
                raise SharePointAuthError(
                    f"Could not acquire a Microsoft Graph token: {exc.__class__.__name__}: {exc}"
                ) from exc
            token = result.get("access_token")
            if not token:
                raise SharePointAuthError(
                    "Microsoft Graph token request failed: "
                    f"{result.get('error', 'unknown_error')}: {result.get('error_description', '')}".rstrip(": ")
                )
            try:
                expires_in = float(result.get("expires_in") or 3600)
            except (TypeError, ValueError):
                expires_in = 3600.0
            self._cached = (token, time.monotonic() + expires_in)
            return token

    def _build_app(self) -> Any:
        import msal  # imported lazily: only needed when SharePoint is actually used

        return msal.ConfidentialClientApplication(
            self._config.client_id,
            authority=self._config.authority,
            client_credential=self._config.client_secret,
        )


_DEFAULT_PROVIDERS: dict[tuple[str, str, str], MsalTokenProvider] = {}
_DEFAULT_PROVIDERS_LOCK = threading.Lock()


def default_token_provider(config: SharePointConfig | None = None) -> MsalTokenProvider:
    """Process-wide msal provider for the given (or env) config, so the token cache is shared.

    Raises:
        SharePointNotConfiguredError: AZ_TENANT_ID / AZ_CLIENT_ID / AZ_CLIENT_SECRET missing.
    """
    config = config if config is not None else load_sharepoint_config()
    if not config.configured:
        raise SharePointNotConfiguredError(config.missing)
    secret_hash = hashlib.sha256(config.client_secret.encode()).hexdigest()
    key = (config.tenant_id, config.client_id, secret_hash)
    with _DEFAULT_PROVIDERS_LOCK:
        provider = _DEFAULT_PROVIDERS.get(key)
        if provider is None:
            provider = _DEFAULT_PROVIDERS[key] = MsalTokenProvider(config)
        return provider


# --- Client ------------------------------------------------------------------
class SharePointClient:
    """Async Graph client for drive items addressed by explicit (drive_id, item_id).

    Use ``async with SharePointClient(...) as sp:`` (it owns one httpx.AsyncClient).
    ``token_provider`` defaults to the shared msal provider built from ``config``
    (or the environment); when one is injected, no configuration is needed.
    """

    def __init__(
        self,
        config: SharePointConfig | None = None,
        *,
        token_provider: TokenProvider | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if chunk_size <= 0 or chunk_size % UPLOAD_CHUNK_ALIGNMENT or chunk_size > MAX_CHUNK_SIZE:
            raise ValueError(
                f"chunk_size must be a positive multiple of {UPLOAD_CHUNK_ALIGNMENT} bytes "
                f"(320 KiB) and at most {MAX_CHUNK_SIZE} bytes, got {chunk_size}"
            )
        self._token_provider = token_provider or default_token_provider(config)
        self._transport = transport
        self._timeout = httpx.Timeout(timeout, connect=min(timeout, 10.0))
        self._max_retries = max(0, max_retries)
        self._chunk_size = chunk_size
        self._sleep = sleep
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> SharePointClient:
        self._client()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(transport=self._transport, timeout=self._timeout)
        return self._http

    async def get_item(self, drive_id: str, item_id: str) -> dict[str, Any]:
        """GET the driveItem metadata."""
        action = f"Get SharePoint item {item_id!r} (drive {drive_id!r})"
        url = f"{GRAPH_BASE}/drives/{_segment(drive_id, 'drive_id')}/items/{_segment(item_id, 'item_id')}"
        return _json_object(await self._send("GET", url, action=action, auth=True), action)

    async def download_item(self, drive_id: str, item_id: str) -> tuple[str, bytes]:
        """Download a file driveItem. Returns (filename, content)."""
        item = await self.get_item(drive_id, item_id)
        if "folder" in item:
            raise SharePointError(f"SharePoint item {item_id!r} is a folder, not a file")
        download_url = item.get("@microsoft.graph.downloadUrl")
        if not download_url:
            raise SharePointError(f"SharePoint item {item_id!r} (drive {drive_id!r}) has no download URL")
        filename = item.get("name") or item_id
        resp = await self._send("GET", download_url, action=f"Download {filename!r}", auth=False,
                                follow_redirects=True)
        logger.info("SharePoint download complete: %s (%d bytes) drive=%s item=%s",
                    filename, len(resp.content), drive_id, item_id)
        return filename, resp.content

    async def upload_file(self, local_path: str | os.PathLike[str], drive_id: str,
                          folder_id: str, filename: str | None = None) -> dict[str, Any]:
        """Upload a local file into a folder. Returns the resulting driveItem.

        Existing files with the same name are replaced (as with the old simple PUT).
        """
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(f"File to upload not found: {path}")
        name = _bare_filename(filename or path.name)
        size = path.stat().st_size
        target = (f"{GRAPH_BASE}/drives/{_segment(drive_id, 'drive_id')}/items/"
                  f"{_segment(folder_id, 'folder_id')}:/{quote(name, safe='')}:")
        simple = size <= SIMPLE_UPLOAD_MAX_BYTES
        if simple:
            item = await self._simple_upload(path, target, name)
        else:
            item = await self._session_upload(path, target, name, size)
        logger.info("SharePoint upload complete: %s (%d bytes, %s) -> item=%s drive=%s folder=%s",
                    name, size, "simple" if simple else "session", item.get("id"), drive_id, folder_id)
        return item

    async def _simple_upload(self, path: Path, target: str, name: str) -> dict[str, Any]:
        action = f"Upload {name!r}"
        data = await asyncio.to_thread(path.read_bytes)
        resp = await self._send("PUT", f"{target}/content", action=action, auth=True, content=data,
                                headers={"Content-Type": "application/octet-stream"})
        return _json_object(resp, action)

    async def _session_upload(self, path: Path, target: str, name: str, size: int) -> dict[str, Any]:
        action = f"Create upload session for {name!r}"
        resp = await self._send(
            "POST", f"{target}/createUploadSession", action=action, auth=True,
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        )
        upload_url = _json_object(resp, action).get("uploadUrl")
        if not upload_url:
            raise SharePointError(f"{action}: response has no uploadUrl")
        try:
            return await self._upload_chunks(upload_url, path, name, size)
        except Exception:
            await self._cancel_session(upload_url, name)
            raise

    async def _upload_chunks(self, upload_url: str, path: Path, name: str, size: int) -> dict[str, Any]:
        start = 0
        max_requests = 2 * math.ceil(size / self._chunk_size) + 2  # guards against a looping server
        for _ in range(max_requests):
            end = min(start + self._chunk_size, size) - 1
            chunk = await asyncio.to_thread(_read_range, path, start, end - start + 1)
            action = f"Upload {name!r} bytes {start}-{end}/{size}"
            resp = await self._send("PUT", upload_url, action=action, auth=False, content=chunk,
                                    headers={"Content-Range": f"bytes {start}-{end}/{size}"})
            if resp.status_code in (200, 201):  # last byte received: body is the driveItem
                return _json_object(resp, action)
            if resp.status_code != 202:
                raise SharePointError(f"{action}: unexpected HTTP {resp.status_code}")
            next_start = _next_expected_start(resp, default=end + 1)
            if next_start is None or next_start >= size:
                raise SharePointError(f"{action}: upload session accepted all bytes but returned no item")
            start = next_start
        raise SharePointError(f"Upload of {name!r} did not complete after {max_requests} chunk requests")

    async def _cancel_session(self, upload_url: str, name: str) -> None:
        """Best-effort DELETE of a failed upload session (frees the partial upload)."""
        try:
            await self._client().request("DELETE", upload_url)
        except Exception as exc:
            logger.debug("Could not cancel upload session for %s: %s", name, exc.__class__.__name__)

    async def _send(self, method: str, url: str, *, action: str, auth: bool,
                    headers: dict[str, str] | None = None, content: bytes | None = None,
                    json: Any = None, follow_redirects: bool = False) -> httpx.Response:
        """Send with bounded retries on network errors, 429 and 5xx (honouring Retry-After).

        ``auth=False`` is used for pre-authenticated URLs: no bearer token, no Accept header.
        """
        http = self._client()
        attempt = 0
        while True:
            req_headers = dict(headers or {})
            if auth:
                req_headers["Accept"] = "application/json"
                req_headers["Authorization"] = f"Bearer {await self._token_provider.get_token()}"
            try:
                resp = await http.request(method, url, headers=req_headers, content=content,
                                          json=json, follow_redirects=follow_redirects)
            except httpx.HTTPError as exc:
                if not isinstance(exc, httpx.TransportError) or attempt >= self._max_retries:
                    raise SharePointError(f"{action} failed: {exc.__class__.__name__}: {exc}") from exc
                delay = _backoff(attempt)
                logger.warning("%s: %s; retrying in %.1fs", action, exc.__class__.__name__, delay)
            else:
                if resp.is_success:
                    return resp
                if resp.status_code not in _RETRY_STATUSES or attempt >= self._max_retries:
                    raise SharePointHTTPError.from_response(action, resp)
                delay = _retry_after(resp, attempt)
                logger.warning("%s: HTTP %d; retrying in %.1fs", action, resp.status_code, delay)
            await self._sleep(delay)
            attempt += 1


# --- Module-level API (signatures used by the routes / job runner) -----------
async def download_attachment_from_sharepoint(
    drive_id: str,
    item_id: str,
    *,
    config: SharePointConfig | None = None,
    token_provider: TokenProvider | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, bytes]:
    """Download one attachment addressed by (drive_id, item_id). Returns (filename, bytes).

    Raises:
        SharePointNotConfiguredError, SharePointAuthError, SharePointHTTPError,
        SharePointError (all RuntimeError), or ValueError for an empty id.
    """
    async with SharePointClient(config, token_provider=token_provider, transport=transport) as sp:
        return await sp.download_item(drive_id, item_id)


async def upload_output_to_sharepoint(
    local_path: str | os.PathLike[str],
    drive_id: str,
    folder_id: str,
    filename: str | None = None,
    *,
    config: SharePointConfig | None = None,
    token_provider: TokenProvider | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Upload a generated output into the folder (drive_id, folder_id) from user_metadata.

    Files above 4 MB use an upload session. Returns the old ``sp_ref`` shape::

        {"sp_file_id", "sp_file_web_url", "sp_drive_id", "sp_folder_id", "filename", "size"}

    Raises:
        FileNotFoundError, ValueError (empty id / filename with a path separator),
        or a SharePointError subclass (RuntimeError).
    """
    fname = filename or os.path.basename(os.fspath(local_path))
    async with SharePointClient(config, token_provider=token_provider, transport=transport) as sp:
        item = await sp.upload_file(local_path, drive_id, folder_id, fname)
    return {
        "sp_file_id": item.get("id"),
        "sp_file_web_url": item.get("webUrl"),
        "sp_drive_id": drive_id,
        "sp_folder_id": folder_id,
        "filename": item.get("name", fname),
        "size": item.get("size"),
    }


# --- Helpers -----------------------------------------------------------------
def _segment(value: str, name: str) -> str:
    """Validate a Graph id and encode it as a single URL path segment."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return quote(value.strip(), safe="!")


def _bare_filename(name: str) -> str:
    name = (name or "").strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError(f"filename must be a bare file name without path separators, got {name!r}")
    return name


def _read_range(path: Path, start: int, length: int) -> bytes:
    with path.open("rb") as fh:
        fh.seek(start)
        data = fh.read(length)
    if len(data) != length:
        raise SharePointError(f"{path.name} changed size during upload")
    return data


def _json_object(resp: httpx.Response, action: str) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError as exc:
        raise SharePointError(f"{action}: expected a JSON response (HTTP {resp.status_code})") from exc
    if not isinstance(data, dict):
        raise SharePointError(f"{action}: expected a JSON object (HTTP {resp.status_code})")
    return data


def _next_expected_start(resp: httpx.Response, *, default: int) -> int | None:
    """First offset of Graph's ``nextExpectedRanges`` (e.g. ``["5242880-"]``).

    ``default`` (the next sequential byte) if the body has no ranges; None if the
    server reports an explicitly empty list.
    """
    try:
        ranges = resp.json().get("nextExpectedRanges")
    except Exception:
        return default
    if ranges is None:
        return default
    if not ranges:
        return None
    try:
        return int(str(ranges[0]).split("-", 1)[0])
    except ValueError:
        return default


def _backoff(attempt: int) -> float:
    return min(float(2 ** attempt), _MAX_RETRY_DELAY)


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    try:
        return min(max(float(resp.headers["Retry-After"]), 0.0), _MAX_RETRY_DELAY)
    except (KeyError, ValueError):
        return _backoff(attempt)
