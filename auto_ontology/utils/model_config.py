# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Which provider and model serves each model role, resolved at call time.

There are four roles (:class:`~auto_ontology.dal.schema.ModelRole`):

* ``chat`` -- the main model: text-to-SQL, semantic compilation, descriptions.
* ``fast_chat`` -- a cheaper model for entity extraction, follow-up rewriting
  and charts. Falls back to ``chat`` when it is not set.
* ``embedding`` -- turns catalog and glossary text into vectors.
* ``rerank`` -- optional; orders candidates in bridge-table detection.

A role is resolved, in order, from:

1. its row in ``model_setting``, written by Settings -> Models in the UI;
2. environment variables ``<PREFIX>_PROVIDER`` / ``_MODEL`` / ``_ENDPOINT`` /
   ``_API_KEY`` (``<PREFIX>`` is ``REASONING``, ``NON_REASONING``, ``EMBED`` or
   ``RERANK``), each falling back to ``DEFAULT_MODELS_<FIELD>``;
3. nothing -- the role is unconfigured and callers say so.

Results are cached for a few seconds per process, so a change saved in the UI
reaches every service (backend, chat workers, ingestion) without a restart.
The backend also drops its cache the moment a setting is saved.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field

from auto_ontology.dal.schema import ModelProvider, ModelRole

logger = logging.getLogger(__name__)

#: How long a resolved role is reused before the database is read again.
CACHE_TTL_S = 10.0

#: Environment-variable prefix for each role.
ENV_PREFIX: dict[ModelRole, str] = {
    ModelRole.CHAT: "REASONING",
    ModelRole.FAST_CHAT: "NON_REASONING",
    ModelRole.EMBEDDING: "EMBED",
    ModelRole.RERANK: "RERANK",
}

#: The providers each role may use.
ROLE_PROVIDERS: dict[ModelRole, tuple[ModelProvider, ...]] = {
    ModelRole.CHAT: (
        ModelProvider.OPENAI,
        ModelProvider.ANTHROPIC,
        ModelProvider.NVIDIA,
        ModelProvider.OPENAI_COMPATIBLE,
    ),
    ModelRole.FAST_CHAT: (
        ModelProvider.OPENAI,
        ModelProvider.ANTHROPIC,
        ModelProvider.NVIDIA,
        ModelProvider.OPENAI_COMPATIBLE,
    ),
    ModelRole.EMBEDDING: (
        ModelProvider.OPENAI,
        ModelProvider.NVIDIA,
        ModelProvider.OPENAI_COMPATIBLE,
    ),
    ModelRole.RERANK: (
        ModelProvider.NVIDIA,
        ModelProvider.RERANK_API,
        ModelProvider.NONE,
    ),
}

#: The NVIDIA NIM model each role starts on until something else is saved. The
#: upstream project's chat default (nemotron-3-nano-30b-a3b) was retired on
#: 2026-09-01, so chat and fast chat use its live successors; embeddings and
#: reranking are upstream's. Only the API key is missing.
NVIDIA_DEFAULT_MODEL: dict[ModelRole, str] = {
    ModelRole.CHAT: "nvidia/nemotron-3-super-120b-a12b",
    ModelRole.FAST_CHAT: "nvidia/nemotron-3.5-lightning-30b-a3b",
    ModelRole.EMBEDDING: "nvidia/nemotron-3-embed-1b",
    ModelRole.RERANK: "nvidia/llama-nemotron-rerank-vl-1b-v2",
}

#: NVIDIA serves reranking from its own host, one path per model.
NVIDIA_RERANK_BASE_URL = "https://ai.api.nvidia.com/v1/retrieval"

#: Endpoint used when a setting leaves ``base_url`` empty.
DEFAULT_BASE_URL: dict[ModelProvider, str] = {
    ModelProvider.OPENAI: "https://api.openai.com/v1",
    ModelProvider.ANTHROPIC: "https://api.anthropic.com",
    ModelProvider.NVIDIA: "https://integrate.api.nvidia.com/v1",
}

#: Providers that refuse a request without a key. The others may be keyless
#: (a local Ollama or vLLM, for instance).
KEY_REQUIRED: frozenset[ModelProvider] = frozenset(
    {ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.NVIDIA}
)


class ModelNotConfiguredError(EnvironmentError):
    """A role has no usable provider and model. The message says how to fix it."""


@dataclass(frozen=True)
class ResolvedModel:
    """A role's effective configuration. The key stays out of ``repr``."""

    role: ModelRole
    provider: ModelProvider
    model: str
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    dimensions: int | None = None
    #: ``settings``, ``environment``, ``chat`` (fast_chat borrowing chat) or ``unset``.
    source: str = "unset"

    @property
    def endpoint(self) -> str:
        """``base_url``, or the provider's default when it is empty."""
        if self.base_url:
            return self.base_url
        if self.provider == ModelProvider.NVIDIA and self.role == ModelRole.RERANK:
            if not self.model:
                return ""
            return f"{NVIDIA_RERANK_BASE_URL}/{self.model}/reranking"
        return DEFAULT_BASE_URL.get(self.provider, "")

    @property
    def configured(self) -> bool:
        if self.provider == ModelProvider.NONE or not self.model:
            return False
        if self.provider in KEY_REQUIRED and not self.api_key:
            return False
        if self.provider in (ModelProvider.OPENAI_COMPATIBLE, ModelProvider.RERANK_API):
            return bool(self.base_url)
        return True

    def require(self) -> ResolvedModel:
        """Return self, or raise :class:`ModelNotConfiguredError`."""
        if not self.configured:
            raise ModelNotConfiguredError(
                f"No {self.role.value.replace('_', ' ')} model is configured. "
                "Choose one under Settings -> Models."
            )
        return self


