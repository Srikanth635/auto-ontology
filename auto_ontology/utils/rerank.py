# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rerank candidate hits against a query with the configured rerank API.

Reranking is optional (Settings -> Models -> Reranking). It speaks the
``/rerank`` request shared by Cohere, Jina, Voyage, vLLM and Infinity::

    {"model": str, "query": str, "documents": [str], "top_n": int}

scored by ``results[].relevance_score``. A base URL that does not already end
in ``/rerank`` gets it appended.
"""

from __future__ import annotations

from typing import Any

import httpx

from auto_ontology.dal.schema import ModelRole
from auto_ontology.utils.model_config import get_model

_TIMEOUT_S = 30.0


def get_rerank_kwargs() -> dict[str, str] | None:
    """Keyword args for :func:`rerank_hits`, or ``None`` when reranking is off."""
    resolved = get_model(ModelRole.RERANK)
    if not resolved.configured:
        return None
    return {
        "rerank_invoke_url": resolved.endpoint,
        "model_name": resolved.model,
        "api_key": resolved.api_key,
    }


def _ranking_url(endpoint: str) -> str:
    url = endpoint.rstrip("/")
    return url if url.endswith("/rerank") else f"{url}/rerank"


def _scores(
    query: str, documents: list[str], *, url: str, model_name: str, api_key: str
) -> list[float]:
    """One score per document, higher is better; ``-inf`` for any not returned."""
    payload: dict[str, Any] = {
        "model": model_name,
        "query": query,
        "documents": documents,
        "top_n": len(documents),
    }
    headers = {"accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = httpx.post(url, json=payload, headers=headers, timeout=_TIMEOUT_S)
    response.raise_for_status()
    data = response.json()

    items = data.get("results") if isinstance(data, dict) else None
    scores = [float("-inf")] * len(documents)
    for item in items if isinstance(items, list) else []:
        try:
            index, score = int(item["index"]), float(item["relevance_score"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= index < len(scores):
            scores[index] = score
    return scores


def rerank_hits(
    query: str,
    hits: list[dict[str, Any]],
    *,
    rerank_invoke_url: str,
    model_name: str,
    api_key: str = "",
    top_n: int | None = None,
    text_key: str = "text",
) -> list[dict[str, Any]]:
    """*hits* sorted by relevance to *query*, best first, each with ``_rerank_score``.

    A hit that already carries ``_rerank_score`` keeps it. Ties keep their
    input order. Raises on an endpoint error; the caller picks the fallback.
    """
    if not hits:
        return hits
    scores = _scores(
        query,
        [str(hit.get(text_key) or "") for hit in hits],
        url=_ranking_url(rerank_invoke_url),
        model_name=model_name,
        api_key=api_key,
    )
    ranked = sorted(
        ({"_rerank_score": score, **hit} for hit, score in zip(hits, scores)),
        key=lambda hit: hit["_rerank_score"],
        reverse=True,
    )
    return ranked[:top_n] if top_n is not None else ranked
