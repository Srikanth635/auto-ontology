# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Database files in the data folder.

Docker Compose mounts the repo's ``data/`` folder at ``/data`` in the backend
and the ingestion service. A SQLite or DuckDB file placed there becomes a
connection of its own: the ingestion service watches the folder, and the
backend lets the UI upload into it. This module is what both sides share — the
folder's location, which files count, and how a file maps to a connection.
"""

from __future__ import annotations

import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = "/data"

#: Extension -> connection ``type``. SQLite is the common case: ``.db`` is its
#: usual alternative extension, so it is read as SQLite rather than guessed at.
DATABASE_EXTENSIONS: dict[str, str] = {
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
    ".db": "sqlite",
    ".duckdb": "duckdb",
}

#: A text dump of a SQLite database (``sqlite3 x.db .dump``). It is not a
#: database yet, so the watcher turns it into a ``.sqlite`` next to it.
SQL_DUMP_EXTENSION = ".sql"

_SQLITE_MAGIC = b"SQLite format 3\x00"
_DUCKDB_MAGIC = b"DUCK"  # at byte offset 8

_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def data_dir() -> Path:
    """The folder database files are read from, ``DATA_DIR`` or ``/data``."""
    return Path(os.environ.get("DATA_DIR") or DEFAULT_DATA_DIR)


def max_upload_bytes() -> int:
    """Largest upload the API accepts, ``MAX_UPLOAD_MB`` megabytes (default 500)."""
    try:
        megabytes = int(os.environ.get("MAX_UPLOAD_MB", "500"))
    except ValueError:
        megabytes = 500
    return max(megabytes, 1) * 1024 * 1024


def is_data_file(path: Path) -> bool:
    """Whether *path* is a database file or a SQL dump the folder handles."""
    if path.name.startswith("."):
        return False
    suffix = path.suffix.lower()
    return suffix in DATABASE_EXTENSIONS or suffix == SQL_DUMP_EXTENSION


def is_database_file(path: Path) -> bool:
    return path.name[:1] != "." and path.suffix.lower() in DATABASE_EXTENSIONS


def connection_type(path: Path) -> str:
    """``sqlite`` or ``duckdb`` for a database file."""
    return DATABASE_EXTENSIONS[path.suffix.lower()]


def database_name(path: Path) -> str:
    """The name the file's connection and catalog database go by: its stem.

    Both connectors derive their database name from the file's stem, so the
    stored connection and the connector agree on it.
    """
    return path.stem


def file_connection(path: Path) -> dict[str, Any]:
    """The connection object a database file is stored as."""
    return {
        "type": connection_type(path),
        "database": database_name(path),
        "path": str(path),
    }


def resolve_inside_data_dir(path: str) -> Path:
    """*path* as an absolute path, which must lie inside the data folder.

    A file connection may only point into the folder that was mounted for the
    purpose; otherwise a connection request could open any file the container
    can read.
    """
    resolved = Path(path).resolve()
    root = data_dir().resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"File connections must point inside {root}")
    return resolved


def safe_filename(name: str) -> str:
    """A bare file name that is safe to create in the data folder.

    Keeps letters, digits, dots, dashes, underscores and spaces, drops any
    directory part, and requires a supported extension.
    """
    base = Path(name.replace("\\", "/")).name.strip()
    base = _FILENAME_UNSAFE.sub("_", base).lstrip(".").strip()
    path = Path(base)
    if not base or not is_data_file(path):
        supported = ", ".join([*DATABASE_EXTENSIONS, SQL_DUMP_EXTENSION])
        raise ValueError(f"Unsupported file. Use one of: {supported}")
    return base


def looks_like_database(path: Path) -> bool:
    """Whether the file's header matches the database format its extension claims.

    A cheap check that catches a renamed CSV or a truncated upload before
    ingestion fails on it with a less helpful message.
    """
    suffix = path.suffix.lower()
    try:
        with path.open("rb") as handle:
            head = handle.read(16)
    except OSError:
        return False
    if suffix in DATABASE_EXTENSIONS:
        if DATABASE_EXTENSIONS[suffix] == "duckdb":
            return head[8:12] == _DUCKDB_MAGIC
        return head == _SQLITE_MAGIC
    return False


def converted_path(dump: Path) -> Path:
    """Where a SQL dump's database is written: the same name, ``.sqlite``."""
    return dump.with_suffix(".sqlite")


def convert_dump(dump: Path) -> Path | None:
    """Build the SQLite database a ``.sql`` dump describes, next to the dump.

    Returns the new file, or ``None`` when an up-to-date one is already there.
    The database is built under a hidden temporary name and renamed into place,
    so a watcher never sees it half-written. Raises ``sqlite3.Error`` when the
    dump is not valid SQLite SQL.
    """
    target = converted_path(dump)
    if target.exists() and target.stat().st_mtime_ns >= dump.stat().st_mtime_ns:
        return None

    temp = dump.with_name(f".{dump.stem}-{uuid.uuid4().hex[:8]}.converting")
    try:
        connection = sqlite3.connect(temp)
        try:
            connection.executescript(dump.read_text(encoding="utf-8", errors="replace"))
            connection.commit()
        finally:
            connection.close()
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def error_marker(path: Path) -> Path:
    """The hidden file that records why a file could not be processed."""
    return path.with_name(f".{path.name}.error")
