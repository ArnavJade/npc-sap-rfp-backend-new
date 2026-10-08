"""Repository-relative locations of knowledge and data (overridable for tests/deployments)."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _dir(env: str, default: Path) -> Path:
    value = os.getenv(env)
    if not value:
        return default
    p = Path(value).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


def assets_dir() -> Path:
    return _dir("ASSETS_DIR", PROJECT_ROOT / "assets")


def policy_dir() -> Path:
    return _dir("POLICY_DIR", PROJECT_ROOT / "policy")


def skills_dir() -> Path:
    return _dir("SKILLS_DIR", PROJECT_ROOT / "skills")


def workspace_dir() -> Path:
    return _dir("WORKSPACE_DIR", PROJECT_ROOT / "workspace")


def catalogue_dir() -> Path:
    return assets_dir() / "catalogue"


def templates_dir() -> Path:
    return assets_dir() / "templates"


def rate_card_path() -> Path:
    return policy_dir() / "rate_cards" / "bp_efforts.parquet"
