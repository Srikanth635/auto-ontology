# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Encrypt and decrypt secrets stored in Postgres, such as model API keys.

The key is derived from ``AUTH_SECRET``, the same secret the frontend already
requires, so there is nothing new to configure. Every service that reads a
stored secret (the backend and the ingestion service) gets ``AUTH_SECRET`` from
the same ``.env``.

Rotating ``AUTH_SECRET`` makes previously stored secrets unreadable: decrypting
them fails and callers treat the secret as missing, so it has to be entered
again. That is the intended trade-off: a key that survives a secret rotation
would not be protected by it.
"""

from __future__ import annotations

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

_HKDF_INFO = b"auto-ontology/stored-secrets/v1"


class SecretsUnavailableError(RuntimeError):
    """``AUTH_SECRET`` is not set, so nothing can be encrypted or decrypted."""


def _fernet() -> Fernet:
    secret = os.environ.get("AUTH_SECRET", "")
    if not secret:
        raise SecretsUnavailableError(
            "AUTH_SECRET is not set; it is needed to encrypt stored API keys."
        )
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(
        secret.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt *plaintext* into a token that is safe to store as text."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    """Decrypt *token*, or ``None`` when it cannot be read.

    ``None`` covers a token written under a different ``AUTH_SECRET`` and a
    missing ``AUTH_SECRET``. Callers treat both as "no key stored".
    """
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except SecretsUnavailableError:
        logger.warning("AUTH_SECRET is not set; stored API keys cannot be read.")
        return None
    except InvalidToken:
        logger.warning(
            "A stored API key could not be decrypted, most likely because "
            "AUTH_SECRET changed since it was saved. Enter the key again."
        )
        return None
