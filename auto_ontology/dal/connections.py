# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""UI-managed database connections.

Connection metadata lives on the catalog database row, so the UI connection and
the catalog database are the same record and cannot drift apart. A database is a
UI-managed connection when it has a ``connection`` value; the catalog name
doubles as the connection's identity.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from auto_ontology.dal import schema as s
from auto_ontology.dal.session import store

logger = logging.getLogger(__name__)


def list_connections() -> list[dict[str, Any]]:
    """Every catalog database's resolved connection.

    Databases with no stored connection are skipped, which is what
    makes this "connections" rather than "databases" — an ingested catalog with
    no UI connection has nothing to return.
    """
    connections: list[dict[str, Any]] = []
    for row in store().query_read(
        select(s.catalog_database.c.name, s.catalog_database.c.connection).order_by(
            s.catalog_database.c.name
        )
    ):
        stored = row["connection"]
        if stored:
            # jsonb here, a JSON *string* on the graph node. Callers get the
            # object either way, so decoding a string keeps a database written
            # before this column existed readable.
            connections.append(
                json.loads(stored) if isinstance(stored, str) else stored
            )
    return connections


def table_counts_by_database() -> dict[str, int]:
    """How many tables each catalog database holds, keyed by database name.

    A database with no ingested tables yet is absent rather than zero, which is
    what tells "registered, still being read" apart from "ready".
    """
    return {
        str(row["name"]): int(row["tables"])
        for row in store().query_read(
            select(
                s.catalog_database.c.name,
                func.count(s.catalog_table.c.id).label("tables"),
            )
            .select_from(
                s.catalog_database.join(
                    s.catalog_schema,
                    s.catalog_schema.c.database_id == s.catalog_database.c.id,
                ).join(
                    s.catalog_table,
                    s.catalog_table.c.schema_id == s.catalog_schema.c.id,
                )
            )
            .group_by(s.catalog_database.c.name)
        )
    }


def insert_connection(
    *,
    connection: str,
    database_name: str,
) -> dict[str, Any]:
    """Attach connection metadata to the catalog database, creating it if needed.

    Creating it matters: a connection is normally configured *before* anything
    is ingested, so there is usually no database row to attach to yet.
    """
    # An empty string means "no connection JSON on the row"; `json.loads("")`
    # would raise.
    payload = json.loads(connection) if connection and connection.strip() else None
    statement = insert(s.catalog_database).values(
        name=database_name, connection=payload
    )
    rows = store().query_write(
        statement.on_conflict_do_update(
            index_elements=[s.catalog_database.c.name],
            set_={"connection": statement.excluded.connection},
        ).returning(s.catalog_database)
    )
    return dict(rows[0])


def clear_connection(*, database_name: str) -> None:
    """Detach connection metadata from the catalog database.

    The counterpart to :func:`insert_connection`, and the write that actually
    makes a database stop being a connection — "connections" are exactly the
    catalog rows carrying a connection value.

    The row itself stays. ``catalog_schema`` cascades off it, so deleting it
    here would drop the ingested catalog while leaving behind the semantic rows
    and pgvector embeddings that are identified *through* it — the half-state
    :func:`auto_ontology.dal.reset.delete_all_data` orders its own deletes to avoid.
    Tearing the graph down is that function's job.
    """
    store().query_write(
        update(s.catalog_database)
        .where(s.catalog_database.c.name == database_name)
        .values(connection=None)
    )


def verify_connectivity() -> None:
    """Probe the store. Raises if it is unreachable.

    Backs the health endpoint, so it must fail rather than report healthy — the
    ``SELECT 1`` is deliberately the cheapest statement that still proves a
    connection can be checked out of the pool and used.
    """
    store().query_read("SELECT 1")
