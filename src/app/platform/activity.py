"""
Activity API Client
====================
Report workflow events to the platform Activity API. Ported from the old
``utils/activity_client.py``. The endpoint, headers, payload, event titles and
messages, and the retry policy are unchanged.

Endpoint: POST {ACTIVITY_API_BASE_URL}/api/v1/workspaces/{workspace_id}/agents/activity

Required headers:
  - accept: application/json
  - Authorization: Bearer <access_token>
  - organization-id: <org_id>
  - Content-Type: application/json

Payload:
  {
    "agent_id":     "<agent_id>",
    "user_id":      "<user_id>",
    "workspace_id": "<workspace_id>",
    "origin":       "model_generated",
    "details": {
      "document_keys": ["<sp_item_id>", ...],   # SharePoint item ids of the outputs
      "repo_link":     [],
      "group_name":    "<repo / group name>",
      "title":         "<event title>",
      "message":       "<event message>"
    }
  }

Design:
  - The event is ESSENTIAL, so sending retries with exponential backoff
    (1s, 2s, 4s, ...) on network errors (any httpx error), HTTP 429 and HTTP 5xx;
    other 4xx are not retried.
  - It NEVER raises (except task cancellation): after exhausting retries, or on
    any unexpected error, it logs and returns False, so a reporting failure never
    discards an already generated and uploaded document.
  - No-op (returns False) when ACTIVITY_API_BASE_URL is empty or the request has
    no workspace_id.

Port changes: configuration is read at call time (``ActivityConfig``), not at
import; the transport and backoff sleep are injectable (``ActivityClient``) for
tests; the report helpers take an optional ``extra`` mapping of additional
``details`` fields (additive only: the standard keys cannot be overridden); the
workspace id is URL-encoded as one path segment.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .request_context import RequestContext
from .settings import ActivityConfig, load_activity_config

logger = logging.getLogger(__name__)

# Single origin used for all documents this agent generates
ORIGIN_MODEL_GENERATED = "model_generated"

# NEUPAC appends this separator after the real JWT in the bearer token
# (e.g. "<jwt>$YashUnified2025$<extra>"). The real, verifiable token is the part
# BEFORE the separator; forwarding the whole string corrupts the JWT signature.
CUSTOM_TOKEN_SEPARATOR = "$YashUnified2025$"

EFFORT_EXCEL_TITLE = "Excel Generated for Review"
EFFORT_EXCEL_MESSAGE = "Excel with the efforts and modules for review"
PROPOSAL_TITLE = "Generated final RFP response"
PROPOSAL_MESSAGE = "Response with modules and efforts finalized."

Sleep = Callable[[float], Awaitable[None]]


def _clean_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """
    Normalise an incoming Authorization value into a clean bearer JWT:
      - drop an optional "Bearer " prefix
      - drop NEUPAC's "$YashUnified2025$…" suffix (keep the part before it)
    Returns None if there is no token.
    """
    if not authorization:
        return None
    token = authorization.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if CUSTOM_TOKEN_SEPARATOR in token:
        token = token.split(CUSTOM_TOKEN_SEPARATOR, 1)[0]
    token = token.strip()
    return token or None


def _build_headers(
    authorization: Optional[str],
    organization_id: Optional[str],
) -> dict[str, str]:
    """Build required Activity API request headers."""
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    clean_token = _clean_bearer_token(authorization)
    if clean_token:
        # Forward a clean "Bearer <jwt>" — NEUPAC's $YashUnified2025$ suffix and
        # any existing Bearer prefix are stripped so the signature verifies.
        headers["Authorization"] = f"Bearer {clean_token}"
    if organization_id:
        headers["organization-id"] = organization_id
    return headers


def _build_details(
    document_keys: list[str],
    title: str,
    message: str,
    group_name: Optional[str],
    extra: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build the `details` block of the Activity API payload (+ additive ``extra`` keys)."""
    details: dict[str, Any] = {
        "document_keys": document_keys or [],
        "repo_link": [],
        "group_name": group_name or "",
        "title": title,
        "message": message,
    }
    for key, value in (extra or {}).items():
        if key in details:
            logger.debug("Activity details: ignoring extra key %r (standard field)", key)
            continue
        details[key] = value
    return details


