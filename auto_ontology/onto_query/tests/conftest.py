# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fixtures: deterministic stand-ins for the chat and embedding models.

``fake_embed`` is a hashed bag of words with light stemming, so texts that
share words land near each other -- enough for retrieval to behave like
retrieval. ``FakeLLM`` answers each structured call from a handler registered
for its schema, and records every prompt so tests can assert on them.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable

import numpy as np
import pytest

from auto_ontology.onto_query import ai
from auto_ontology.onto_query.registry import OntologyRegistry, set_registry

FIXTURES = Path(__file__).parent / "fixtures"
K = "http://example.org/kitchen#"
H = "http://example.org/household/"

_DIM = 256


def _stem(word: str) -> str:
    for suffix in ("ing", "es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)]
    return word


def fake_embed(texts: list[str], input_type: str) -> list[list[float] | None]:
    from auto_ontology.onto_query.text import tokens

    out: list[list[float] | None] = []
    for text in texts:
        if not text.strip():
            out.append(None)
            continue
        vec = np.zeros(_DIM)
        for token in tokens(text):
            h = int(hashlib.md5(_stem(token).encode()).hexdigest(), 16)
            vec[h % _DIM] += 1.0
        out.append(vec.tolist())
    return out


class FakeLLM:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable] = {}
        self.calls: list[dict] = []

    def on(self, schema_name: str, handler: Callable) -> None:
        self.handlers[schema_name] = handler

    def __call__(self, system: str, user: str, schema, *, fast: bool = False):  # noqa: ANN001, ANN204
        name = schema.__name__
        self.calls.append(
            {"schema": name, "system": system, "user": user, "fast": fast}
        )
        handler = self.handlers.get(name)
        if handler is None:
            raise ai.OntoQueryModelError(f"no fake handler for {name}")
        result = handler(user)
        return result if isinstance(result, schema) else schema.model_validate(result)

    def count(self, schema_name: str) -> int:
        return sum(1 for c in self.calls if c["schema"] == schema_name)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ONTO_QUERY_VECTOR_STORE", "memory")
    monkeypatch.setenv("ONTO_QUERY_LOCAL_RERANK", "off")
    monkeypatch.setenv("ONTO_QUERY_DATA_DIR", str(tmp_path / "ontologies"))
    for var in ("RERANK_ENDPOINT", "RERANK_MODEL", "RERANK_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    # The rerank role is resolved from the database first; there is none here.
    from auto_ontology.utils import model_config

    monkeypatch.setattr(model_config, "_from_db", lambda role: None)
    model_config.invalidate_model_cache()


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(ai, "structured", fake)
    return fake


@pytest.fixture
def embeddings(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Turns embeddings on; ``state["model"]`` switches the vector space."""
    state = {"model": "fake-a", "calls": 0}

    def _embed(texts: list[str], input_type: str) -> list[list[float] | None]:
        state["calls"] += len(texts)
        return fake_embed(texts, input_type)

    monkeypatch.setattr(ai, "can_embed", lambda: True)
    monkeypatch.setattr(ai, "embed", _embed)
    monkeypatch.setattr(ai, "embedding_model_id", lambda: state["model"])
    return state


@pytest.fixture
def no_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai, "can_embed", lambda: False)
    monkeypatch.setattr(ai, "embedding_model_id", lambda: "")


@pytest.fixture
def registry(tmp_path: Path) -> OntologyRegistry:
    reg = OntologyRegistry(tmp_path / "ontologies")
    set_registry(reg)
    yield reg
    set_registry(None)


def _load(registry: OntologyRegistry, name: str):  # noqa: ANN202
    path = FIXTURES / name
    return registry.create(path.read_bytes(), filename=path.name)


@pytest.fixture
def kitchen(registry: OntologyRegistry, embeddings: dict):  # noqa: ANN201
    return _load(registry, "kitchen.ttl")


@pytest.fixture
def household(registry: OntologyRegistry, embeddings: dict):  # noqa: ANN201
    return _load(registry, "household.ttl")


@pytest.fixture
def mentions_none(llm: FakeLLM) -> FakeLLM:
    """Mention extraction returns nothing, so retrieval uses the question alone."""
    llm.on("Mentions", lambda user: {"mentions": []})
    return llm


def iris_in(text: str) -> list[str]:
    return re.findall(r"<(http[^>]+)>", text)