# ---------------------------------------------------------------------------
# Environment fallback
# ---------------------------------------------------------------------------


def _env(prefix: str, name: str) -> str:
    return (
        os.environ.get(f"{prefix}_{name}", "")
        or os.environ.get(f"DEFAULT_MODELS_{name}", "")
    ).strip()


def _infer_provider(role: ModelRole, endpoint: str) -> ModelProvider:
    if role == ModelRole.RERANK:
        return ModelProvider.RERANK_API if endpoint else ModelProvider.NONE
    if "anthropic.com" in endpoint:
        return ModelProvider.ANTHROPIC
    if "nvidia.com" in endpoint:
        return ModelProvider.NVIDIA
    if not endpoint or "api.openai.com" in endpoint:
        return ModelProvider.OPENAI
    return ModelProvider.OPENAI_COMPATIBLE


def _from_env(role: ModelRole) -> ResolvedModel | None:
    prefix = ENV_PREFIX[role]
    # The rerank role reads only its own variables: DEFAULT_MODELS_* names a
    # chat endpoint, which is never a rerank endpoint.
    if role == ModelRole.RERANK:
        endpoint = os.environ.get("RERANK_ENDPOINT", "").strip()
        model = os.environ.get("RERANK_MODEL", "").strip()
        api_key = os.environ.get("RERANK_API_KEY", "").strip()
        provider_name = os.environ.get("RERANK_PROVIDER", "").strip()
    else:
        endpoint = _env(prefix, "ENDPOINT")
        model = _env(prefix, "MODEL")
        api_key = _env(prefix, "API_KEY")
        provider_name = _env(prefix, "PROVIDER")
    if not (endpoint or model or api_key or provider_name):
        return None
    try:
        provider = (
            ModelProvider(provider_name)
            if provider_name
            else _infer_provider(role, endpoint)
        )
    except ValueError:
        logger.warning("%s_PROVIDER=%r is not a known provider", prefix, provider_name)
        return None
    dimensions = os.environ.get("EMBED_DIMENSIONS", "").strip()
    return ResolvedModel(
        role=role,
        provider=provider,
        model=model,
        base_url=endpoint,
        api_key=api_key,
        dimensions=int(dimensions)
        if role == ModelRole.EMBEDDING and dimensions.isdigit()
        else None,
        source="environment",
    )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def _from_row(row: dict) -> ResolvedModel:
    from auto_ontology.infra.secrets import decrypt_secret

    return ResolvedModel(
        role=ModelRole(row["role"]),
        provider=ModelProvider(row["provider"]),
        model=row.get("model") or "",
        base_url=row.get("base_url") or "",
        api_key=decrypt_secret(row.get("api_key") or "") or "",
        dimensions=row.get("dimensions"),
        source="settings",
    )


def _from_db(role: ModelRole) -> ResolvedModel | None:
    from auto_ontology.dal.model_settings import get_model_setting

    try:
        row = get_model_setting(role.value)
    except Exception as exc:  # noqa: BLE001 -- fall back to env when unreadable
        # Before the first migration, or with Postgres briefly unreachable, the
        # environment is still a usable answer.
        logger.debug("model_setting unreadable (%s); using the environment", exc)
        return None
    return _from_row(row) if row else None


# ---------------------------------------------------------------------------
# Resolution and cache
# ---------------------------------------------------------------------------

_cache: dict[ModelRole, tuple[float, ResolvedModel]] = {}
_cache_lock = threading.Lock()


def _resolve_uncached(role: ModelRole) -> ResolvedModel:
    resolved = _from_db(role) or _from_env(role)
    if resolved is not None:
        return resolved
    if role == ModelRole.FAST_CHAT:
        chat = get_model(ModelRole.CHAT)
        return ResolvedModel(
            role=role,
            provider=chat.provider,
            model=chat.model,
            base_url=chat.base_url,
            api_key=chat.api_key,
            source="chat" if chat.configured else "unset",
        )
    # Nothing saved and nothing in the environment: start on NVIDIA NIM with the
    # upstream models. The role stays unconfigured until a key is entered.
    return ResolvedModel(
        role=role,
        provider=ModelProvider.NVIDIA,
        model=NVIDIA_DEFAULT_MODEL[role],
    )


def get_model(role: ModelRole | str) -> ResolvedModel:
    """The effective configuration for *role* (possibly unconfigured)."""
    role = ModelRole(role)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(role)
        if cached is not None and now - cached[0] < CACHE_TTL_S:
            return cached[1]
    resolved = _resolve_uncached(role)
    with _cache_lock:
        _cache[role] = (now, resolved)
    return resolved


def invalidate_model_cache() -> None:
    """Forget every cached role, so the next lookup reads the database."""
    with _cache_lock:
        _cache.clear()


__all__ = [
    "CACHE_TTL_S",
    "DEFAULT_BASE_URL",
    "ENV_PREFIX",
    "KEY_REQUIRED",
    "ModelNotConfiguredError",
    "ROLE_PROVIDERS",
    "ResolvedModel",
    "get_model",
    "invalidate_model_cache",
]
