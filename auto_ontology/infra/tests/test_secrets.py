# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stored secrets are encrypted under AUTH_SECRET and unreadable without it."""

from __future__ import annotations

import pytest

from auto_ontology.infra.secrets import (
    SecretsUnavailableError,
    decrypt_secret,
    encrypt_secret,
)


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SECRET", "first-secret-for-tests")


def test_a_secret_round_trips() -> None:
    token = encrypt_secret("sk-live-123")
    assert decrypt_secret(token) == "sk-live-123"


def test_the_stored_token_does_not_contain_the_secret() -> None:
    assert "sk-live-123" not in encrypt_secret("sk-live-123")


def test_another_auth_secret_cannot_read_it(monkeypatch: pytest.MonkeyPatch) -> None:
    token = encrypt_secret("sk-live-123")
    monkeypatch.setenv("AUTH_SECRET", "a-rotated-secret")
    assert decrypt_secret(token) is None


def test_encrypting_without_auth_secret_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTH_SECRET")
    with pytest.raises(SecretsUnavailableError):
        encrypt_secret("sk-live-123")


def test_decrypting_without_auth_secret_reads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = encrypt_secret("sk-live-123")
    monkeypatch.delenv("AUTH_SECRET")
    assert decrypt_secret(token) is None


def test_an_empty_token_is_no_secret() -> None:
    assert decrypt_secret("") is None
