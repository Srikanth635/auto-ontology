# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Model settings: validate, store encrypted, apply live, and test a provider."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from auto_ontology.dal import model_settings as dal
from auto_ontology.dal.schema import ModelProvider, ModelRole
from auto_ontology.infra.secrets import SecretsUnavailableError, encrypt_secret
from auto_ontology.utils.embedding import VECTOR_DIM
from auto_ontology.utils.model_config import (
    DEFAULT_BASE_URL,
    KEY_REQUIRED,
    ROLE_PROVIDERS,
    ResolvedModel,
    get_model,
    invalidate_model_cache,
)

logger = logging.getLogger(__name__)

_LIST_TIMEOUT_S = 20.0
_ANTHROPIC_VERSION = "2023-06-01"

ROLE_LABELS: dict[ModelRole, str] = {
    ModelRole.CHAT: "Chat",
    ModelRole.FAST_CHAT: "Fast chat",
    ModelRole.EMBEDDING: "Embeddings",
    ModelRole.RERANK: "Reranking",
}

PROVIDER_LABELS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI: "OpenAI",
    ModelProvider.ANTHROPIC: "Anthropic",
    ModelProvider.OPENAI_COMPATIBLE: "OpenAI-compatible",
    ModelProvider.RERANK_API: "Rerank API",
    ModelProvider.NONE: "Off",
}


class ModelSettingBody(BaseModel):
    """What a role is set to. ``api_key`` omitted keeps the stored key."""

    provider: str
    model: str = ""
    base_url: str = ""
    #: ``None`` keeps the stored key (when the provider is unchanged); ``""``
    #: removes it.
    api_key: str | None = None
    dimensions: int | None = Field(default=None, ge=1, le=VECTOR_DIM)


class InvalidModelSettingError(ValueError):
    """The submitted setting is not allowed for the role. Maps to 422."""


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def _view(resolved: ResolvedModel) -> dict[str, Any]:
    return {
        "role": resolved.role.value,
        "provider": resolved.provider.value,
        "model": resolved.model,
        "base_url": resolved.base_url,
        "dimensions": resolved.dimensions,
        "has_api_key": bool(resolved.api_key),
        "configured": resolved.configured,
        "source": resolved.source,
    }


def catalog() -> dict[str, Any]:
    """Which providers each role may use, and how each provider is reached."""
    return {
        "roles": {
            role.value: {
                "label": ROLE_LABELS[role],
                "providers": [p.value for p in ROLE_PROVIDERS[role]],
            }
            for role in ModelRole
        },
        "providers": {
            provider.value: {
                "label": PROVIDER_LABELS[provider],
                "default_base_url": DEFAULT_BASE_URL.get(provider, ""),
                "key_required": provider in KEY_REQUIRED,
            }
            for provider in ModelProvider
        },
    }


def list_settings() -> list[dict[str, Any]]:
    """Every role's effective setting, read fresh."""
    invalidate_model_cache()
    return [_view(get_model(role)) for role in ModelRole]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _parse_role(role: str) -> ModelRole:
    try:
        return ModelRole(role)
    except ValueError as exc:
        raise LookupError(f"Unknown model role {role!r}") from exc


