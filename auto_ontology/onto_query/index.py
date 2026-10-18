# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hybrid search over an ontology's element documents.

Two rankings are fused with reciprocal-rank fusion:

* **Dense** -- cosine similarity of embeddings, searched in pgvector (the app's
  vector store, collection :data:`VDB_COLLECTION`) or in memory.
* **Keyword** -- BM25 over labels, synonyms, definitions and parent names.
  Ontology labels are short and exact, so this catches what embeddings blur
  ("ABox" vs "TBox") and keeps search working with no embedding model at all.

Vectors are also cached on disk next to the ontology (``vectors.npy``), keyed
by a hash of each document, for three reasons: a restart does not re-embed,
editing an ontology re-embeds only the elements whose text changed, and
all-pairs work (duplicate detection, alignment) needs the matrix in memory.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from auto_ontology.onto_query import ai, config
from auto_ontology.onto_query.documents import element_document, keyword_text
from auto_ontology.onto_query.model import ElementKind, Ontology
from auto_ontology.onto_query.text import tokens

logger = logging.getLogger(__name__)

#: pgvector collection holding every ontology's vectors, one ``database_name``
#: (``onto:<id>``) per ontology.
VDB_COLLECTION = "ontology_layer"
#: Reciprocal-rank-fusion constant; 60 is the value from the original paper
#: and the usual default.
RRF_K = 60
#: Each ranking contributes this many hits per requested result before fusion.
_DEPTH_FACTOR = 4
_MIN_DEPTH = 40


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class Hit:
    iri: str
    score: float
    dense_rank: int | None = None
    keyword_rank: int | None = None
    dense_similarity: float | None = None
    rerank_score: float | None = None

    def to_dict(self) -> dict:
        return {
            "iri": self.iri,
            "score": round(self.score, 6),
            "dense_rank": self.dense_rank,
            "keyword_rank": self.keyword_rank,
            "dense_similarity": None
            if self.dense_similarity is None
            else round(self.dense_similarity, 4),
            "rerank_score": None
            if self.rerank_score is None
            else round(self.rerank_score, 4),
        }


@dataclass
class IndexStatus:
    dense: bool = False
    store: str = "none"
    embedded: int = 0
    reused: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dense": self.dense,
            "vector_store": self.store,
            "embedded": self.embedded,
            "reused": self.reused,
            "warnings": self.warnings,
        }


