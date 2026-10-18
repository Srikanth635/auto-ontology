# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Settings -> Models: validation, encryption at rest, and applying a change."""

from __future__ import annotations

import os
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import select  # noqa: E402

from auto_ontology.dal import schema as s  # noqa: E402
from auto_ontology.dal.session import store  # noqa: E402
from auto_ontology.server.model_settings import service  # noqa: E402
from auto_ontology.server.model_settings.service import (  # noqa: E402
    InvalidModelSettingError,
    ModelSettingBody,
)
from auto_ontology.utils import model_config  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def require_schema():
    if not os.environ.get("POSTGRES_USER"):
        pytest.skip("POSTGRES_* not set")
    try:
        store().query_read("SELECT 1 FROM model_setting LIMIT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"auto_ontology schema unavailable (alembic upgrade head): {exc}")


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """An empty settings table, no model env vars, and recorded side effects."""
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret")
    for name in list(os.environ):
        if name.split("_")[0] in {"DEFAULT", "REASONING", "NON", "EMBED", "RERANK"}:
            monkeypatch.delenv(name)
    calls: dict[str, Any] = {"reembed": 0, "workers": 0}

    def _reembed() -> bool:
        calls["reembed"] += 1
        return True

    def _workers() -> None:
        calls["workers"] += 1

    monkeypatch.setattr(
        "auto_ontology.server.ingestion.proxy.trigger_reembed", _reembed
    )
    monkeypatch.setattr(
        "auto_ontology.server.chat.worker.refresh_chat_workers", _workers
    )
    store().query_write(s.model_setting.delete())
    model_config.invalidate_model_cache()
    yield calls
    store().query_write(s.model_setting.delete())
    model_config.invalidate_model_cache()


def _stored_key(role: str) -> str | None:
    rows = store().query_read(
        select(s.model_setting.c.api_key).where(s.model_setting.c.role == role)
    )
    return rows[0]["api_key"] if rows else None


def _chat(**overrides: Any) -> ModelSettingBody:
    fields = {"provider": "openai", "model": "gpt-test", "api_key": "sk-plain-1"}
    fields.update(overrides)
    return ModelSettingBody(**fields)


def test_the_key_is_encrypted_at_rest_and_never_returned() -> None:
    result = service.save_setting("chat", _chat(), updated_by="u1")

    assert result["data"]["has_api_key"] is True
    assert "sk-plain-1" not in str(result)
    stored = _stored_key("chat")
    assert stored and "sk-plain-1" not in stored
    assert model_config.get_model("chat").api_key == "sk-plain-1"


def test_saving_takes_effect_at_once(clean: dict[str, Any]) -> None:
    service.save_setting("chat", _chat(model="first"), updated_by=None)
    service.save_setting("chat", _chat(model="second"), updated_by=None)
    assert model_config.get_model("chat").model == "second"
    assert clean["workers"] == 2


def test_an_omitted_key_is_kept_for_the_same_provider() -> None:
    service.save_setting("chat", _chat(), updated_by=None)
    service.save_setting("chat", _chat(model="gpt-2", api_key=None), updated_by=None)
    assert model_config.get_model("chat").api_key == "sk-plain-1"


def test_an_omitted_key_is_not_carried_to_another_provider() -> None:
    service.save_setting("chat", _chat(), updated_by=None)
    with pytest.raises(InvalidModelSettingError, match="needs an API key"):
        service.save_setting(
            "chat", _chat(provider="anthropic", api_key=None), updated_by=None
        )


@pytest.mark.parametrize(
    ("role", "body", "message"),
    [
        (
            "embedding",
            {"provider": "anthropic", "model": "m", "api_key": "k"},
            "cannot serve",
        ),
        (
            "chat",
            {"provider": "openai_compatible", "model": "m"},
            "base URL is required",
        ),
        (
            "chat",
            {"provider": "openai", "model": "", "api_key": "k"},
            "model is required",
        ),
        (
            "rerank",
            {"provider": "openai", "model": "m", "api_key": "k"},
            "cannot serve",
        ),
        (
            "chat",
            {"provider": "openai_compatible", "model": "m", "base_url": "ftp://x"},
            "http",
        ),
    ],
)
def test_invalid_settings_are_refused(role: str, body: dict, message: str) -> None:
    with pytest.raises(InvalidModelSettingError, match=message):
        service.save_setting(role, ModelSettingBody(**body), updated_by=None)


def test_an_unknown_role_is_not_found() -> None:
    with pytest.raises(LookupError):
        service.save_setting("vision", _chat(), updated_by=None)


def test_a_keyless_local_server_can_be_saved() -> None:
    result = service.save_setting(
        "embedding",
        ModelSettingBody(
            provider="openai_compatible",
            model="nomic-embed-text",
            base_url="http://localhost:11434/v1/",
        ),
        updated_by=None,
    )
    assert result["data"]["configured"] is True
    assert result["data"]["base_url"] == "http://localhost:11434/v1"
    assert _stored_key("embedding") is None


def test_changing_the_embedding_model_re_embeds(clean: dict[str, Any]) -> None:
    body = ModelSettingBody(
        provider="openai", model="text-embedding-3-small", api_key="sk-e"
    )
    first = service.save_setting("embedding", body, updated_by=None)
    again = service.save_setting("embedding", body, updated_by=None)
    resized = service.save_setting(
        "embedding", body.model_copy(update={"dimensions": 512}), updated_by=None
    )

    assert first["reembed_triggered"] is True
    assert again["reembed_triggered"] is False
    assert resized["reembed_triggered"] is True
    assert clean["reembed"] == 2


def test_a_chat_change_does_not_re_embed(clean: dict[str, Any]) -> None:
    service.save_setting("chat", _chat(), updated_by=None)
    assert clean["reembed"] == 0


def test_resetting_falls_back_to_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service.save_setting("chat", _chat(model="from-settings"), updated_by=None)
    monkeypatch.setenv("REASONING_MODEL", "from-env")
    monkeypatch.setenv("REASONING_API_KEY", "sk-env")

    result = service.reset_setting("chat")

    assert result["data"]["model"] == "from-env"
    assert result["data"]["source"] == "environment"


def test_reranking_can_be_switched_off() -> None:
    result = service.save_setting(
        "rerank", ModelSettingBody(provider="none"), updated_by=None
    )
    assert result["data"]["configured"] is False
    assert result["data"]["provider"] == "none"


def test_the_listing_covers_every_role_and_hides_keys() -> None:
    service.save_setting("chat", _chat(), updated_by=None)
    rows = service.list_settings()
    assert [r["role"] for r in rows] == ["chat", "fast_chat", "embedding", "rerank"]
    assert all("api_key" not in r for r in rows)
    assert rows[1]["source"] == "chat"
