# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The two model calls OntoQuerying makes: structured chat and embeddings.

Everything else in the package calls these, never the clients directly, so a
test can replace both with deterministic fakes (see ``tests/fakes.py``).
"""

from __future__ import annotations

import logging
from typing import Type, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from auto_ontology.utils.embedding import (
    InputType,
    embed_texts,
    embedding_configured,
    get_embed_params,
)
from auto_ontology.utils.llm_invoke import (
    get_llm_client,
    get_non_reasoning_llm_client,
    safe_invoke_with_structured_output,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OntoQueryModelError(RuntimeError):
    """A model call failed or no model is configured; the message says which."""


def structured(system: str, user: str, schema: Type[T], *, fast: bool = False) -> T:
    """Ask the ``chat`` (or ``fast_chat``) model for an instance of *schema*."""
    try:
        llm = get_non_reasoning_llm_client() if fast else get_llm_client()
    except EnvironmentError as exc:
        raise OntoQueryModelError(str(exc)) from exc
    try:
        return safe_invoke_with_structured_output(
            llm, [SystemMessage(content=system), HumanMessage(content=user)], schema
        )
    except Exception as exc:  # noqa: BLE001 -- surface one error type to callers
        raise OntoQueryModelError(
            f"The language model call failed ({type(exc).__name__}: {str(exc)[:300]})"
        ) from exc


def can_embed() -> bool:
    return embedding_configured()


def embedding_model_id() -> str:
    """Identifies the vector space: vectors from different models never mix."""
    params = get_embed_params()
    return f"{params.embed_invoke_url}|{params.model_name}|{params.dimensions or ''}"


def embed(texts: list[str], input_type: InputType) -> list[list[float] | None]:
    """One vector per text (``None`` for blank ones); raises if unconfigured."""
    if not embedding_configured():
        raise OntoQueryModelError(
            "No embedding model is configured. Choose one under Settings -> Models."
        )
    try:
        return embed_texts(texts, get_embed_params(), input_type)
    except Exception as exc:  # noqa: BLE001
        raise OntoQueryModelError(
            f"Embedding failed ({type(exc).__name__}: {str(exc)[:300]})"
        ) from exc