def _resolve_body(role: ModelRole, body: ModelSettingBody) -> ResolvedModel:
    """*body* as a :class:`ResolvedModel`, with the stored key filled in when kept."""
    try:
        provider = ModelProvider(body.provider)
    except ValueError as exc:
        raise InvalidModelSettingError(f"Unknown provider {body.provider!r}") from exc
    if provider not in ROLE_PROVIDERS[role]:
        allowed = ", ".join(PROVIDER_LABELS[p] for p in ROLE_PROVIDERS[role])
        raise InvalidModelSettingError(
            f"{PROVIDER_LABELS[provider]} cannot serve {ROLE_LABELS[role]}. "
            f"Choose one of: {allowed}."
        )

    model = body.model.strip()
    base_url = body.base_url.strip().rstrip("/")
    if provider != ModelProvider.NONE:
        if not model:
            raise InvalidModelSettingError("A model is required.")
        if provider in (ModelProvider.OPENAI_COMPATIBLE, ModelProvider.RERANK_API):
            if not base_url:
                raise InvalidModelSettingError(
                    "A base URL is required for this provider."
                )
        if base_url and not base_url.startswith(("http://", "https://")):
            raise InvalidModelSettingError("The base URL must start with http(s)://")

    if body.api_key is None:
        # Keep the stored key, but only for the same provider: an OpenAI key
        # would be wrong for Anthropic, and sending it there would leak it.
        current = get_model(role)
        api_key = current.api_key if current.provider == provider else ""
    else:
        api_key = body.api_key.strip()

    if provider in KEY_REQUIRED and not api_key:
        raise InvalidModelSettingError(f"{PROVIDER_LABELS[provider]} needs an API key.")

    return ResolvedModel(
        role=role,
        provider=provider,
        model=model if provider != ModelProvider.NONE else "",
        base_url=base_url if provider != ModelProvider.NONE else "",
        api_key=api_key if provider != ModelProvider.NONE else "",
        dimensions=body.dimensions if role == ModelRole.EMBEDDING else None,
        source="settings",
    )


def _embedding_identity(resolved: ResolvedModel) -> tuple[Any, ...]:
    """What makes two embedding settings produce comparable vectors."""
    return (
        resolved.configured,
        resolved.provider,
        resolved.model,
        resolved.endpoint,
        resolved.dimensions,
    )


# ---------------------------------------------------------------------------
# Applying a change
# ---------------------------------------------------------------------------


def _apply(role: ModelRole, before: ResolvedModel) -> bool:
    """Make the change take effect everywhere; return whether a re-embed started."""
    from auto_ontology.server.chat.worker import refresh_chat_workers
    from auto_ontology.server.ingestion.proxy import trigger_reembed

    invalidate_model_cache()
    after = get_model(role)
    try:
        # Prewarmed chat workers built their clients at start-up.
        refresh_chat_workers()
    except Exception:
        logger.exception("Failed to refresh chat workers after a model change")

    if role != ModelRole.EMBEDDING or not after.configured:
        return False
    if _embedding_identity(before) == _embedding_identity(after):
        return False
    return trigger_reembed()


def save_setting(
    role_name: str, body: ModelSettingBody, *, updated_by: str | None
) -> dict[str, Any]:
    """Validate and store *body* for *role_name*, then apply it."""
    role = _parse_role(role_name)
    before = get_model(role)
    resolved = _resolve_body(role, body)
    try:
        encrypted = encrypt_secret(resolved.api_key) if resolved.api_key else None
    except SecretsUnavailableError as exc:
        raise InvalidModelSettingError(str(exc)) from exc

    dal.upsert_model_setting(
        role=role.value,
        provider=resolved.provider.value,
        model=resolved.model,
        base_url=resolved.base_url,
        api_key=encrypted,
        dimensions=resolved.dimensions,
        updated_by=updated_by,
    )
    reembed = _apply(role, before)
    return {"data": _view(get_model(role)), "reembed_triggered": reembed}


def reset_setting(role_name: str) -> dict[str, Any]:
    """Forget the saved setting, so *role_name* falls back to the environment."""
    role = _parse_role(role_name)
    before = get_model(role)
    dal.delete_model_setting(role.value)
    reembed = _apply(role, before)
    return {"data": _view(get_model(role)), "reembed_triggered": reembed}


# ---------------------------------------------------------------------------
# Testing a setting and listing a provider's models
# ---------------------------------------------------------------------------


def _short(exc: Exception, secret: str = "") -> str:
    """A one-line error safe to show, with *secret* redacted.

    Some providers quote the submitted key back in their error (OpenAI does,
    for one), so the key is removed before the message goes anywhere.
    """
    text = " ".join(str(exc).split())
    if secret:
        text = text.replace(secret, "***")
    return text[:300] or type(exc).__name__


