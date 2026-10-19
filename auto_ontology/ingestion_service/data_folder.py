# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Watch the data folder and turn the database files in it into connections.

A SQLite or DuckDB file placed in ``DATA_DIR`` (``/data``, the repo's ``data/``
folder) becomes a connection named after the file, and is ingested. Replacing
the file ingests it again. A ``.sql`` dump of a SQLite database is first turned
into a ``.sqlite`` next to it.

The folder is polled rather than watched for change events: Docker Desktop does
not forward file-system events through a bind mount from Windows or macOS, so
event-based watching would silently never fire there.

A file is only touched once its size and modification time have stopped moving
for a few seconds, so a copy that is still in progress is never read.

Removing a file does **not** remove its connection or its ingested data. The
descriptions curated on top of it are worth more than the file, and one stray
delete in a file manager should not take them away. The UI's remove button is
the way to drop a database.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from auto_ontology.dal.connections import insert_connection, list_connections
from auto_ontology.infra.data_files import (
    SQL_DUMP_EXTENSION,
    convert_dump,
    data_dir,
    database_name,
    error_marker,
    file_connection,
    is_data_file,
    is_database_file,
    looks_like_database,
)

logger = logging.getLogger(__name__)

DEFAULT_API_SERVER_URL = "http://localhost:3001"
_REFRESH_ATTEMPTS = 5


@dataclass
class _Seen:
    """What the watcher knows about one file."""

    signature: tuple[int, int]  # (mtime_ns, size)
    changed_at: float  # monotonic time the signature last moved
    handled: tuple[int, int] | None = None  # signature already acted on


def _poll_seconds() -> float:
    return _env_seconds("DATA_FOLDER_POLL_SECONDS", 3.0)


def _settle_seconds() -> float:
    return _env_seconds("DATA_FOLDER_SETTLE_SECONDS", 3.0)


def _env_seconds(name: str, default: float) -> float:
    try:
        return max(float(os.environ.get(name, default)), 0.0)
    except ValueError:
        return default


def refresh_api_server_caches() -> bool:
    """Tell the API server to reload its connectors; ``True`` once it has.

    The API server keeps connectors, and the chat workers built on them, in
    memory. A connection registered here is invisible to it until they are
    rebuilt, and without that a question about the new database could not find
    a connector to run its SQL on. Retried briefly because on startup the API
    server may still be coming up.
    """
    base = os.environ.get("API_SERVER_URL", DEFAULT_API_SERVER_URL).rstrip("/")
    url = f"{base}/api/connections/refresh"
    for attempt in range(1, _REFRESH_ATTEMPTS + 1):
        try:
            httpx.post(url, timeout=10.0).raise_for_status()
            return True
        except Exception as exc:
            logger.info(
                "data folder: API server not ready to refresh (%s), attempt %d/%d",
                exc,
                attempt,
                _REFRESH_ATTEMPTS,
            )
            time.sleep(min(2.0 * attempt, 10.0))
    logger.warning(
        "data folder: could not reach the API server at %s; restart the stack to "
        "make new databases queryable",
        url,
    )
    return False


def _stored_connection_named(name: str) -> dict[str, Any] | None:
    key = name.casefold()
    return next(
        (
            conn
            for conn in list_connections()
            if str(conn.get("database") or "").casefold() == key
        ),
        None,
    )


