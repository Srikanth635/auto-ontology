# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Database files in the data folder: list, upload, remove.

Uploading only writes the file. The ingestion service's folder watcher notices
it and does the rest, so a file put there by hand and one dropped on the page
take the same path.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from auto_ontology.dal.connections import list_connections, table_counts_by_database
from auto_ontology.infra.data_files import (
    DATABASE_EXTENSIONS,
    SQL_DUMP_EXTENSION,
    connection_type,
    converted_path,
    data_dir,
    database_name,
    error_marker,
    is_data_file,
    is_database_file,
    looks_like_database,
    max_upload_bytes,
    safe_filename,
)
from auto_ontology.server.connections import service

logger = logging.getLogger(__name__)

_READ_ERROR_LIMIT = 500


class UploadTooLarge(ValueError):
    """The upload went past ``MAX_UPLOAD_MB``."""


def _read_error(path: Path) -> str | None:
    try:
        text = error_marker(path).read_text(errors="replace").strip()
    except OSError:
        return None
    return text[:_READ_ERROR_LIMIT] or None


def _file_connections() -> dict[str, dict[str, Any]]:
    """Stored file connections, by lower-cased database name."""
    return {
        str(conn.get("database") or "").casefold(): conn
        for conn in list_connections()
        if conn.get("type") in ("sqlite", "duckdb")
    }


def list_files() -> list[dict[str, Any]]:
    """Every file in the data folder with its loading status.

    A SQL dump whose database has been built is left out: the database stands
    for it. Connections whose file has disappeared are listed as ``missing`` so
    the data they hold can still be removed from the page.
    """
    folder = data_dir()
    connections = _file_connections()
    tables = {name.casefold(): n for name, n in table_counts_by_database().items()}
    rows: list[dict[str, Any]] = []
    listed: set[str] = set()

    paths = sorted(folder.iterdir()) if folder.is_dir() else []
    for path in paths:
        if not path.is_file() or not is_data_file(path):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        error = _read_error(path)
        row: dict[str, Any] = {
            "name": path.name,
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
            "error": error,
        }

        if path.suffix.lower() == SQL_DUMP_EXTENSION:
            if converted_path(path).exists():
                continue
            rows.append(
                {
                    **row,
                    "kind": "sql",
                    "database_name": converted_path(path).stem,
                    "status": "failed" if error else "converting",
                }
            )
            continue

        name = database_name(path)
        key = name.casefold()
        stored = connections.get(key)
        listed.add(key)
        if error:
            status = "failed"
        elif stored is None or str(stored.get("path") or "") != str(path):
            status = "pending"
        elif tables.get(key, 0) > 0:
            status = "ready"
        else:
            status = "ingesting"
        rows.append(
            {
                **row,
                "kind": connection_type(path),
                "database_name": name,
                "status": status,
            }
        )

    for key, stored in connections.items():
        if key in listed:
            continue
        stored_path = Path(str(stored.get("path") or ""))
        if stored_path.exists():
            continue
        rows.append(
            {
                "name": stored_path.name or str(stored.get("database") or ""),
                "kind": str(stored.get("type") or ""),
                "size_bytes": None,
                "modified_at": None,
                "database_name": str(stored.get("database") or ""),
                "status": "missing",
                "error": None,
            }
        )
    return rows


async def save_upload(filename: str, chunks: AsyncIterator[bytes]) -> dict[str, Any]:
    """Write an uploaded file into the data folder and return its listing row.

    The body is written under a hidden temporary name and renamed into place, so
    the folder watcher never sees a partial file, and it is checked against its
    extension's file format before it is accepted. Replacing a file of the same
    name is allowed: the watcher then ingests the new contents.
    """
    name = safe_filename(filename)
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    limit = max_upload_bytes()
    target = folder / name
    temp = folder / f".upload-{uuid.uuid4().hex}.tmp"

    written = 0
    try:
        with temp.open("wb") as handle:
            async for chunk in chunks:
                written += len(chunk)
                if written > limit:
                    raise UploadTooLarge(
                        f"File is larger than the {limit // (1024 * 1024)} MB limit"
                    )
                handle.write(chunk)
        if written == 0:
            raise ValueError("The file is empty")

        # `looks_like_database` goes by the suffix, which the temp name lacks.
        probe = temp.with_name(f"{temp.name}{target.suffix.lower()}")
        os.replace(temp, probe)
        temp = probe
        if is_database_file(target) and not looks_like_database(probe):
            kind = DATABASE_EXTENSIONS[target.suffix.lower()]
            raise ValueError(f"This is not a valid {kind} database file")

        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)

    logger.info("data folder: received %s (%d bytes)", name, written)
    listed = next((row for row in list_files() if row["name"] == name), None)
    if listed is not None:
        return listed
    # A SQL dump already converted is listed under its database, not its own name.
    return {
        "name": name,
        "kind": "sql" if target.suffix.lower() == SQL_DUMP_EXTENSION else "",
        "size_bytes": written,
        "modified_at": None,
        "database_name": database_name(target),
        "status": "pending",
        "error": None,
    }


def remove_file(filename: str) -> bool:
    """Delete a file and, with it, the database loaded from it.

    The connection and everything ingested from the file go as well: a file the
    app still described would be a database with nothing behind it. ``False``
    when there is neither a file nor a connection by that name.
    """
    folder = data_dir()
    name = Path(filename.replace("\\", "/")).name
    path = folder / name
    if name != filename or name.startswith("."):
        raise ValueError("Not a file name")

    found = False
    candidates = [path]
    if path.suffix.lower() == SQL_DUMP_EXTENSION:
        candidates.append(converted_path(path))
    elif is_database_file(path):
        dump = path.with_suffix(SQL_DUMP_EXTENSION)
        if dump.exists():
            candidates.append(dump)

    for candidate in candidates:
        if candidate.is_file():
            candidate.unlink()
            found = True
        error_marker(candidate).unlink(missing_ok=True)

    stored = _file_connections().get(database_name(path).casefold())
    if stored is not None and service.delete_connection(str(stored["database"])):
        found = True
    return found
