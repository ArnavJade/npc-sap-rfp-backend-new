"""Environment-driven configuration for the platform glue (SharePoint + Activity API).

Ported from the SharePoint / Activity parts of the old ``config/settings.py``. The
old module read the environment once at import time and raised if SharePoint was
not configured. Here each ``load_*`` call reads ``os.environ`` (or a mapping you
pass in) at call time and never raises. Callers check the ``configured``
property. Load ``.env`` (python-dotenv) at app start-up, before the first call.

Variables (see ``.env.example``):
    AZ_TENANT_ID, AZ_CLIENT_ID, AZ_CLIENT_SECRET   app-only Graph credentials
    AZ_SHAREPOINT_HOSTNAME, AZ_SHAREPOINT_SITE_PATH site coordinates (kept for parity;
                                                    not needed by the drive/item calls)
    SHAREPOINT_ROOT_FOLDER                          workspace parent folder (parity)
    ACTIVITY_API_BASE_URL                           empty -> activity reporting disabled
    ACTIVITY_API_MAX_RETRIES (default 3), ACTIVITY_API_TIMEOUT (seconds, default 5)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_ACTIVITY_MAX_RETRIES = 3
DEFAULT_ACTIVITY_TIMEOUT = 5.0

# Credentials needed for an app-only Microsoft Graph token.
_SHAREPOINT_REQUIRED_ENV = {
    "tenant_id": "AZ_TENANT_ID",
    "client_id": "AZ_CLIENT_ID",
    "client_secret": "AZ_CLIENT_SECRET",
}


@dataclass(frozen=True)
class SharePointConfig:
    """Azure AD app + SharePoint site configuration (Microsoft Graph, app-only auth)."""

    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    hostname: str = ""
    site_path: str = ""
    root_folder: str = ""

    @property
    def configured(self) -> bool:
        """True when the app-only Graph credentials are all set.

        Downloads and uploads address items by explicit (drive_id, item/folder id),
        so the site hostname/path are not required for them.
        """
        return not self.missing

    @property
    def missing(self) -> list[str]:
        """Names of the required env variables that are empty."""
        return [env for attr, env in _SHAREPOINT_REQUIRED_ENV.items() if not getattr(self, attr)]

    @property
    def authority(self) -> str:
        """Entra ID authority URL for this tenant."""
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> SharePointConfig:
        """Build from environment variables (``os.environ`` by default)."""
        env = os.environ if env is None else env
        return cls(
            tenant_id=_str(env, "AZ_TENANT_ID"),
            client_id=_str(env, "AZ_CLIENT_ID"),
            client_secret=_str(env, "AZ_CLIENT_SECRET"),
            hostname=_str(env, "AZ_SHAREPOINT_HOSTNAME"),
            site_path=_str(env, "AZ_SHAREPOINT_SITE_PATH"),
            root_folder=_str(env, "SHAREPOINT_ROOT_FOLDER").strip("/"),
        )


@dataclass(frozen=True)
class ActivityConfig:
    """Platform Activity API configuration. An empty base URL disables reporting."""

    base_url: str = ""
    max_retries: int = DEFAULT_ACTIVITY_MAX_RETRIES
    timeout: float = DEFAULT_ACTIVITY_TIMEOUT

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", (self.base_url or "").strip().rstrip("/"))
        object.__setattr__(self, "max_retries", max(1, int(self.max_retries)))
        if not self.timeout or self.timeout <= 0:
            object.__setattr__(self, "timeout", DEFAULT_ACTIVITY_TIMEOUT)

    @property
    def configured(self) -> bool:
        """True when ACTIVITY_API_BASE_URL is set."""
        return bool(self.base_url)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ActivityConfig:
        """Build from environment variables (``os.environ`` by default).

        Invalid numbers fall back to the defaults with a warning instead of raising.
        """
        env = os.environ if env is None else env
        return cls(
            base_url=_str(env, "ACTIVITY_API_BASE_URL"),
            max_retries=_int(env, "ACTIVITY_API_MAX_RETRIES", DEFAULT_ACTIVITY_MAX_RETRIES),
            timeout=_float(env, "ACTIVITY_API_TIMEOUT", DEFAULT_ACTIVITY_TIMEOUT),
        )


def load_sharepoint_config(env: Mapping[str, str] | None = None) -> SharePointConfig:
    """Read the SharePoint configuration from the environment (at call time)."""
    return SharePointConfig.from_env(env)


def load_activity_config(env: Mapping[str, str] | None = None) -> ActivityConfig:
    """Read the Activity API configuration from the environment (at call time)."""
    return ActivityConfig.from_env(env)


def _str(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = _str(env, name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = _str(env, name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default