class ActivityClient:
    """Sends Activity API events. Config defaults to the environment at construction."""

    def __init__(
        self,
        config: ActivityConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.config = config if config is not None else load_activity_config()
        self._transport = transport
        self._sleep = sleep

    async def send_activity(
        self,
        workspace_id: Optional[str],
        agent_id: Optional[str],
        user_id: Optional[str],
        organization_id: Optional[str],
        authorization: Optional[str],
        origin: str,
        details: Mapping[str, Any],
    ) -> bool:
        """POST one event, retrying transient failures. Returns True on success; never raises."""
        try:
            return await self._send(workspace_id, agent_id, user_id, organization_id,
                                    authorization, origin, details)
        except Exception:
            logger.exception("Activity API: unexpected error for origin=%s (ignored)", origin)
            return False

    async def _send(
        self,
        workspace_id: Optional[str],
        agent_id: Optional[str],
        user_id: Optional[str],
        organization_id: Optional[str],
        authorization: Optional[str],
        origin: str,
        details: Mapping[str, Any],
    ) -> bool:
        cfg = self.config
        if not cfg.configured:
            logger.debug("Activity API not configured (ACTIVITY_API_BASE_URL not set). "
                         "Skipping event: origin=%s", origin)
            return False
        if not workspace_id:
            logger.debug("No workspace_id available — skipping activity event: origin=%s", origin)
            return False

        url = f"{cfg.base_url}/api/v1/workspaces/{quote(workspace_id, safe='')}/agents/activity"
        payload = {
            "agent_id": agent_id or "",
            "user_id": user_id or "",
            "workspace_id": workspace_id,
            "origin": origin,
            "details": dict(details),
        }
        headers = _build_headers(authorization, organization_id)

        last_error = "unknown error"
        async with httpx.AsyncClient(timeout=cfg.timeout, transport=self._transport) as client:
            for attempt in range(1, cfg.max_retries + 1):
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                except httpx.HTTPError as e:  # network errors / timeouts: retryable
                    last_error = f"{e.__class__.__name__}: {e}"
                else:
                    if resp.is_success:
                        logger.info("Activity reported: origin=%s workspace=%s status=%s "
                                    "(attempt %d/%d)", origin, workspace_id, resp.status_code,
                                    attempt, cfg.max_retries)
                        return True
                    # Non-retryable client errors (4xx except 429): give up immediately.
                    if resp.status_code < 500 and resp.status_code != 429:
                        logger.warning("Activity API returned non-retryable %s for origin=%s: %s",
                                       resp.status_code, origin, resp.text[:200])
                        return False
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"

                # Backoff before the next attempt (skip after the final attempt)
                if attempt < cfg.max_retries:
                    backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s, ...
                    logger.warning("Activity API attempt %d/%d failed (origin=%s, error=%s); "
                                   "retrying in %ss", attempt, cfg.max_retries, origin,
                                   last_error, backoff)
                    await self._sleep(backoff)

        logger.error("Activity API failed after %d attempts: origin=%s workspace=%s error=%s",
                     cfg.max_retries, origin, workspace_id, last_error)
        return False

    async def report_effort_excel_generated(
        self,
        request_ctx: RequestContext,
        sp_ref: Optional[Mapping[str, Any]] = None,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Report that the effort workbook (for review) was generated and uploaded."""
        return await self._report(request_ctx, sp_ref, extra, EFFORT_EXCEL_TITLE, EFFORT_EXCEL_MESSAGE)

    async def report_proposal_generated(
        self,
        request_ctx: RequestContext,
        sp_ref: Optional[Mapping[str, Any]] = None,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Report that the final RFP response document was generated and uploaded."""
        return await self._report(request_ctx, sp_ref, extra, PROPOSAL_TITLE, PROPOSAL_MESSAGE)

    async def _report(
        self,
        request_ctx: RequestContext,
        sp_ref: Optional[Mapping[str, Any]],
        extra: Optional[Mapping[str, Any]],
        title: str,
        message: str,
    ) -> bool:
        try:
            item_id = (sp_ref or {}).get("sp_file_id")
            details = _build_details(
                document_keys=[item_id] if item_id else [],
                title=title,
                message=message,
                group_name=getattr(request_ctx, "company_name", None),
                extra=extra,
            )
            return await self.send_activity(
                workspace_id=request_ctx.get_workspace_id(),
                agent_id=request_ctx.get_agent_id(),
                user_id=request_ctx.get_user_id(),
                organization_id=request_ctx.get_organization_id(),
                authorization=request_ctx.get_authorization(),
                origin=ORIGIN_MODEL_GENERATED,
                details=details,
            )
        except Exception:
            logger.exception("Activity API: could not report %r (ignored)", title)
            return False


# ---------------------------------------------------------------------------
# Module-level API (same call shapes as the old client)
# ---------------------------------------------------------------------------


def _client_or_default(client: ActivityClient | None) -> ActivityClient | None:
    if client is not None:
        return client
    try:
        return ActivityClient()
    except Exception:
        logger.exception("Activity API: could not build client (ignored)")
        return None


async def send_activity(
    workspace_id: Optional[str],
    agent_id: Optional[str],
    user_id: Optional[str],
    organization_id: Optional[str],
    authorization: Optional[str],
    origin: str,
    details: Mapping[str, Any],
    *,
    client: ActivityClient | None = None,
) -> bool:
    """POST an event to the Activity API. Never raises; True on success."""
    active = _client_or_default(client)
    if active is None:
        return False
    return await active.send_activity(workspace_id, agent_id, user_id, organization_id,
                                      authorization, origin, details)


async def report_effort_excel_generated(
    request_ctx: RequestContext,
    sp_ref: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
    *,
    client: ActivityClient | None = None,
) -> bool:
    """
    Report that the effort Excel workbook (for review) has been generated.

    Called at the end of POST /pipeline/match/effort after the SharePoint upload.
    ``sp_ref`` is the dict from upload_output_to_sharepoint (its sp_file_id is the
    document key). ``extra`` adds fields to ``details``. Never raises.
    """
    active = _client_or_default(client)
    if active is None:
        return False
    return await active.report_effort_excel_generated(request_ctx, sp_ref, extra)


async def report_proposal_generated(
    request_ctx: RequestContext,
    sp_ref: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
    *,
    client: ActivityClient | None = None,
) -> bool:
    """
    Report that the final RFP Response document has been generated.

    Called at the end of POST /pipeline/generate/from-excel after the SharePoint
    upload. ``sp_ref`` is the dict for the generated DOCX. ``extra`` adds fields to
    ``details``. Never raises.
    """
    active = _client_or_default(client)
    if active is None:
        return False
    return await active.report_proposal_generated(request_ctx, sp_ref, extra)
