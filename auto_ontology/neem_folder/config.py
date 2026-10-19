# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Settings for the NEEM data folder, all read from the environment at call time.

The feature is off unless ``NEEM_DATA_DIR`` is set. Compose sets it to
``/data``, the bind mount of the repo's ``data/`` folder, for both the API
server (uploads, query execution) and the ingestion service (the watcher).
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

from auto_ontology.infra.postgres import get_postgres_connection_string

DEFAULT_DATABASE = "neem"
DEFAULT_POLL_SECONDS = 5.0
DEFAULT_MAX_UPLOAD_MB = 500

# Same bound as every other Postgres consumer in the repo: a blackholed server
# must fail a check, not hang it.
_CONNECT_TIMEOUT = 3


def data_dir() -> Path | None:
    """The watched folder, or ``None`` when the feature is off."""
    raw = os.environ.get("NEEM_DATA_DIR", "").strip()
    return Path(raw) if raw else None


def is_enabled() -> bool:
    """Whether a NEEM data folder is configured."""
    return data_dir() is not None


def database_name() -> str:
    """The Postgres database every NEEM is merged into."""
    return os.environ.get("NEEM_DATABASE", "").strip() or DEFAULT_DATABASE


def poll_seconds() -> float:
    """How often the watcher looks at the folder."""
    try:
        return max(1.0, float(os.environ.get("NEEM_POLL_SECONDS", "")))
    except ValueError:
        return DEFAULT_POLL_SECONDS


def max_upload_bytes() -> int:
    """The largest file the upload endpoint accepts."""
    try:
        megabytes = int(os.environ.get("NEEM_MAX_UPLOAD_MB", ""))
    except ValueError:
        megabytes = DEFAULT_MAX_UPLOAD_MB
    return max(1, megabytes) * 1024 * 1024


def _with_database(url: str, database: str) -> str:
    """Swap the database at the end of a ``postgresql://`` URL."""
    base, _, _ = url.rpartition("/")
    return f"{base}/{database}"


def connection_string() -> str:
    """Connector URL of the merged NEEM database (same server and role as the store)."""
    return _with_database(get_postgres_connection_string(), database_name())


def maintenance_conninfo() -> str:
    """URL of the store's own database, used to create and look up the NEEM one."""
    return get_postgres_connection_string()


def database_exists() -> bool:
    """Whether the merged database has been created yet.

    It is created by the first load, so until a NEEM file has been dropped in
    there is nothing to connect to, and the connector registry must not try.
    """
    try:
        with psycopg.connect(
            maintenance_conninfo(), connect_timeout=_CONNECT_TIMEOUT, autocommit=True
        ) as conn:
            row = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (database_name(),)
            ).fetchone()
            return row is not None
    except psycopg.Error:
        return False
