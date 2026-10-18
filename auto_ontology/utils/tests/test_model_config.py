# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""How a model role is resolved: saved settings, then the environment, then unset."""

from __future__ import annotations

import pytest

from auto_ontology.dal.schema import ModelProvider, ModelRole
from auto_ontology.utils import model_config
from auto_ontology.utils.model_config import (
    ModelNotConfiguredError,
    ResolvedModel,
    get_model,
)

_ENV_NAMES = [
    f"{prefix}_{field}"
    for prefix in ("DEFAULT_MODELS", "REASONING", "NON_REASONING", "EMBED", "RERANK")
    for field in ("PROVIDER", "ENDPOINT", "MODEL", "API_KEY")
] + ["EMBED_DIMENSIONS"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> dict[ModelRole, ResolvedModel]:
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    saved: dict[ModelRole, ResolvedModel] = {}
    monkeypatch.setattr(model_config, "_from_db", lambda role: saved.get(role))
    model_config.invalidate_model_cache()
    yield saved
    model_config.invalidate_model_cache()


def test_nothing_configured_is_unconfigured() -> None:
    chat = get_model(ModelRole.CHAT)
    assert chat.source == "unset"
    assert not chat.configured
    with pytest.raises(ModelNotConfiguredError, match="Settings -> Models"):
        chat.require()


def test_a_saved_setting_wins_over_the_environment(
    monkeypatch: pytest.MonkeyPatch, _clean: dict
) -> None:
    monkeypatch.setenv("REASONING_MODEL", "from-env")
    monkeypatch.setenv("REASONING_API_KEY", "sk-env")
    _clean[ModelRole.CHAT] = ResolvedModel(
        ModelRole.CHAT,
        ModelProvider.ANTHROPIC,
        "claude-from-settings",
        api_key="sk-ant",
        source="settings",
    )
    chat = get_model("chat")
    assert (chat.provider, chat.model, chat.source) == (
        ModelProvider.ANTHROPIC,
        "claude-from-settings",
        "settings",
    )
    assert chat.endpoint == "https://api.anthropic.com"


@pytest.mark.parametrize(
    ("endpoint", "provider"),
    [
        ("", ModelProvider.OPENAI),
        ("https://api.openai.com/v1", ModelProvider.OPENAI),
        ("https://api.anthropic.com", ModelProvider.ANTHROPIC),
        ("http://localhost:11434/v1", ModelProvider.OPENAI_COMPATIBLE),
    ],
)
def test_the_environment_infers_the_provider_from_the_endpoint(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, provider: ModelProvider
) -> None:
    monkeypatch.setenv("DEFAULT_MODELS_MODEL", "m")
    if endpoint:
        monkeypatch.setenv("DEFAULT_MODELS_ENDPOINT", endpoint)
    assert get_model(ModelRole.CHAT).provider == provider


def test_an_explicit_provider_overrides_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REASONING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("REASONING_ENDPOINT", "https://api.openai.com/v1")
    monkeypatch.setenv("REASONING_MODEL", "m")
    assert get_model(ModelRole.CHAT).provider == ModelProvider.OPENAI_COMPATIBLE


def test_fast_chat_borrows_chat_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REASONING_MODEL", "gpt-main")
    monkeypatch.setenv("REASONING_API_KEY", "sk-1")
    fast = get_model(ModelRole.FAST_CHAT)
    assert (fast.model, fast.source, fast.configured) == ("gpt-main", "chat", True)


def test_rerank_ignores_the_shared_chat_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEFAULT_MODELS_ENDPOINT", "https://api.openai.com/v1")
    monkeypatch.setenv("DEFAULT_MODELS_MODEL", "gpt-main")
    rerank = get_model(ModelRole.RERANK)
    assert rerank.provider == ModelProvider.NONE
    assert not rerank.configured


def test_a_keyless_local_server_is_configured() -> None:
    local = ResolvedModel(
        ModelRole.EMBEDDING,
        ModelProvider.OPENAI_COMPATIBLE,
        "nomic-embed-text",
        base_url="http://localhost:11434/v1",
    )
    assert local.configured


def test_openai_without_a_key_is_not_configured() -> None:
    assert not ResolvedModel(ModelRole.CHAT, ModelProvider.OPENAI, "gpt").configured


def test_a_compatible_provider_needs_a_base_url() -> None:
    assert not ResolvedModel(
        ModelRole.CHAT, ModelProvider.OPENAI_COMPATIBLE, "llama", api_key="k"
    ).configured


def test_results_are_cached_until_invalidated(_clean: dict) -> None:
    _clean[ModelRole.CHAT] = ResolvedModel(
        ModelRole.CHAT, ModelProvider.OPENAI, "first", api_key="k", source="settings"
    )
    assert get_model(ModelRole.CHAT).model == "first"
    _clean[ModelRole.CHAT] = ResolvedModel(
        ModelRole.CHAT, ModelProvider.OPENAI, "second", api_key="k", source="settings"
    )
    assert get_model(ModelRole.CHAT).model == "first"
    model_config.invalidate_model_cache()
    assert get_model(ModelRole.CHAT).model == "second"


def test_the_key_stays_out_of_repr() -> None:
    resolved = ResolvedModel(ModelRole.CHAT, ModelProvider.OPENAI, "m", api_key="sk-x")
    assert "sk-x" not in repr(resolved)