class OntologyIndex:
    """Documents, keyword index and (optionally) vectors for one ontology."""

    def __init__(self, ontology: Ontology, directory: Path | None = None) -> None:
        self.ontology = ontology
        self.directory = directory
        self.iris: list[str] = []
        self.documents: list[str] = []
        self.kinds: list[ElementKind] = []
        self._position: dict[str, int] = {}
        self._bm25: BM25Okapi | None = None
        self.vectors: np.ndarray | None = None
        self.status = IndexStatus()
        self._vdb = None
        #: Which embedding model the vectors came from (see ``ai.embedding_model_id``).
        self.space = ""

    # -- building -------------------------------------------------------------

    @property
    def vdb_key(self) -> str:
        return f"onto:{self.ontology.id}"

    def build(self, *, embed: bool = True) -> IndexStatus:
        """(Re)build everything; reuses cached vectors whose document is unchanged."""
        elements = sorted(self.ontology.elements.values(), key=lambda e: e.iri)
        self.iris = [e.iri for e in elements]
        self.kinds = [e.kind for e in elements]
        self.documents = [element_document(self.ontology, e) for e in elements]
        self._position = {iri: i for i, iri in enumerate(self.iris)}
        corpus = [tokens(keyword_text(self.ontology, e)) or ["_"] for e in elements]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self.status = IndexStatus()
        if embed:
            self._build_vectors()
        else:
            self.status.warnings.append("Embedding skipped; keyword search only.")
        return self.status

    def _cache_paths(self) -> tuple[Path, Path] | None:
        if self.directory is None:
            return None
        return self.directory / "vectors.npy", self.directory / "vectors.json"

    def _load_cache(self) -> dict[str, np.ndarray]:
        paths = self._cache_paths()
        if paths is None or not paths[0].exists() or not paths[1].exists():
            return {}
        try:
            matrix = np.load(paths[0])
            keys = json.loads(paths[1].read_text())
        except Exception:  # noqa: BLE001 -- a corrupt cache just re-embeds
            logger.warning("Ignoring unreadable vector cache in %s", self.directory)
            return {}
        if len(keys) != len(matrix):
            return {}
        return {key: matrix[i] for i, key in enumerate(keys)}

    def _save_cache(self, keys: list[str], matrix: np.ndarray) -> None:
        paths = self._cache_paths()
        if paths is None:
            return
        np.save(paths[0], matrix.astype(np.float16))
        paths[1].write_text(json.dumps(keys))

    def _build_vectors(self) -> None:
        if not ai.can_embed():
            self.status.warnings.append(
                "No embedding model is configured (Settings -> Models), so "
                "search is keyword-only."
            )
            return
        # The model is part of the key: after a model change every vector is
        # stale, and vectors of two models are not comparable.
        space = ai.embedding_model_id()
        self.space = space
        keys = [_hash(f"{space}\n{doc}") for doc in self.documents]
        cache = self._load_cache()
        missing = [i for i, key in enumerate(keys) if key not in cache]
        fresh: dict[int, list[float]] = {}
        if missing:
            try:
                vectors = ai.embed([self.documents[i] for i in missing], "passage")
            except ai.OntoQueryModelError as exc:
                self.status.warnings.append(f"{exc} Search is keyword-only.")
                return
            for i, vector in zip(missing, vectors):
                if vector is not None:
                    fresh[i] = vector
        found: dict[int, np.ndarray] = {}
        for i, key in enumerate(keys):
            if key in cache:
                found[i] = cache[key].astype(np.float32)
            elif i in fresh:
                found[i] = np.asarray(fresh[i], dtype=np.float32)
        if not found:
            self.status.warnings.append("No vectors were produced; keyword-only.")
            return
        width = max(len(v) for v in found.values())
        # An element whose text could not be embedded keeps a zero row: it is
        # never a dense match, but keyword search still finds it.
        matrix = np.zeros((len(keys), width), dtype=np.float32)
        for i, row in found.items():
            matrix[i, : len(row)] = row
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.vectors = matrix / norms
        self.status.dense = True
        self.status.embedded = len(fresh)
        self.status.reused = len(keys) - len(missing)
        self._save_cache(keys, self.vectors)
        self.status.store = "memory"
        if config.vector_store() == "pgvector":
            self._write_pgvector()

    def _get_vdb(self):  # noqa: ANN202 -- PostgresVDB, imported lazily
        if self._vdb is None:
            from auto_ontology.vdb import get_vdb

            self._vdb = get_vdb(collection_name=VDB_COLLECTION)
        return self._vdb

    def _write_pgvector(self) -> None:
        from auto_ontology.vdb.records import write_embedded_rows

        assert self.vectors is not None
        try:
            vdb = self._get_vdb()
            vdb.delete_by_database(self.vdb_key)
            rows = [
                {
                    "text": doc,
                    "path": f"ontology:{self.ontology.id}:{iri}",
                    "metadata": {
                        "id": iri,
                        "label": kind.value,
                        "name": self.ontology.name(iri),
                        "database_name": self.vdb_key,
                        "embedding": self.vectors[i].tolist(),
                    },
                }
                for i, (iri, kind, doc) in enumerate(
                    zip(self.iris, self.kinds, self.documents)
                )
            ]
            write_embedded_rows(vdb, rows)
            self.status.store = "pgvector"
        except Exception as exc:  # noqa: BLE001 -- memory search still works
            logger.warning("pgvector unavailable for %s: %s", self.ontology.id, exc)
            self.status.warnings.append(
                "pgvector is unreachable; searching the in-memory vectors instead."
            )
            self.status.store = "memory"

    def drop_pgvector(self) -> None:
        if config.vector_store() != "pgvector":
            return
        try:
            self._get_vdb().delete_by_database(self.vdb_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not drop pgvector rows for %s: %s", self.vdb_key, exc)

    # -- lookup ---------------------------------------------------------------

    def document(self, iri: str) -> str:
        i = self._position.get(iri)
        return self.documents[i] if i is not None else ""

    def vector(self, iri: str) -> np.ndarray | None:
        i = self._position.get(iri)
        if i is None or self.vectors is None:
            return None
        return self.vectors[i]

    # -- search ---------------------------------------------------------------

    def _allowed(self, kinds: set[ElementKind] | None) -> np.ndarray:
        if not kinds:
            return np.ones(len(self.iris), dtype=bool)
        return np.array([k in kinds for k in self.kinds], dtype=bool)

    def keyword_ranking(
        self, query: str, depth: int, kinds: set[ElementKind] | None = None
    ) -> list[tuple[str, float]]:
        if self._bm25 is None:
            return []
        query_tokens = tokens(query)
        if not query_tokens:
            return []
        scores = np.asarray(self._bm25.get_scores(query_tokens), dtype=np.float64)
        scores[~self._allowed(kinds)] = -np.inf
        order = np.argsort(-scores)[:depth]
        return [(self.iris[i], float(scores[i])) for i in order if scores[i] > 0]

    def dense_ranking_by_vector(
        self,
        vector: np.ndarray,
        depth: int,
        kinds: set[ElementKind] | None = None,
        exclude: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        if self.vectors is None:
            return []
        query = np.asarray(vector, dtype=np.float32)
        if query.shape[0] != self.vectors.shape[1]:
            padded = np.zeros(self.vectors.shape[1], dtype=np.float32)
            n = min(len(query), len(padded))
            padded[:n] = query[:n]
            query = padded
        norm = np.linalg.norm(query)
        if norm == 0:
            return []
        sims = self.vectors @ (query / norm)
        sims = sims.astype(np.float64)
        sims[~self._allowed(kinds)] = -np.inf
        if exclude:
            for iri in exclude:
                if iri in self._position:
                    sims[self._position[iri]] = -np.inf
        order = np.argsort(-sims)[:depth]
        return [(self.iris[i], float(sims[i])) for i in order if np.isfinite(sims[i])]

    def _dense_ranking(
        self, query: str, depth: int, kinds: set[ElementKind] | None
    ) -> list[tuple[str, float]]:
        if self.vectors is None:
            return []
        if ai.embedding_model_id() != self.space:
            logger.warning(
                "Embedding model changed since %s was indexed; dense search is off "
                "until it is reindexed.",
                self.ontology.id,
            )
            return []
        try:
            vector = ai.embed([query], "query")[0]
        except ai.OntoQueryModelError as exc:
            logger.warning("Dense search skipped: %s", exc)
            return []
        if vector is None:
            return []
        if self.status.store == "pgvector":
            try:
                hits = self._get_vdb().retrieval(
                    [vector], top_k=depth * 2, where={"database_name": self.vdb_key}
                )[0]
                ranked = [
                    (str(h["metadata"].get("id")), 1.0 - float(h["_distance"]))
                    for h in hits
                    if h.get("metadata", {}).get("id") in self._position
                ]
                if kinds:
                    ranked = [
                        r for r in ranked if self.kinds[self._position[r[0]]] in kinds
                    ]
                if ranked:
                    return ranked[:depth]
            except Exception as exc:  # noqa: BLE001 -- fall back to memory
                logger.warning("pgvector search failed, using memory: %s", exc)
        return self.dense_ranking_by_vector(np.asarray(vector), depth, kinds)

    def search(
        self,
        query: str,
        *,
        k: int = 10,
        kinds: set[ElementKind] | None = None,
        include_deprecated: bool = False,
    ) -> list[Hit]:
        """The *k* best elements for *query*, fused from both rankings."""
        depth = max(_MIN_DEPTH, k * _DEPTH_FACTOR)
        dense = self._dense_ranking(query, depth, kinds)
        keyword = self.keyword_ranking(query, depth, kinds)
        return self.fuse(dense, keyword, k=k, include_deprecated=include_deprecated)

    def fuse(
        self,
        dense: list[tuple[str, float]],
        keyword: list[tuple[str, float]],
        *,
        k: int,
        include_deprecated: bool = False,
    ) -> list[Hit]:
        hits: dict[str, Hit] = {}
        for rank, (iri, sim) in enumerate(dense, start=1):
            hit = hits.setdefault(iri, Hit(iri=iri, score=0.0))
            hit.score += 1.0 / (RRF_K + rank)
            hit.dense_rank = rank
            hit.dense_similarity = sim
        for rank, (iri, _) in enumerate(keyword, start=1):
            hit = hits.setdefault(iri, Hit(iri=iri, score=0.0))
            hit.score += 1.0 / (RRF_K + rank)
            hit.keyword_rank = rank
        ranked = sorted(hits.values(), key=lambda h: h.score, reverse=True)
        if not include_deprecated:
            ranked = [
                h
                for h in ranked
                if not getattr(self.ontology.get(h.iri), "deprecated", False)
            ]
        return ranked[:k]
