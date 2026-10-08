"""RequestContext / UserMetadata / PlatformHeaders parsing (ported contract + fixes)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.platform.headers import PlatformHeaders
from app.platform.request_context import RequestContext, UserMetadata, UserMetadataError

VALID_METADATA = {
    "team_id": "  c2d00988-team  ",
    "organization_id": "org-1",
    "message_id": "msg-1",
    "workspace_id": "ws-1",
    "session_id": "sess-1",
    "user_id": "user-1",
    "user_email": "presales@example.com",
    "company_name": "Acme Corp",
    "attachment_ids": ["att-1", "att-2"],
    "attachment_sharepoint_map": {
        "sp-ref-1": {"sp_item_id": "01I3ITEM", "sp_drive_id": "b!Y_rgDRIVE"},
        "sp-ref-2": {"sp_item_id": "01ABITEM", "sp_drive_id": "b!Y_rgDRIVE"},
    },
    "agent_ids": ["agent-1", "agent-2"],
    "sharepoint_enabled": True,
    "sp_drive_id": "b!Y_rgDRIVE",
    "sp_folder_id": "01I3FOLDER",
    "sp_folder_web_url": "https://tenant.sharepoint.com/sites/x/folder",
    "attachment_url_map": {"att-1": "s3://legacy/bucket/key"},  # legacy S3 key: ignored
}


def _ctx(metadata: dict | str, **kwargs) -> RequestContext:
    raw = metadata if isinstance(metadata, str) else json.dumps(metadata)
    return RequestContext.from_user_metadata_string(raw, **kwargs)


def test_valid_user_metadata_populates_context_and_getters():
    ctx = _ctx(VALID_METADATA, client_name="Acme", effort_sheet="SAP BP",
               instructions="Keep it short", authorization="Bearer jwt")

    assert ctx.get_team_id() == "c2d00988-team"  # stripped
    assert ctx.get_message_id() == "msg-1"
    assert ctx.get_user_id() == "user-1"
    assert ctx.get_organization_id() == "org-1"
    assert ctx.get_workspace_id() == "ws-1"
    assert ctx.get_session_id() == "sess-1"
    assert ctx.get_agent_id() == "agent-1"  # first of agent_ids
    assert ctx.get_authorization() == "Bearer jwt"
    assert ctx.company_name == "Acme Corp"
    assert ctx.user_email == "presales@example.com"
    assert (ctx.client_name, ctx.effort_sheet, ctx.instructions) == ("Acme", "SAP BP", "Keep it short")
    assert ctx.go_live_date is None

    assert ctx.get_attachment_ids() == ["att-1", "att-2"]
    assert ctx.get_sharepoint_attachments() == VALID_METADATA["attachment_sharepoint_map"]
    assert ctx.resolve_attachment_sharepoint("sp-ref-2") == {"sp_item_id": "01ABITEM", "sp_drive_id": "b!Y_rgDRIVE"}
    assert ctx.resolve_attachment_sharepoint("att-1") is None  # keys are not attachment_ids
    assert ctx.get_sharepoint_upload_target() == ("b!Y_rgDRIVE", "01I3FOLDER")
    assert ctx.is_sharepoint_enabled() is True
    assert ctx.get_sharepoint_context() == {
        "enabled": True,
        "drive_id": "b!Y_rgDRIVE",
        "folder_id": "01I3FOLDER",
        "folder_web_url": "https://tenant.sharepoint.com/sites/x/folder",
    }


def test_minimal_metadata_defaults():
    ctx = _ctx({"team_id": "t1"})
    assert ctx.get_sharepoint_attachments() == {}
    assert ctx.get_attachment_ids() == []
    assert ctx.get_sharepoint_upload_target() == (None, None)
    assert ctx.is_sharepoint_enabled() is False
    assert ctx.get_agent_id() is None
    assert ctx.get_authorization() is None


def test_legacy_s3_attachment_url_map_is_ignored():
    meta = UserMetadata.from_json_string(json.dumps(VALID_METADATA))
    assert "attachment_url_map" not in meta.to_dict()
    assert not hasattr(meta, "attachment_url_map")
    assert not hasattr(RequestContext, "resolve_attachment_url")


def test_headers_fill_only_missing_keys():
    headers = PlatformHeaders.from_request_headers(httpx.Headers({
        "X-User-Id": "hdr-user", "X-TEAM-ID": "hdr-team", "x-session-id": "hdr-sess",
        "X-Agent-Id": "hdr-agent", "X-Message-Id": "hdr-msg",
    }))
    assert headers.has_any_headers()
    assert headers.to_dict() == {"x_user_id": "hdr-user", "x_team_id": "hdr-team",
                                 "x_session_id": "hdr-sess", "x_agent_id": "hdr-agent",
                                 "x_message_id": "hdr-msg"}

    # Nothing in metadata -> every value comes from the headers
    ctx = _ctx({}, platform_headers=headers)
    assert (ctx.team_id, ctx.user_id, ctx.session_id, ctx.message_id, ctx.agent_id) == (
        "hdr-team", "hdr-user", "hdr-sess", "hdr-msg", "hdr-agent")

    # Metadata values are authoritative
    ctx = _ctx(VALID_METADATA, platform_headers=headers)
    assert (ctx.team_id, ctx.user_id, ctx.session_id, ctx.message_id, ctx.agent_id) == (
        "c2d00988-team", "user-1", "sess-1", "msg-1", "agent-1")


def test_empty_headers():
    headers = PlatformHeaders.from_request_headers({})
    assert not headers.has_any_headers()
    assert headers.to_dict() == {}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("{not json", "Invalid JSON in user_metadata"),
        ("", "Invalid JSON in user_metadata"),
        ("[]", "must be a JSON object"),
        ("null", "must be a JSON object"),
        ('"team"', "must be a JSON object"),
        ("{}", "Failed to create UserMetadata"),  # team_id missing
        ('{"team_id": "   "}', "team_id is required"),
        ('{"team_id": "t", "attachment_sharepoint_map": ["not", "a", "map"]}', "Failed to create UserMetadata"),
        ('{"team_id": "t", "agent_ids": "agent-1"}', "Failed to create UserMetadata"),
    ],
)
def test_invalid_user_metadata_raises_value_error(raw, message):
    with pytest.raises(UserMetadataError, match=message) as excinfo:
        _ctx(raw)
    assert isinstance(excinfo.value, ValueError)  # old routes: except ValueError -> HTTP 400


def test_header_team_id_does_not_override_blank_metadata_team_id():
    headers = PlatformHeaders(x_team_id="hdr-team")
    with pytest.raises(UserMetadataError, match="team_id is required"):
        _ctx({"team_id": ""}, platform_headers=headers)


def test_authorization_kept_out_of_logs():
    ctx = _ctx(VALID_METADATA, authorization="Bearer super-secret-jwt")
    assert "super-secret-jwt" not in repr(ctx)
    assert "authorization" not in ctx.to_dict()
    assert ctx.to_dict()["team_id"] == "c2d00988-team"


def test_round_trip_through_dict():
    ctx = _ctx(VALID_METADATA, client_name="Acme", authorization="Bearer jwt")
    again = RequestContext.model_validate(ctx.model_dump())
    assert again == ctx
    assert again.get_agent_id() == "agent-1"


def test_explicit_core_fields_win_over_user_metadata():
    meta = UserMetadata(team_id="t1", workspace_id="ws-meta", agent_ids=["a1"])
    ctx = RequestContext(user_metadata=meta, workspace_id="ws-explicit", agent_id="a-explicit")
    assert ctx.workspace_id == "ws-explicit"
    assert ctx.agent_id == "a-explicit"
    assert ctx.team_id == "t1"
