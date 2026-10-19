# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""API routes for the NEEM folder: list, upload and delete NEEM files."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Request

from auto_ontology.server.neem_files import service
from auto_ontology.server.responses import (
    NeemFileItem,
    NeemFilesResponse,
    StatusResponse,
)

router = APIRouter()

_FILE_NAME = Path(
    ..., description="File name in the NEEM folder, e.g. pickup_neem.sqlite"
)


@router.get("/neem-files", response_model=NeemFilesResponse)
def list_neem_files() -> dict[str, Any]:
    """List the NEEM files in the folder and how far each one has got.

    Every file in the folder is merged into one database (``database``). A
    file's ``state`` is ``waiting`` while it is still changing, then
    ``loading``, then ``loaded`` or ``failed`` (with ``error``). ``unknown``
    means the ingestion service could not be asked. ``catalog`` is
    ``ingesting`` while the merged database is being re-read after a change.
    """
    return service.list_files()


@router.put("/neem-files/{file_name}", status_code=201, response_model=NeemFileItem)
async def upload_neem_file(
    request: Request, file_name: str = _FILE_NAME
) -> dict[str, Any]:
    """Upload a NEEM file: the request body is the file's raw bytes.

    Accepts a SQLite database (``.sqlite``, ``.sqlite3``, ``.db``) or a SQLite
    ``.sql`` dump, up to ``max_upload_bytes``. A file of the same name is
    replaced. The ingestion service picks the file up within a few seconds and
    merges it; poll ``GET /neem-files`` for its state.
    """
    try:
        return await service.save_upload(file_name, request.stream())
    except service.NeemFolderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/neem-files/{file_name}", response_model=StatusResponse)
def delete_neem_file(file_name: str = _FILE_NAME) -> dict[str, str]:
    """Delete a NEEM file. Its rows leave the merged database on the next poll."""
    try:
        service.delete_file(file_name)
    except service.NeemFolderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"status": "ok"}
