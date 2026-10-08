"""
Request Context Models
=======================
Ported from the old service (``src/models/request_context.py``).

``user_metadata`` is the JSON string the platform posts (as a Form field) to the
two public routes. It carries the platform context the service needs for:

- SharePoint input: ``attachment_sharepoint_map`` = ``{<key>: {sp_item_id, sp_drive_id}}``
  (the source of truth for input files; its keys are opaque and are NOT
  ``attachment_ids``)
- SharePoint output: ``sp_drive_id`` + ``sp_folder_id`` (upload target)
- Activity API reporting: ``workspace_id``, ``organization_id``, ``user_id``,
  ``agent_ids``, ``company_name``
- Request tracing: ``team_id``, ``message_id``, ``session_id``

Platform headers (x-user-id, x-team-id, ...) are a fallback: user_metadata
values are authoritative, headers only fill keys that are absent.

Port changes:
- The legacy S3 ``attachment_url_map`` field and its resolvers are dropped (no S3
  in this service). The key is still accepted in the JSON and ignored, like any
  other unknown key.
- Model configuration no longer depends on ``team_id`` (models come from
  env/LiteLLM). ``team_id`` stays required so the platform contract is unchanged.
- A ``user_metadata`` that is valid JSON but not an object is rejected with a
  ValueError (the old code could raise a TypeError there).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .headers import PlatformHeaders


class UserMetadataError(ValueError):
    """``user_metadata`` is not valid JSON, not an object, or fails validation."""


class UserMetadata(BaseModel):
    """
    Platform-level request context metadata (parsed ``user_metadata``).

    Fields:
        team_id: Team identifier (required by the platform contract)
        organization_id: Organization identifier (Activity API ``organization-id`` header)
        message_id: Unique message/request identifier for tracing
        workspace_id: Workspace identifier (Activity API path segment)
        session_id: Conversation session identifier
        user_id: User identifier who initiated the request
        user_email: Email of the requesting user
        company_name: Company display name (Activity API ``group_name``)
        attachment_ids: List of attachment identifiers from the request
        file_hashes: List of file content hashes for deduplication
        attachment_sharepoint_map: ``{key: {sp_item_id, sp_drive_id}}`` input files
        agent_ids: List of agent identifiers involved in processing
        sharepoint_enabled: Whether SharePoint integration is enabled
        sp_drive_id: SharePoint drive identifier for output storage
        sp_folder_id: SharePoint folder identifier for output storage
        sp_folder_web_url: SharePoint folder web URL for user access
    """

    # Core identifiers
    team_id: str = Field(..., description="Team identifier (platform contract)")
    organization_id: Optional[str] = Field(None, description="Organization identifier")
    message_id: Optional[str] = Field(None, description="Unique message/request identifier")

    # Workspace and session context
    workspace_id: Optional[str] = Field(None, description="Workspace identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    user_email: Optional[str] = Field(None, description="Email of the requesting user")
    company_name: Optional[str] = Field(None, description="Company / organization display name")

    # File and attachment tracking
    attachment_ids: Optional[list[str]] = Field(None, description="List of attachment identifiers")
    file_hashes: Optional[list[str]] = Field(None, description="List of file content hashes")

    # SharePoint attachment resolution map. Maps each key to the Graph
    # coordinates needed to download it:
    #   { "<key>": {"sp_item_id": "...", "sp_drive_id": "..."} }
    attachment_sharepoint_map: Optional[dict[str, dict[str, str]]] = Field(
        None,
        description=(
            "Map of key -> {sp_item_id, sp_drive_id} for downloading "
            "each attachment from SharePoint via Microsoft Graph"
        ),
    )

    # Agent context
    agent_ids: Optional[list[str]] = Field(None, description="List of agent identifiers")

    # SharePoint integration
    sharepoint_enabled: Optional[bool] = Field(False, description="SharePoint integration enabled")
    sp_drive_id: Optional[str] = Field(None, description="SharePoint drive id for output upload")
    sp_folder_id: Optional[str] = Field(None, description="SharePoint folder id for output upload")
    sp_folder_web_url: Optional[str] = Field(None, description="SharePoint folder web URL")

    @field_validator("team_id")
    @classmethod
    def validate_team_id(cls, v: str) -> str:
        """Validate that team_id is not empty."""
        if not v or not v.strip():
            raise ValueError("team_id is required and cannot be empty")
        return v.strip()

    @classmethod
    def from_json_string(
        cls,
        json_str: str,
        platform_headers: Optional[PlatformHeaders] = None,
    ) -> UserMetadata:
        """
        Parse user_metadata from a JSON string and merge with platform headers.

        Precedence:
        - user_metadata values are AUTHORITATIVE (if the key is present in JSON)
        - Headers are FALLBACK (used only if JSON doesn't provide the key)

        Raises:
            UserMetadataError (a ValueError): invalid JSON, not a JSON object,
                or required fields missing/invalid.
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise UserMetadataError(f"Invalid JSON in user_metadata: {e}") from e
        except Exception as e:
            raise UserMetadataError(f"Failed to parse user_metadata: {e}") from e

        if not isinstance(data, dict):
            raise UserMetadataError(
                f"user_metadata must be a JSON object, got {type(data).__name__}"
            )

        if platform_headers:
            # Only use header values if not present in user_metadata
            if "user_id" not in data and platform_headers.x_user_id:
                data["user_id"] = platform_headers.x_user_id

            if "team_id" not in data and platform_headers.x_team_id:
                data["team_id"] = platform_headers.x_team_id

            if "session_id" not in data and platform_headers.x_session_id:
                data["session_id"] = platform_headers.x_session_id

            if "message_id" not in data and platform_headers.x_message_id:
                data["message_id"] = platform_headers.x_message_id

            # Header provides a single agent_id; metadata can carry a list
            if "agent_ids" not in data and platform_headers.x_agent_id:
                data["agent_ids"] = [platform_headers.x_agent_id]

        try:
            return cls(**data)
        except Exception as e:
            raise UserMetadataError(f"Failed to create UserMetadata: {e}") from e

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        return self.model_dump(exclude_none=True)

    def to_json_string(self) -> str:
        """Convert to JSON string."""
        return self.model_dump_json(exclude_none=True)

    def resolve_attachment_sharepoint(self, attachment_id: str) -> Optional[dict[str, str]]:
        """Return ``{"sp_item_id": ..., "sp_drive_id": ...}`` for a key, or None if not mapped."""
        if not self.attachment_sharepoint_map:
            return None
        return self.attachment_sharepoint_map.get(attachment_id)


# Core fields copied from UserMetadata onto RequestContext when not given explicitly.
_CORE_FIELDS = (
    "team_id",
    "organization_id",
    "workspace_id",
    "session_id",
    "message_id",
    "user_id",
    "user_email",
    "company_name",
)


class RequestContext(BaseModel):
    """
    Request context: parsed user_metadata plus request-specific inputs.

    Core fields are copied from ``user_metadata`` for easy access unless passed
    explicitly; ``agent_id`` is the first entry of ``user_metadata.agent_ids``.

    Request-specific fields as used by the two public routes:
        client_name: Form field on both routes (output file names, document)
        effort_sheet: Rate card sheet; the effort route sets "SAP BP"
        instructions: Free-text RFP-manager instructions (proposal route)
        go_live_date: Optional go-live target
        authorization: Incoming Authorization header, forwarded to the Activity API
    """

    user_metadata: UserMetadata

    # Request-specific context
    client_name: Optional[str] = Field(None, description="Client name from request")
    effort_sheet: Optional[str] = Field(None, description="Effort sheet selection")
    go_live_date: Optional[str] = Field(None, description="Project go-live date")
    instructions: Optional[str] = Field(None, description="Custom instructions")

    # Core context fields (extracted for easy access)
    team_id: str = Field(..., description="Team identifier (from user_metadata)")
    organization_id: Optional[str] = Field(None, description="Organization identifier")
    workspace_id: Optional[str] = Field(None, description="Workspace identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    message_id: Optional[str] = Field(None, description="Message identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    user_email: Optional[str] = Field(None, description="User email")
    company_name: Optional[str] = Field(None, description="Company / organization display name")
    agent_id: Optional[str] = Field(None, description="Primary agent identifier")
    authorization: Optional[str] = Field(None, description="Authorization token", repr=False)

    @model_validator(mode="before")
    @classmethod
    def _extract_core_fields(cls, data: Any) -> Any:
        """Copy core fields from user_metadata unless they were passed explicitly."""
        if not isinstance(data, dict):
            return data
        user_meta = data.get("user_metadata")
        if isinstance(user_meta, dict):
            user_meta = UserMetadata.model_validate(user_meta)
        if not isinstance(user_meta, UserMetadata):
            return data

        data = {**data, "user_metadata": user_meta}
        for name in _CORE_FIELDS:
            if name not in data:
                data[name] = getattr(user_meta, name)
        # Primary agent_id from the agent_ids list
        if "agent_id" not in data and user_meta.agent_ids:
            data["agent_id"] = user_meta.agent_ids[0]
        return data

    @classmethod
    def from_user_metadata_string(
        cls,
        user_metadata_json: str,
        platform_headers: Optional[PlatformHeaders] = None,
        client_name: Optional[str] = None,
        effort_sheet: Optional[str] = None,
        go_live_date: Optional[str] = None,
        instructions: Optional[str] = None,
        authorization: Optional[str] = None,
    ) -> RequestContext:
        """
        Create a RequestContext from the user_metadata JSON string and route inputs.

        Raises:
            UserMetadataError (a ValueError) if user_metadata is invalid. The old
            routes mapped ``ValueError`` to HTTP 400 and pydantic
            ``ValidationError`` to 422.
        """
        user_meta = UserMetadata.from_json_string(
            user_metadata_json,
            platform_headers=platform_headers,
        )
        return cls(
            user_metadata=user_meta,
            client_name=client_name,
            effort_sheet=effort_sheet,
            go_live_date=go_live_date,
            instructions=instructions,
            authorization=authorization,
        )

    # ------------------------------------------------------------------
    # Getters (same surface as the old service)
    # ------------------------------------------------------------------

    def get_team_id(self) -> str:
        """Get team_id."""
        return self.team_id

    def get_message_id(self) -> Optional[str]:
        """Get message_id for request tracing."""
        return self.message_id

    def get_user_id(self) -> Optional[str]:
        """Get user_id for audit logging."""
        return self.user_id

    def get_organization_id(self) -> Optional[str]:
        """Get organization_id for multi-tenancy."""
        return self.organization_id

    def get_workspace_id(self) -> Optional[str]:
        """Get workspace_id for file isolation."""
        return self.workspace_id

    def get_session_id(self) -> Optional[str]:
        """Get session_id for conversation tracking."""
        return self.session_id

    def get_agent_id(self) -> Optional[str]:
        """Get primary agent_id."""
        return self.agent_id

    def get_authorization(self) -> Optional[str]:
        """Get authorization token."""
        return self.authorization

    # ------------------------------------------------------------------
    # Attachments / SharePoint
    # ------------------------------------------------------------------

    def get_attachment_ids(self) -> list[str]:
        """Return attachment_ids from user_metadata (empty list if unset)."""
        return self.user_metadata.attachment_ids or []

    def resolve_attachment_sharepoint(self, attachment_id: str) -> Optional[dict[str, str]]:
        """Resolve a single key to its ``{sp_item_id, sp_drive_id}`` coords."""
        return self.user_metadata.resolve_attachment_sharepoint(attachment_id)

    def get_sharepoint_attachments(self) -> dict[str, dict[str, str]]:
        """
        Return the full attachment_sharepoint_map: ``{key: {sp_item_id, sp_drive_id}}``.

        This is the source of truth for input files. Its keys are opaque
        SharePoint reference ids and are NOT the same as attachment_ids.
        """
        return self.user_metadata.attachment_sharepoint_map or {}

    def is_sharepoint_enabled(self) -> bool:
        """Check if SharePoint integration is enabled."""
        return self.user_metadata.sharepoint_enabled or False

    def get_sharepoint_upload_target(self) -> tuple[Optional[str], Optional[str]]:
        """Return (sp_drive_id, sp_folder_id) for uploading generated outputs."""
        return self.user_metadata.sp_drive_id, self.user_metadata.sp_folder_id

    def get_sharepoint_context(self) -> dict:
        """Get SharePoint context for file operations."""
        return {
            "enabled": self.is_sharepoint_enabled(),
            "drive_id": self.user_metadata.sp_drive_id,
            "folder_id": self.user_metadata.sp_folder_id,
            "folder_web_url": self.user_metadata.sp_folder_web_url,
        }

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/debugging (no authorization token)."""
        return {
            "team_id": self.team_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "client_name": self.client_name,
            "effort_sheet": self.effort_sheet,
        }
