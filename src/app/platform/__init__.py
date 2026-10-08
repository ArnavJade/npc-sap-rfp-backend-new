"""Platform glue for the two public routes, ported from the old FastAPI service.

- ``headers`` / ``request_context``: platform headers + ``user_metadata`` -> RequestContext
- ``sharepoint``: download attachments / upload outputs via Microsoft Graph (app-only)
- ``activity``: Activity API events (never raises; no-op when unconfigured)
- ``settings``: env-driven SharePoint / Activity configuration

S3, KMS and the per-team LLM-config database are intentionally not ported: the
PoC configures models via env/LiteLLM.
"""

from .activity import (
    ActivityClient,
    report_effort_excel_generated,
    report_proposal_generated,
    send_activity,
)
from .headers import PlatformHeaders
from .request_context import RequestContext, UserMetadata, UserMetadataError
from .settings import (
    ActivityConfig,
    SharePointConfig,
    load_activity_config,
    load_sharepoint_config,
)
from .sharepoint import (
    MsalTokenProvider,
    SharePointAuthError,
    SharePointClient,
    SharePointError,
    SharePointHTTPError,
    SharePointNotConfiguredError,
    TokenProvider,
    download_attachment_from_sharepoint,
    upload_output_to_sharepoint,
)

__all__ = [
    "ActivityClient",
    "ActivityConfig",
    "MsalTokenProvider",
    "PlatformHeaders",
    "RequestContext",
    "SharePointAuthError",
    "SharePointClient",
    "SharePointConfig",
    "SharePointError",
    "SharePointHTTPError",
    "SharePointNotConfiguredError",
    "TokenProvider",
    "UserMetadata",
    "UserMetadataError",
    "download_attachment_from_sharepoint",
    "load_activity_config",
    "load_sharepoint_config",
    "report_effort_excel_generated",
    "report_proposal_generated",
    "send_activity",
    "upload_output_to_sharepoint",
]
