# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Routes for Settings -> Models: which provider and model serve each role."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Path, Request

from auto_ontology.server.identity import resolve_internal_user
from auto_ontology.server.ingestion.proxy import get_reembed_status, trigger_reembed
from auto_ontology.server.model_settings import service
from auto_ontology.server.model_settings.service import (
    InvalidModelSettingError,
    ModelSettingBody,
)
from auto_ontology.server.responses import (
    ModelListResponse,
    ModelSettingSaveResponse,
    ModelSettingsResponse,
    ModelTestResponse,
    ReembedStatusResponse,
    StatusResponse,
)

router = APIRouter()

_ROLE = Path(description="`chat`, `fast_chat`, `embedding` or `rerank`.")


@router.get("/model-settings", response_model=ModelSettingsResponse)
def list_model_settings() -> dict[str, Any]:
    """Every model role's effective provider and model, and what each may use.

    API keys are never returned; ``has_api_key`` says whether one is stored.
    ``source`` says where a role's value comes from: saved settings, the
    environment, the chat model (fast chat only), or nowhere yet.
    """
    return {
        "data": service.list_settings(),
        **service.catalog(),
        "reembed": get_reembed_status(),
    }


@router.put("/model-settings/{role}", response_model=ModelSettingSaveResponse)
def save_model_setting(
    body: ModelSettingBody, request: Request, role: str = _ROLE
) -> dict[str, Any]:
    """Save a role's provider and model. The API key is stored encrypted.

    Omitting ``api_key`` keeps the stored key when the provider is unchanged.
    Changing the embedding model starts a background re-embed of every stored
    vector; ``reembed_triggered`` says whether one started.
    """
    try:
        return service.save_setting(
            role, body, updated_by=resolve_internal_user(request, required=False)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidModelSettingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/model-settings/{role}", response_model=ModelSettingSaveResponse)
def reset_model_setting(role: str = _ROLE) -> dict[str, Any]:
    """Forget a role's saved setting, so it falls back to the environment."""
    try:
        return service.reset_setting(role)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/model-settings/{role}/test", response_model=ModelTestResponse)
def test_model_setting(body: ModelSettingBody, role: str = _ROLE) -> dict[str, Any]:
    """Make one small real call with a setting, without saving it.

    ``ok`` is false, with the provider's error in ``detail``, when the call
    fails. Omitting ``api_key`` uses the stored key.
    """
    try:
        return service.test_setting(role, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidModelSettingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/model-settings/{role}/models", response_model=ModelListResponse)
def list_provider_models(body: ModelSettingBody, role: str = _ROLE) -> dict[str, Any]:
    """The model ids the provider in the body offers, for the model picker.

    Omitting ``api_key`` uses the stored key. A provider that cannot be reached
    answers 502 with its error.
    """
    try:
        return service.list_models(role, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidModelSettingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not list models: {service._short(exc)}"
        ) from exc


@router.get("/model-settings/reembed", response_model=ReembedStatusResponse)
def reembed_status() -> dict[str, Any]:
    """Whether a re-embed pass is running, and how the last one ended."""
    status = get_reembed_status()
    if status is None:
        raise HTTPException(status_code=503, detail="Ingestion service unreachable")
    return status


@router.post("/model-settings/reembed", status_code=202, response_model=StatusResponse)
def start_reembed() -> dict[str, str]:
    """Rebuild every stored vector with the current embedding model."""
    if not trigger_reembed():
        raise HTTPException(status_code=503, detail="Ingestion service unreachable")
    return {"status": "accepted"}
