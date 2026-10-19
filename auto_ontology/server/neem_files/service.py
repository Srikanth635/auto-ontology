# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The NEEM folder as the API sees it: list, upload into, delete from.

This side only touches files. Loading them is the ingestion service's watcher
(``auto_ontology.neem_folder.watcher``), so a file copied into the folder by
hand and one uploaded here take exactly the same path from then on.

An upload is streamed to ``.<name>.part`` -- invisible to the watcher, which
ignores dot-files -- and renamed into place only once it is complete and its
header checks out. The watcher therefore never sees a partial upload, and a
rejected one leaves nothing behind.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from auto_ontology.neem_folder import config
from auto_ontology.neem_folder.files import (
    DUMP_SUFFIXES,
    is_valid_name,
    looks_like_sql_dump,
    looks_like_sqlite,
    scan,
)
from auto_ontology.server.ingestion.proxy import get_neem_status

logger = logging.getLogger(__name__)

# Enough to see the SQLite header, or to judge whether a dump is text.
_HEAD_BYTES = 4096


class NeemFolderError(Exception):
    """A request the folder cannot satisfy; ``status_code`` is the HTTP answer."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _directory() -> Path:
    directory = config.data_dir()
    if directory is None:
        raise NeemFolderError(
            503, "No NEEM folder is configured. Set NEEM_DATA_DIR (Compose sets /data)."
        )
    return directory


def _checked_name(file_name: str) -> str:
    if not is_valid_name(file_name):
        raise NeemFolderError(
            400,
            "Use a plain file name ending in .sqlite, .sqlite3, .db or .sql "
            "(letters, digits, '.', '-', '_' and spaces).",
        )
    return file_name


def list_files() -> dict[str, Any]:
    """The folder's NEEM files, merged with the watcher's state for each."""
    directory = config.data_dir()
    if directory is None:
        return {
            "enabled": False,
            "database": config.database_name(),
            "catalog": "idle",
            "max_upload_bytes": config.max_upload_bytes(),
            "files": [],
        }

    status = get_neem_status() or {}
    states = {item["name"]: item for item in status.get("files", [])}
    files = []
    for file in scan(directory):
        state = states.get(file.name, {})
        files.append(
            {
                "name": file.name,
                "size": file.size,
                "modified_at": datetime.fromtimestamp(
                    file.mtime_ns / 1e9, UTC
                ).isoformat(),
                "state": state.get("state", "unknown" if not status else "waiting"),
                "error": state.get("error"),
                "rows": state.get("rows"),
            }
        )
    return {
        "enabled": True,
        "database": config.database_name(),
        "catalog": status.get("catalog", "idle"),
        "max_upload_bytes": config.max_upload_bytes(),
        "files": files,
    }


def _validate_head(file_name: str, head: bytes) -> None:
    if Path(file_name).suffix.lower() in DUMP_SUFFIXES:
        if not looks_like_sql_dump(head):
            raise NeemFolderError(400, "This .sql file is not a text SQL dump.")
    elif not looks_like_sqlite(head):
        raise NeemFolderError(400, "This file is not a SQLite database.")


async def save_upload(file_name: str, chunks: AsyncIterator[bytes]) -> dict[str, Any]:
    """Stream an upload into the folder, replacing a file of the same name."""
    directory = _directory()
    name = _checked_name(file_name)
    limit = config.max_upload_bytes()
    target = directory / name
    partial = directory / f".{name}.part"

    size = 0
    head = b""
    try:
        with partial.open("wb") as handle:
            async for chunk in chunks:
                if not chunk:
                    continue
                size += len(chunk)
                if size > limit:
                    raise NeemFolderError(
                        413,
                        f"The file is larger than the {limit // (1024 * 1024)} MB limit.",
                    )
                if len(head) < _HEAD_BYTES:
                    head += chunk[: _HEAD_BYTES - len(head)]
                await asyncio.to_thread(handle.write, chunk)
            await asyncio.to_thread(handle.flush)
            await asyncio.to_thread(os.fsync, handle.fileno())
        if size == 0:
            raise NeemFolderError(400, "The file is empty.")
        _validate_head(name, head)
        os.replace(partial, target)
    except NeemFolderError:
        partial.unlink(missing_ok=True)
        raise
    except OSError as exc:
        partial.unlink(missing_ok=True)
        logger.exception("neem: could not write %s", target)
        raise NeemFolderError(
            500, f"Could not write to the NEEM folder: {exc}"
        ) from exc

    logger.info("neem: received %s (%d bytes)", name, size)
    stat = target.stat()
    return {
        "name": name,
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        "state": "waiting",
    }


def delete_file(file_name: str) -> None:
    """Remove a file from the folder; the watcher then deletes its rows."""
    directory = _directory()
    path = directory / _checked_name(file_name)
    if not path.is_file():
        raise NeemFolderError(404, f"No NEEM file named {file_name!r}.")
    try:
        path.unlink()
    except OSError as exc:
        raise NeemFolderError(500, f"Could not delete {file_name!r}: {exc}") from exc
    logger.info("neem: deleted %s", file_name)
