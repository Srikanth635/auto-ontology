# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Poll the NEEM folder and keep the merged database in step with it.

Polling, not file-system events: the folder is a bind mount, and Docker Desktop
does not deliver inotify events from a Windows or macOS host into a container.
A listing every few seconds costs nothing at this scale.

A file is acted on only once it is *stable* -- the same size and modification
time on two consecutive polls -- so a NEEM still being copied in is never read
half-written. Then:

* a file the database does not hold, or holds with a different SHA-256, is
  loaded (replacing the earlier version);
* a file whose size or mtime changed but whose content did not just has its
  fingerprint updated;
* a file the database holds but the folder no longer has is removed.

After a pass that changed anything, the merged database is re-ingested into
the catalog and *on_changed* runs (the service uses it to start a semantic
compilation pass when that is enabled).

A file that fails to load is not retried until it changes: the same bytes would
fail the same way on every poll.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from auto_ontology.neem_folder import config, merge
from auto_ontology.neem_folder.files import NeemFile, scan, sha256

logger = logging.getLogger(__name__)

STATE_WAITING = "waiting"
STATE_LOADING = "loading"
STATE_LOADED = "loaded"
STATE_FAILED = "failed"


@dataclass
class FileStatus:
    """What the watcher knows about one file, as reported by ``GET /neem/status``."""

    name: str
    state: str
    error: str | None = None
    rows: int | None = None
    updated_at: float = 0.0


class NeemFolderWatcher:
    """The polling loop. One per ingestion-service process."""

    def __init__(
        self,
        directory: Path,
        *,
        ingest: Callable[[], None],
        on_changed: Callable[[], None] | None = None,
        poll_seconds: float | None = None,
    ) -> None:
        self._directory = directory
        self._ingest = ingest
        self._on_changed = on_changed
        self._poll_seconds = poll_seconds or config.poll_seconds()
        self._previous: dict[str, tuple[int, int]] = {}
        # Fingerprints of files that failed, so they are retried only on change.
        self._failed: dict[str, tuple[int, int]] = {}
        self._status: dict[str, FileStatus] = {}
        self._catalog_state = "idle"
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    async def _run_forever(self) -> None:
        logger.info(
            "neem: watching %s every %.0fs (database %s)",
            self._directory,
            self._poll_seconds,
            config.database_name(),
        )
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self.poll_once)
            except Exception:
                logger.exception("neem: poll failed; will retry")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                pass

    # -- status --------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Per-file states plus whether the catalog is being refreshed."""
        return {
            "directory": str(self._directory),
            "database": config.database_name(),
            "catalog": self._catalog_state,
            "files": [
                asdict(s) for s in sorted(self._status.values(), key=lambda s: s.name)
            ],
        }

    def _set(self, name: str, state: str, **extra: Any) -> None:
        self._status[name] = FileStatus(
            name=name, state=state, updated_at=time.time(), **extra
        )

    # -- the pass --------------------------------------------------------------

    def poll_once(self) -> bool:
        """One pass over the folder. Returns whether the database changed."""
        current = {f.name: f for f in scan(self._directory)}
        stable: dict[str, NeemFile] = {}
        for name, file in current.items():
            if self._previous.get(name) == file.fingerprint:
                stable[name] = file
            elif name not in self._status or self._status[name].state != STATE_LOADING:
                self._set(name, STATE_WAITING)
        self._previous = {name: f.fingerprint for name, f in current.items()}

        loaded = merge.loaded_sources()
        changed = False

        for name in sorted(set(loaded) - set(current)):
            merge.remove_file(name)
            self._status.pop(name, None)
            self._failed.pop(name, None)
            changed = True

        for name, file in stable.items():
            if self._failed.get(name) == file.fingerprint:
                continue
            record = loaded.get(name)
            if (
                record is not None
                and (record.file_size, record.file_mtime_ns) == file.fingerprint
            ):
                if (
                    name not in self._status
                    or self._status[name].state == STATE_WAITING
                ):
                    self._set(name, STATE_LOADED, rows=record.row_count)
                continue
            try:
                digest = sha256(file.path)
            except OSError as exc:
                # Gone or locked between the listing and the read; next poll decides.
                logger.warning("neem: cannot read %s yet: %s", name, exc)
                continue
            if record is not None and record.sha256 == digest:
                merge.update_fingerprint(file)
                self._set(name, STATE_LOADED, rows=record.row_count)
                continue

            self._set(name, STATE_LOADING)
            try:
                merge.ensure_database()
                result = merge.load_file(file, digest=digest)
            except merge.NeemLoadError as exc:
                self._fail(file, str(exc))
                continue
            except Exception as exc:
                logger.exception("neem: loading %s failed", name)
                self._fail(file, f"{type(exc).__name__}: {exc}")
                continue
            self._failed.pop(name, None)
            self._set(name, STATE_LOADED, rows=result.rows)
            changed = True

        for name in list(self._status):
            if name not in current:
                self._status.pop(name)

        if changed:
            self._refresh_catalog()
        return changed

    def _fail(self, file: NeemFile, error: str) -> None:
        logger.warning("neem: could not load %s: %s", file.name, error)
        self._failed[file.name] = file.fingerprint
        self._set(file.name, STATE_FAILED, error=error)

    def _refresh_catalog(self) -> None:
        self._catalog_state = "ingesting"
        try:
            self._ingest()
            if self._on_changed is not None:
                self._on_changed()
        except Exception:
            logger.exception("neem: re-ingesting %s failed", config.database_name())
        finally:
            self._catalog_state = "idle"
