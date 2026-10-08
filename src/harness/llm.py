"""Model access for every agent, through LiteLLM (no vendor lock-in: Gemini, Claude on Bedrock, ...).

Resolution per role, first hit wins:
  1. the run's override (the model the user picked for this job in the UI/API)
  2. env LLM_MODEL_<ROLE>             e.g. LLM_MODEL_WRITER=bedrock/<profile-id>
  3. policy/runtime.yaml models.roles.<role>.model
  4. env LLM_MODEL                    the default for everything

Tests (and offline demos) replace the whole factory with `set_model_factory`.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter

from bidcore.policy import get_policy

log = logging.getLogger(__name__)

ModelFactory = Callable[[str, str], BaseChatModel]   # (role, agent_name) -> model

_factory: ModelFactory | None = None
_limiter: InMemoryRateLimiter | None = None
_disabled_gp_for: set[str] = set()
_lock = threading.Lock()


class ModelNotConfigured(RuntimeError):
    """No model string resolved for a role: the job fails fast with this message."""


def set_model_factory(factory: ModelFactory | None) -> None:
    """Install (or with None, remove) a factory used instead of LiteLLM - tests and offline demos."""
    global _factory
    _factory = factory


def resolve_model_name(role: str, run_model: str | None = None) -> str:
    if run_model:
        return run_model.strip()
    env = os.getenv(f"LLM_MODEL_{role.upper()}", "").strip()
    if env:
        return env
    roles = get_policy().runtime.models.get("roles", {}) or {}
    configured = str((roles.get(role) or {}).get("model") or "").strip()
    return configured or os.getenv("LLM_MODEL", "").strip()


def models_in_use(run_model: str | None = None) -> dict[str, str]:
    roles = get_policy().runtime.models.get("roles", {}) or {}
    return {role: (resolve_model_name(role, run_model) or "(not configured)") for role in roles}


def _rate_limiter() -> InMemoryRateLimiter:
    global _limiter
    with _lock:
        if _limiter is None:
            rps = float(get_policy().runtime.limits.get("model_requests_per_second", 4) or 4)
            _limiter = InMemoryRateLimiter(requests_per_second=rps, check_every_n_seconds=0.05,
                                           max_bucket_size=max(1, int(rps)))
        return _limiter


def disable_general_purpose_subagent(model: BaseChatModel) -> None:
    """Our orchestrators may only delegate to the specialists we define, never to Deep Agents'
    built-in general-purpose subagent, so switch it off for this model's provider (idempotent)."""
    from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, register_harness_profile
    from deepagents._models import get_model_provider

    provider = get_model_provider(model) or type(model).__name__.lower()
    with _lock:
        if provider in _disabled_gp_for:
            return
        register_harness_profile(provider, HarnessProfile(
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
        _disabled_gp_for.add(provider)


_SAFE_CLASSES: dict[type, type] = {}


def _schema_safe_class(base: type) -> type:
    """`base` with bind_tools sending provider-safe schemas (see harness.tool_schema)."""
    if base not in _SAFE_CLASSES:
        from harness.tool_schema import safe_tools

        def bind_tools(self, tools, tool_choice=None, **kwargs):
            return base.bind_tools(self, safe_tools(list(tools)), tool_choice=tool_choice, **kwargs)

        _SAFE_CLASSES[base] = type(f"SchemaSafe{base.__name__}", (base,), {"bind_tools": bind_tools})
    return _SAFE_CLASSES[base]


def chat_model(role: str, agent: str = "", run_model: str | None = None) -> BaseChatModel:
    """The chat model for one agent. Raises ModelNotConfigured when nothing resolves."""
    if _factory is not None:
        model = _factory(role, agent)
        disable_general_purpose_subagent(model)
        return model
    name = resolve_model_name(role, run_model)
    if not name:
        raise ModelNotConfigured(
            f"No model configured for role '{role}'. Set LLM_MODEL (a LiteLLM model string such as "
            "'gemini/gemini-3.8-flash' or 'bedrock/<model-id>') in .env, or choose a model for the run.")
    from langchain_litellm import ChatLiteLLM

    settings = get_policy().runtime.models
    role_cfg = (settings.get("roles", {}) or {}).get(role) or {}
    kwargs: dict[str, Any] = {
        "model": name,
        "max_tokens": int(role_cfg.get("max_tokens") or settings.get("max_tokens") or 16000),
        "request_timeout": float(settings.get("request_timeout_seconds") or 300),
        "max_retries": 3,
        "rate_limiter": _rate_limiter(),
    }
    temperature = role_cfg.get("temperature", settings.get("temperature"))
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    model = _schema_safe_class(ChatLiteLLM)(**kwargs)
    disable_general_purpose_subagent(model)
    log.debug("model for %s/%s -> %s", role, agent, name)
    return model
