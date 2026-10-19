# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP API routes for the ingestion service."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from auto_ontology.ingestion_service.config import is_semantic_compilation_enabled
from auto_ontology.ingestion_service.history import (
    get_last_failure_if_most_recent,
    get_last_successful_run,
)
from auto_ontology.ingestion_service.ingest import (
    trigger_delete_ingest,
    trigger_ingest,
    trigger_reset_semantic,
)
from auto_ontology.ingestion_service.reembed import reembed_status, trigger_reembed
from auto_ontology.server.health.checks import check_schema, check_store
from auto_ontology.server.responses import (
    HealthResponse,
    ReembedStatusResponse,
    SemanticRunningResponse,
    StatusResponse,
)

router = APIRouter()


@router.get(
    "/health",
    include_in_schema=False,
    responses={
        200: {"model": HealthResponse, "description": "All dependencies reachable"},
        503: {"model": HealthResponse, "description": "Postgres or schema unusable"},
    },
)
async def health() -> JSONResponse:
    """Readiness probe: can this service actually ingest right now?

    Same path and same meaning as the API server's ``/api/health``, on purpose.
    The two used to disagree — bare ``/health`` was liveness here and readiness
    there — so the same-looking path meant opposite things and a probe config
    copied between the two charts would have been silently wrong.

    Reports the same two checks the API server does, from the same helpers,
    because both services depend on the same database and the same migrated
    schema and should not be able to disagree about them.
    """
    postgres = check_store()
    migrations = check_schema()
    ready = postgres["status"] == "ok" and migrations["status"] == "ok"
    body: dict[str, Any] = {
        "status": "ok" if ready else "degraded",
        "postgres": postgres,
        "migrations": migrations,
    }
    return JSONResponse(status_code=200 if ready else 503, content=body)


@router.get("/health/live", include_in_schema=False, response_model=StatusResponse)
async def liveness() -> dict[str, str]:
    """Liveness only: no dependency is checked, and this must never fail.

    Restarting the process cannot fix an unreachable database, so making this
    depend on one converts a database blip into a rolling restart. Mirrors the
    API server's ``/api/health/live`` exactly.
    """
    return {"status": "ok"}


def _start_or_trigger(scheduler: Any) -> None:
    """Run a compilation pass now, starting the job first if it is idle."""
    # start() performs an immediate first run on its own. Only ask for an extra
    # run when the job was already started; otherwise the first run and the
    # trigger would compile twice.
    if not scheduler.start():
        scheduler.trigger()


@router.post("/ingest", status_code=202, response_model=StatusResponse)
async def ingest_connection(
    request: Request, connection: dict[str, Any] = Body(...)
) -> dict[str, str]:
    """Trigger a non-blocking ingest for a single connection.

    When semantic compilation is on, a compilation pass follows the ingest so
    the new or changed database gets its semantic layer straight away.
    """
    scheduler = request.app.state.semantic_scheduler
    loop = asyncio.get_running_loop()

    def _compile_after_ingest() -> None:
        if is_semantic_compilation_enabled():
            loop.call_soon_threadsafe(_start_or_trigger, scheduler)

    trigger_ingest(connection, on_done=_compile_after_ingest)
    return {"status": "accepted"}


@router.post("/ingest/delete", status_code=202, response_model=StatusResponse)
async def ingest_delete(database_name: str) -> dict[str, str]:
    """Trigger a non-blocking reset of a database's ingested data.

    ``database_name`` is required: this endpoint always targets one database.
    """
    trigger_delete_ingest(database_name)
    return {"status": "accepted"}


@router.post("/semantic/reset", status_code=202, response_model=StatusResponse)
async def semantic_reset(
    request: Request, database_name: str | None = None
) -> dict[str, str]:
    """Trigger a non-blocking reset of a database's semantic layer.

    Deletes the semantic nodes and embeddings, then asks for a compilation pass
    so the layer is rebuilt straight away.
    Omitting ``database_name`` resets every database.

    The three steps are strictly ordered — stop the running pass, wait for it to
    stop, delete, then rebuild — and run as a background task, so this returns
    immediately while the wait can take minutes. They used to overlap, which
    lost data in both directions: a pass reads its work list once at the start,
    so one beginning before the delete finished saw every table still carrying a
    Term and compiled nothing, while a pass still running during the delete kept
    writing Terms it had already swept past.
    """
    trigger_reset_semantic(request.app.state.semantic_scheduler, database_name)
    return {"status": "accepted"}


@router.post("/semantic/compile", status_code=202, response_model=StatusResponse)
async def semantic_compile(request: Request) -> dict[str, str]:
    """Trigger a non-blocking semantic compilation pass.

    Ensures the scheduler is running first (``start()`` is idempotent), so this
    also takes effect when compilation is enabled while the service is already
    up — no restart needed. Runs on the scheduler's own task.
    """
    _start_or_trigger(request.app.state.semantic_scheduler)
    return {"status": "accepted"}


@router.get("/semantic/status", response_model=SemanticRunningResponse)
async def semantic_status(request: Request) -> dict[str, bool | str | None]:
    """Report whether a compilation pass is executing right now, when the last
    one finished successfully, and when it last failed (if that's more recent
    than the last success).

    Backed by the ``semantic_compilation_history`` table (see ``history.py``),
    which this service owns — the neemontology API server relays this response rather
    than reading that table itself.
    """
    scheduler = request.app.state.semantic_scheduler
    return {
        "running": scheduler.running,
        "last_success_at": get_last_successful_run(),
        "last_failure_at": get_last_failure_if_most_recent(),
    }


@router.post("/semantic/stop", status_code=202, response_model=StatusResponse)
async def semantic_stop(request: Request) -> dict[str, str]:
    """Ask the in-flight semantic compilation pass to stop.

    The database being compiled finishes first — that work runs in a thread that
    cannot be interrupted — so the pass ends at the next database boundary. The
    job stays alive and runs again on the next trigger.
    """
    request.app.state.semantic_scheduler.abort()
    return {"status": "accepted"}


@router.post("/reembed", status_code=202, response_model=StatusResponse)
async def reembed() -> dict[str, str]:
    """Rebuild every stored vector with the current embedding model.

    Runs in the background. Called when the embedding model changes; a request
    made while a pass is running queues one more pass after it.
    """
    trigger_reembed()
    return {"status": "accepted"}


@router.get("/reembed/status", response_model=ReembedStatusResponse)
async def reembed_state() -> dict[str, Any]:
    """Whether a re-embed pass is running, and how the last one ended."""
    return reembed_status()