def test_setting(role_name: str, body: ModelSettingBody) -> dict[str, Any]:
    """Make one small real call with *body*, without saving it."""
    role = _parse_role(role_name)
    resolved = _resolve_body(role, body)
    if resolved.provider == ModelProvider.NONE:
        return {"ok": True, "detail": "Reranking is off; nothing to test."}
    try:
        if role in (ModelRole.CHAT, ModelRole.FAST_CHAT):
            return _test_chat(resolved)
        if role == ModelRole.EMBEDDING:
            return _test_embedding(resolved)
        return _test_rerank(resolved)
    except Exception as exc:  # noqa: BLE001 -- every failure is the test's answer
        return {"ok": False, "detail": _short(exc, resolved.api_key)}


def _test_chat(resolved: ResolvedModel) -> dict[str, Any]:
    from auto_ontology.utils.llm_invoke import build_chat_client

    client = build_chat_client(resolved, max_tokens=64)
    reply = client.invoke("Reply with the single word OK.")
    text = str(getattr(reply, "content", reply)).strip()
    return {"ok": True, "detail": f"The model answered: {text[:80] or '(empty)'}"}


def _test_embedding(resolved: ResolvedModel) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(
        base_url=resolved.endpoint,
        api_key=resolved.api_key or "unused",
        max_retries=0,
        timeout=_LIST_TIMEOUT_S,
    )
    response = client.embeddings.create(
        model=resolved.model,
        input=["Auto Ontology connection test"],
        encoding_format="float",
        **({"dimensions": resolved.dimensions} if resolved.dimensions else {}),
    )
    width = len(response.data[0].embedding)
    if width > VECTOR_DIM:
        return {
            "ok": False,
            "detail": (
                f"The model returns {width} dimensions; at most {VECTOR_DIM} can be "
                f"stored. Set Dimensions to {VECTOR_DIM} or fewer."
            ),
            "dimensions": width,
        }
    return {
        "ok": True,
        "detail": f"Embeddings work: {width} dimensions.",
        "dimensions": width,
    }


def _test_rerank(resolved: ResolvedModel) -> dict[str, Any]:
    from auto_ontology.utils.rerank import rerank_hits

    ranked = rerank_hits(
        "film rental revenue",
        [{"text": "Payments made for film rentals"}, {"text": "Staff addresses"}],
        rerank_invoke_url=resolved.endpoint,
        model_name=resolved.model,
        api_key=resolved.api_key,
    )
    best = ranked[0].get("text") if ranked else None
    return {"ok": True, "detail": f"Reranking works; ranked first: {best!r}."}


def list_models(role_name: str, body: ModelSettingBody) -> dict[str, Any]:
    """The models the provider in *body* offers, for the model picker."""
    role = _parse_role(role_name)
    # Listing needs no model yet, so validate with a placeholder.
    resolved = _resolve_body(role, body.model_copy(update={"model": body.model or "-"}))
    if resolved.provider in (ModelProvider.NONE, ModelProvider.RERANK_API):
        return {"models": []}

    if resolved.provider == ModelProvider.ANTHROPIC:
        url = f"{resolved.endpoint.rstrip('/')}/v1/models"
        headers = {
            "x-api-key": resolved.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }
    else:
        url = f"{resolved.endpoint.rstrip('/')}/models"
        headers = (
            {"Authorization": f"Bearer {resolved.api_key}"} if resolved.api_key else {}
        )

    response = httpx.get(
        url, headers=headers, params={"limit": 1000}, timeout=_LIST_TIMEOUT_S
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("data", []) if isinstance(payload, dict) else []
    ids = sorted({str(item.get("id")) for item in items if item.get("id")})

    if role == ModelRole.EMBEDDING:
        embedding_ids = [i for i in ids if "embed" in i.lower()]
        ids = embedding_ids or ids
    elif role in (ModelRole.CHAT, ModelRole.FAST_CHAT):
        chat_ids = [i for i in ids if "embed" not in i.lower()]
        ids = chat_ids or ids
    return {"models": ids}
