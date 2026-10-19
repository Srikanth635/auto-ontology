# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Settings for OntoQuerying, all read from the environment at call time.

The models themselves are not configured here: OntoQuerying uses the same
roles as the rest of the app (Settings -> Models): ``chat`` for SPARQL, shapes
and judgements, ``fast_chat`` for extracting concepts from a question,
``embedding`` for the vector index and ``rerank`` for the reranking API.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """Where uploaded ontologies, their manifests and vectors are kept.

    ``ONTO_QUERY_DATA_DIR``; defaults to ``data/ontologies`` in the repo, which
    the Docker Compose file mounts as a volume.
    """
    configured = os.environ.get("ONTO_QUERY_DATA_DIR", "").strip()
    return Path(configured) if configured else _REPO_ROOT / "data" / "ontologies"


def vector_store() -> str:
    """``pgvector`` (default) or ``memory``: where nearest-neighbour search runs.

    Vectors are cached on disk either way; ``memory`` searches that cache
    directly and needs no Postgres, which suits tests and small ontologies.
    """
    value = os.environ.get("ONTO_QUERY_VECTOR_STORE", "pgvector").strip().lower()
    return value if value in ("pgvector", "memory") else "pgvector"


def local_rerank_mode() -> str:
    """``auto`` (default), ``on`` or ``off`` for the local cross-encoder.

    ``auto`` uses it only when the rerank API role is unset and
    ``sentence-transformers`` is installed (``uv sync --extra onto-rerank``).
    """
    value = os.environ.get("ONTO_QUERY_LOCAL_RERANK", "auto").strip().lower()
    return value if value in ("auto", "on", "off") else "auto"


def local_rerank_model() -> str:
    """The Hugging Face cross-encoder to load, ``ONTO_QUERY_RERANK_MODEL``."""
    return (
        os.environ.get("ONTO_QUERY_RERANK_MODEL", "").strip()
        or "BAAI/bge-reranker-base"
    )


def default_reasoner() -> str:
    """``ONTO_QUERY_REASONER``: ``auto`` (default), ``owlrl`` or ``hermit``.

    ``auto`` uses HermiT when Java is on the PATH, OWL RL otherwise.
    """
    value = os.environ.get("ONTO_QUERY_REASONER", "auto").strip().lower()
    return value if value in ("auto", "owlrl", "hermit") else "auto"


def max_upload_bytes() -> int:
    """Largest ontology file accepted, ``ONTO_QUERY_MAX_UPLOAD_MB`` (default 200)."""
    raw = os.environ.get("ONTO_QUERY_MAX_UPLOAD_MB", "").strip()
    megabytes = int(raw) if raw.isdigit() else 200
    return megabytes * 1024 * 1024