class DataFolderWatcher:
    """Polls the data folder; see the module docstring for the rules."""

    def __init__(self, on_ingested: Callable[[], None] | None = None) -> None:
        self._on_ingested = on_ingested
        self._seen: dict[Path, _Seen] = {}
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._warned_missing = False
        self._warned_env = False

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    async def _run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=_poll_seconds())
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            try:
                await asyncio.to_thread(self.scan_once, startup=False)
            except Exception:
                logger.exception("data folder: scan failed")

    # ---- one pass --------------------------------------------------------

    def scan_once(self, *, startup: bool) -> None:
        """Look at the folder once and act on files that have settled.

        With *startup* set, files are registered but not ingested: the data
        scheduler's startup pass ingests every connection anyway, and doing it
        here as well would ingest each new file twice.
        """
        folder = data_dir()
        if not folder.is_dir():
            if not self._warned_missing:
                logger.info("data folder: %s does not exist; nothing to watch", folder)
                self._warned_missing = True
            return
        self._warned_missing = False

        if os.environ.get("CONNECTION_STRINGS", "").strip() and not self._warned_env:
            logger.warning(
                "data folder: CONNECTION_STRINGS is set, so ingestion uses it and "
                "ignores the files in %s. Empty it in .env to use data files.",
                folder,
            )
            self._warned_env = True

        now = time.monotonic()
        settle = _settle_seconds()
        present: set[Path] = set()
        registered_any = False
        ingest: list[dict[str, Any]] = []

        # Dumps first, so a database made from one is picked up in the same pass
        # it appears rather than a poll later.
        entries = sorted(
            (p for p in folder.iterdir() if p.is_file() and is_data_file(p)),
            key=lambda p: (p.suffix.lower() != SQL_DUMP_EXTENSION, p.name),
        )
        for path in entries:
            try:
                stat = path.stat()
            except OSError:
                continue
            present.add(path)
            signature = (stat.st_mtime_ns, stat.st_size)
            seen = self._seen.get(path)
            if seen is None:
                # At startup nothing is mid-copy that we could know about, so a
                # file already there counts as settled.
                seen = _Seen(signature, now - settle if startup else now)
                self._seen[path] = seen
            elif seen.signature != signature:
                seen.signature = signature
                seen.changed_at = now
                seen.handled = None
            if seen.handled == seen.signature or now - seen.changed_at < settle:
                continue

            seen.handled = seen.signature
            try:
                if path.suffix.lower() == SQL_DUMP_EXTENSION:
                    self._convert(path)
                else:
                    outcome = self._register(path, startup=startup)
                    if outcome is not None:
                        registered_any = registered_any or outcome[0]
                        if outcome[1] is not None:
                            ingest.append(outcome[1])
            except Exception:
                logger.exception("data folder: could not process %s", path.name)
                error_marker(path).write_text("Could not be processed; see the log.")

        for gone in set(self._seen) - present:
            del self._seen[gone]

        if registered_any or ingest:
            if startup:
                # The API server may still be starting, and the retries inside
                # can take half a minute: do not hold up this service's own
                # startup for it.
                threading.Thread(
                    target=refresh_api_server_caches,
                    name="data-folder-refresh",
                    daemon=True,
                ).start()
            else:
                refresh_api_server_caches()
        for connection in ingest:
            self._ingest(connection)

    # ---- actions ---------------------------------------------------------

    def _convert(self, dump: Path) -> None:
        marker = error_marker(dump)
        try:
            produced = convert_dump(dump)
        except (sqlite3.Error, OSError, UnicodeError) as exc:
            logger.warning("data folder: could not convert %s: %s", dump.name, exc)
            marker.write_text(f"Not a valid SQLite dump: {exc}")
            return
        marker.unlink(missing_ok=True)
        if produced is not None:
            logger.info("data folder: converted %s to %s", dump.name, produced.name)
            # Written whole and renamed into place, so there is nothing to wait
            # for: the next poll can register it straight away.
            stat = produced.stat()
            self._seen[produced] = _Seen(
                (stat.st_mtime_ns, stat.st_size), time.monotonic() - _settle_seconds()
            )

    def _register(
        self, path: Path, *, startup: bool
    ) -> tuple[bool, dict[str, Any] | None] | None:
        """Make sure *path* is a connection.

        Returns ``(newly_registered, connection_to_ingest)``, or ``None`` when
        the file cannot be used.
        """
        marker = error_marker(path)
        if not is_database_file(path):
            return None
        if not looks_like_database(path):
            logger.warning("data folder: %s is not a valid database file", path.name)
            marker.write_text("Not a valid SQLite or DuckDB database file.")
            return None

        name = database_name(path)
        stored = _stored_connection_named(name)
        connection = file_connection(path)
        if stored is None:
            insert_connection(connection=json.dumps(connection), database_name=name)
            marker.unlink(missing_ok=True)
            logger.info("data folder: added database %r from %s", name, path.name)
            return True, None if startup else connection

        if str(stored.get("path") or "") != str(path):
            logger.warning(
                "data folder: %s not added, a database named %r already exists",
                path.name,
                name,
            )
            marker.write_text(
                f"A database named {name!r} already exists. Rename the file."
            )
            return None

        marker.unlink(missing_ok=True)
        if startup:
            return False, None
        logger.info("data folder: %s changed; ingesting again", path.name)
        return False, stored

    def _ingest(self, connection: dict[str, Any]) -> None:
        # Imported here: the ingest module pulls in the whole pipeline.
        from auto_ontology.ingestion_service.ingest import trigger_ingest

        trigger_ingest(connection, on_done=self._on_ingested)
