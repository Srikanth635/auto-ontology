# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Re-embed every stored vector after the embedding model changes.

Vectors from two models cannot be compared, so once the embedding model changes
every row in both collections has to be rebuilt with the new one. Nothing that
was curated is lost: every vector is derived from rows that stay put.

* The data layer is rebuilt by re-ingesting each connection, the same pass a
  new connection gets.
* The semantic layer is cleared and rebuilt from the stored glossary: every
  Term with its column attributes, every SQL attribute, and every custom and
  predictive analysis. No compilation runs, so names, descriptions and
  certifications written by hand are embedded as they are.

Only one pass runs at a time. A request that arrives during a pass is folded
into one more pass after it, which then sees the latest model.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "pending": False,
    "last_started_at": None,
    "last_finished_at": None,
    "last_error": None,
}


def reembed_status() -> dict[str, Any]:
    """Whether a pass is running, and how the last one ended."""
    with _lock:
        return {
            k: _state[k]
            for k in ("running", "last_started_at", "last_finished_at", "last_error")
        }


def _reembed_data_layer() -> int:
    from auto_ontology.connectors.registry import (
        get_connectors,
        invalidate_connectors_cache,
    )
    from auto_ontology.ingestion_service.ingest import run_ingest

    invalidate_connectors_cache()
    done = 0
    for connector in get_connectors():
        try:
            run_ingest(connector)
            done += 1
        except Exception:
            logger.exception(
                "reembed: data layer failed for %s",
                getattr(connector, "database_name", "?"),
            )
    return done


def _reembed_semantic_layer() -> int:
    from auto_ontology.dal import sql_attributes as sql_attr_dal
    from auto_ontology.dal.custom_analyses import embed_custom_analyses
    from auto_ontology.dal.pql_analyses import embed_pql_analyses
    from auto_ontology.dal.terms import fetch_all_terms_and_attributes
    from auto_ontology.server.terms.service import refresh_term_embeddings
    from auto_ontology.utils.embedding import embed_docs_into_vdb, get_embed_params
    from auto_ontology.vdb import get_semantic_vdb

    vdb = get_semantic_vdb()
    cleared = vdb.delete_all()
    logger.info("reembed: cleared %d semantic vector(s)", cleared)

    terms, _ = fetch_all_terms_and_attributes()
    for term in terms:
        if term.get("id"):
            refresh_term_embeddings(term["id"], refresh_dependent_attrs=True)

    # SQL attributes that hang off no Term are not reached through one, and the
    # rest are deleted first, so embedding all of them again leaves no duplicate.
    embed_params = get_embed_params()
    for attr in sql_attr_dal.list_sql_attributes():
        attr_id = attr.get("id")
        if not attr_id:
            continue
        vdb.delete_by_id(attr_id)
        embed_docs_into_vdb(
            sql_attr_dal.fetch_sql_attribute_docs(attr_id),
            embed_params,
            vdb,
            attr.get("database_name"),
        )

    embed_custom_analyses(embed_params, vdb)
    embed_pql_analyses(embed_params, vdb)
    return len(terms)


def _run() -> None:
    from auto_ontology.utils.embedding import embedding_configured
    from auto_ontology.utils.model_config import invalidate_model_cache

    while True:
        with _lock:
            _state["pending"] = False
            _state["last_started_at"] = datetime.now(UTC).isoformat()
            _state["last_error"] = None
        started = time.monotonic()
        error: str | None = None
        try:
            # The setting was just saved by another process; read it fresh.
            invalidate_model_cache()
            if not embedding_configured():
                raise RuntimeError("No embedding model is configured.")
            databases = _reembed_data_layer()
            terms = _reembed_semantic_layer()
            logger.info(
                "reembed: finished — %d database(s), %d term(s) in %.1fs",
                databases,
                terms,
                time.monotonic() - started,
            )
        except Exception as exc:  # noqa: BLE001 -- reported through the status
            logger.exception("reembed: pass failed")
            error = str(exc)
        with _lock:
            _state["last_finished_at"] = datetime.now(UTC).isoformat()
            _state["last_error"] = error
            if not _state["pending"]:
                _state["running"] = False
                return


def trigger_reembed() -> None:
    """Start a pass in the background, or queue one behind the running pass."""
    with _lock:
        if _state["running"]:
            _state["pending"] = True
            return
        _state["running"] = True
    threading.Thread(target=_run, daemon=True, name="reembed").start()
