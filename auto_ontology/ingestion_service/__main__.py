# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Ingestion service.

Serves a FastAPI app exposing ingest and delete-ingest endpoints, and runs two
background schedulers via the app lifespan:

* :class:`DataScheduler` — data ingestion, triggerable via ``POST /ingest``.
* :class:`SemanticScheduler` — semantic compilation over the catalog that
  :class:`DataScheduler` writes to the store, triggerable via
  ``POST /semantic/compile``. Its first pass waits for
  :class:`DataScheduler`'s first pass to finish (see ``semantic_scheduler.py``)
  so the two, which both start at the same moment on boot, can't race.

Each runs once at startup and afterwards only on demand; nothing recurs on a
timer. Connections are reloaded from the catalog on every pass.

Usage::

    uv run --no-sync python -m auto_ontology.ingestion_service
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from auto_ontology.env import load_env

load_env()

from auto_ontology.dal.schema_version import require_current_schema  # noqa: E402
from auto_ontology.ingestion_service.config import (  # noqa: E402
    is_semantic_compilation_enabled,
)
from auto_ontology.ingestion_service.data_scheduler import DataScheduler  # noqa: E402
from auto_ontology.ingestion_service.ingest import ingest_database  # noqa: E402
from auto_ontology.ingestion_service.router import (  # noqa: E402
    _start_or_trigger,
    router,
)
from auto_ontology.ingestion_service.semantic_scheduler import SemanticScheduler  # noqa: E402
from auto_ontology.neem_folder import config as neem_config  # noqa: E402
from auto_ontology.neem_folder.watcher import NeemFolderWatcher  # noqa: E402
from auto_ontology.version import get_app_version  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Same gate as the API server: this service writes the catalog, so against a
    # schema it does not expect every ingest fails partway through instead of
    # not starting. Worse here than there, because a scheduler runs unattended —
    # nobody is watching a request come back 500, so the failure surfaces as an
    # empty catalog hours later.
    require_current_schema()

    # uvicorn owns SIGINT/SIGTERM; each scheduler exposes a stop() that unwinds
    # its in-flight wait promptly on shutdown. Schedulers are stored on
    # app.state so the router can trigger them on demand.
    data_scheduler = DataScheduler()
    # Waits for the ingest scheduler's first pass before compiling (see
    # semantic_scheduler.py) so the two starting at the same moment on boot
    # can't race — otherwise the very first compile could run against a
    # catalog that ingest hasn't written yet.
    semantic_scheduler = SemanticScheduler(depends_on=data_scheduler)
    app.state.data_scheduler = data_scheduler
    app.state.semantic_scheduler = semantic_scheduler

    data_scheduler.start()
    # Only start semantic compilation if it's enabled in settings. When a user
    # enables it later, the POST /semantic/compile trigger starts the scheduler
    # on demand, so no restart is needed.
    if is_semantic_compilation_enabled():
        semantic_scheduler.start()
        logger.info("semantic: compilation enabled; scheduler started")
    else:
        logger.info(
            "semantic: compilation disabled; scheduler idle "
            "(enable it in Settings → Semantic Compilation)"
        )
    neem_watcher = _start_neem_watcher(semantic_scheduler)
    app.state.neem_watcher = neem_watcher
    try:
        yield
    finally:
        if neem_watcher is not None:
            await neem_watcher.stop()
        await data_scheduler.stop()
        await semantic_scheduler.stop()
        logger.info("ingestion_service: shutting down")


def _start_neem_watcher(
    semantic_scheduler: SemanticScheduler,
) -> NeemFolderWatcher | None:
    """Watch the NEEM folder when one is configured (``NEEM_DATA_DIR``).

    The watcher re-ingests the merged database on its own thread after a
    change, then hands back to the loop to start a compilation pass -- the same
    follow-up ``POST /ingest`` gives a connection saved in the UI.
    """
    directory = neem_config.data_dir()
    if directory is None:
        return None
    loop = asyncio.get_running_loop()

    def _compile_after_ingest() -> None:
        if is_semantic_compilation_enabled():
            loop.call_soon_threadsafe(_start_or_trigger, semantic_scheduler)

    watcher = NeemFolderWatcher(
        directory,
        ingest=lambda: ingest_database(neem_config.database_name()),
        on_changed=_compile_after_ingest,
    )
    watcher.start()
    return watcher


app = FastAPI(title="neemontology Ingestion Service", lifespan=lifespan)
app.include_router(router)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info(
        "Starting neemontology Ingestion Service — app version %s", get_app_version()
    )
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("INGESTION_PORT", "3002")),
        log_config=None,
    )


if __name__ == "__main__":
    main()
