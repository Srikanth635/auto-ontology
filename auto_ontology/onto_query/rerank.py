# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rerank fused hits with a cross-encoder.

Tried in order:

1. the **rerank API** role from Settings -> Models (Cohere, Jina, Voyage,
   vLLM, Infinity -- anything speaking ``/rerank``);
2. a **local cross-encoder** (``BAAI/bge-reranker-base`` by default) when
   ``sentence-transformers`` is installed (``uv sync --extra onto-rerank``);
3. **none** -- the fused order stands.

A failure at any step falls through to the next, so reranking can only ever
make search better, never break it.
"""

from __future__ import annotations

import logging
import threading

from auto_ontology.onto_query import config
from auto_ontology.onto_query.index import Hit, OntologyIndex

logger = logging.getLogger(__name__)

_local_model = None
_local_failed = False
_local_lock = threading.Lock()


def _local_cross_encoder():  # noqa: ANN202 -- sentence_transformers.CrossEncoder
    global _local_model, _local_failed
    mode = config.local_rerank_mode()
    if mode == "off" or _local_failed:
        return None
    with _local_lock:
        if _local_model is not None:
            return _local_model
        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            if mode == "on":
                logger.warning(
                    "ONTO_QUERY_LOCAL_RERANK=on but sentence-transformers is not "
                    "installed; run `uv sync --extra onto-rerank`."
                )
            _local_failed = True
            return None
        try:
            _local_model = CrossEncoder(config.local_rerank_model())
        except Exception as exc:  # noqa: BLE001 -- e.g. no network for the download
            logger.warning("Could not load local reranker: %s", exc)
            _local_failed = True
            return None
        return _local_model


def backend_name() -> str:
    from auto_ontology.utils.rerank import get_rerank_kwargs

    if get_rerank_kwargs() is not None:
        return "api"
    if config.local_rerank_mode() != "off" and not _local_failed:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            return "none"
        return "local"
    return "none"


def _apply(hits: list[Hit], scores: list[float], source: str) -> list[Hit]:
    for hit, score in zip(hits, scores):
        hit.rerank_score = float(score)
    logger.debug("Reranked %d hits with %s", len(hits), source)
    return sorted(hits, key=lambda h: h.rerank_score or 0.0, reverse=True)


def rerank(index: OntologyIndex, query: str, hits: list[Hit]) -> tuple[list[Hit], str]:
    """*hits* reordered by relevance to *query*, and which backend did it."""
    if len(hits) < 2:
        return hits, "none"
    documents = [index.document(h.iri) for h in hits]

    from auto_ontology.utils.rerank import get_rerank_kwargs, rerank_hits

    api = get_rerank_kwargs()
    if api is not None:
        try:
            ranked = rerank_hits(
                query,
                [{"text": d, "i": i} for i, d in enumerate(documents)],
                **api,
            )
            scores = [0.0] * len(hits)
            for item in ranked:
                scores[item["i"]] = item["_rerank_score"]
            return _apply(hits, scores, "api"), "api"
        except Exception as exc:  # noqa: BLE001 -- fall through to local
            logger.warning("Rerank API failed, trying local: %s", exc)

    model = _local_cross_encoder()
    if model is not None:
        try:
            scores = model.predict([(query, d) for d in documents])
            return _apply(hits, list(scores), "local"), "local"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local rerank failed: %s", exc)
    return hits, "none"
