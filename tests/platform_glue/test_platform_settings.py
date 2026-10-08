"""Env-driven SharePoint / Activity configuration."""

from __future__ import annotations

from app.platform.settings import (
    ActivityConfig,
    SharePointConfig,
    load_activity_config,
    load_sharepoint_config,
)

SP_ENV = {
    "AZ_TENANT_ID": "tenant-guid",
    "AZ_CLIENT_ID": "client-guid",
    "AZ_CLIENT_SECRET": "very-secret",
    "AZ_SHAREPOINT_HOSTNAME": "tenant.sharepoint.com",
    "AZ_SHAREPOINT_SITE_PATH": "/sites/presales",
    "SHAREPOINT_ROOT_FOLDER": "/rfp-agent/dev/",
}


def test_sharepoint_config_from_env():
    cfg = SharePointConfig.from_env(SP_ENV)
    assert cfg.configured
    assert cfg.missing == []
    assert cfg.hostname == "tenant.sharepoint.com"
    assert cfg.site_path == "/sites/presales"
    assert cfg.root_folder == "rfp-agent/dev"
    assert cfg.authority == "https://login.microsoftonline.com/tenant-guid"
    assert "very-secret" not in repr(cfg)


def test_sharepoint_config_missing_credentials():
    cfg = SharePointConfig.from_env({"AZ_TENANT_ID": "t", "AZ_CLIENT_SECRET": "  "})
    assert not cfg.configured
    assert cfg.missing == ["AZ_CLIENT_ID", "AZ_CLIENT_SECRET"]
    assert not SharePointConfig().configured


def test_sharepoint_site_settings_not_required_for_item_calls():
    env = {k: v for k, v in SP_ENV.items() if k.startswith(("AZ_TENANT", "AZ_CLIENT"))}
    assert SharePointConfig.from_env(env).configured


def test_load_sharepoint_config_reads_os_environ_at_call_time(monkeypatch):
    for key in SP_ENV:
        monkeypatch.delenv(key, raising=False)
    assert not load_sharepoint_config().configured
    for key, value in SP_ENV.items():
        monkeypatch.setenv(key, value)
    assert load_sharepoint_config().configured


def test_activity_config_defaults_and_disabled():
    cfg = ActivityConfig.from_env({})
    assert (cfg.base_url, cfg.max_retries, cfg.timeout) == ("", 3, 5.0)
    assert not cfg.configured


def test_activity_config_from_env():
    cfg = ActivityConfig.from_env({
        "ACTIVITY_API_BASE_URL": " https://activity.example.com/ ",
        "ACTIVITY_API_MAX_RETRIES": "5",
        "ACTIVITY_API_TIMEOUT": "2.5",
    })
    assert cfg.configured
    assert (cfg.base_url, cfg.max_retries, cfg.timeout) == ("https://activity.example.com", 5, 2.5)


def test_activity_config_invalid_numbers_fall_back():
    cfg = ActivityConfig.from_env({
        "ACTIVITY_API_BASE_URL": "https://a",
        "ACTIVITY_API_MAX_RETRIES": "many",
        "ACTIVITY_API_TIMEOUT": "soon",
    })
    assert (cfg.max_retries, cfg.timeout) == (3, 5.0)
    assert ActivityConfig(base_url="x", max_retries=0, timeout=-1).max_retries == 1
    assert ActivityConfig(base_url="x", max_retries=0, timeout=-1).timeout == 5.0


def test_load_activity_config_reads_os_environ(monkeypatch):
    monkeypatch.setenv("ACTIVITY_API_BASE_URL", "https://activity.example.com")
    monkeypatch.delenv("ACTIVITY_API_MAX_RETRIES", raising=False)
    assert load_activity_config().configured
    monkeypatch.setenv("ACTIVITY_API_BASE_URL", "")
    assert not load_activity_config().configured
