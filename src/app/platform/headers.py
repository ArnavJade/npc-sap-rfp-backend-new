"""
Platform Headers Extraction
============================
Ported verbatim from the old service (``src/models/headers.py``).

Extracts and validates platform headers (x-user-id, x-team-id, x-session-id,
x-agent-id, x-message-id) from incoming requests and merges them with
user_metadata with clear precedence rules.

Precedence:
- user_metadata values are AUTHORITATIVE (if present)
- Headers are FALLBACK (used only if user_metadata doesn't provide the value)
"""

from collections.abc import Mapping
from typing import Optional

from pydantic import BaseModel, Field


class PlatformHeaders(BaseModel):
    """
    Platform-level HTTP headers for request context.

    These headers provide an alternative way to pass platform context,
    typically set by the platform's API gateway or orchestration layer.

    Headers:
        x_user_id: User identifier from x-user-id header
        x_team_id: Team identifier from x-team-id header
        x_session_id: Session identifier from x-session-id header
        x_agent_id: Agent identifier from x-agent-id header
        x_message_id: Message identifier from x-message-id header

    Precedence:
        user_metadata values take precedence over headers.
        Headers are only used as fallback when user_metadata doesn't provide the value.
    """

    x_user_id: Optional[str] = Field(None, description="User ID from x-user-id header")
    x_team_id: Optional[str] = Field(None, description="Team ID from x-team-id header")
    x_session_id: Optional[str] = Field(None, description="Session ID from x-session-id header")
    x_agent_id: Optional[str] = Field(None, description="Agent ID from x-agent-id header")
    x_message_id: Optional[str] = Field(None, description="Message ID from x-message-id header")

    @classmethod
    def from_request_headers(cls, headers: Mapping[str, str]) -> "PlatformHeaders":
        """
        Extract platform headers from FastAPI request headers.

        Args:
            headers: FastAPI request.headers mapping (case-insensitive)

        Returns:
            PlatformHeaders instance with extracted values

        Note:
            FastAPI headers are case-insensitive, so 'x-user-id', 'X-User-Id',
            and 'X-USER-ID' are all equivalent. A plain dict is NOT
            case-insensitive: pass lower-case keys when using one.
        """
        return cls(
            x_user_id=headers.get("x-user-id"),
            x_team_id=headers.get("x-team-id"),
            x_session_id=headers.get("x-session-id"),
            x_agent_id=headers.get("x-agent-id"),
            x_message_id=headers.get("x-message-id"),
        )

    def has_any_headers(self) -> bool:
        """Check if any headers were provided."""
        return any([
            self.x_user_id,
            self.x_team_id,
            self.x_session_id,
            self.x_agent_id,
            self.x_message_id,
        ])

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        return self.model_dump(exclude_none=True)
