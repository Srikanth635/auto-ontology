# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Uploading into, listing and deleting from the NEEM folder.

The upload is the part that can go wrong quietly: a rejected or oversized file
must leave nothing in the folder, since anything there is something the watcher
will try to load.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from auto_ontology.server.neem_files import service


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("NEEM_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        service,
        "get_neem_status",
        lambda: {
            "catalog": "idle",
            "files": [{"name": "a.sqlite", "state": "loaded", "rows": 4}],
        },
    )
    return tmp_path


def _sqlite_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "source.bin"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()
    data = path.read_bytes()
    path.unlink()
    return data


def _upload(name: str, data: bytes, chunk: int = 1000) -> dict:
    async def chunks() -> AsyncIterator[bytes]:
        for i in range(0, len(data), chunk):
            yield data[i : i + chunk]

    return asyncio.run(service.save_upload(name, chunks()))


def test_an_upload_lands_under_its_name_and_is_listed(folder: Path) -> None:
    data = _sqlite_bytes(folder)
    result = _upload("a.sqlite", data)

    assert result["name"] == "a.sqlite"
    assert (folder / "a.sqlite").read_bytes() == data
    assert [p.name for p in folder.iterdir()] == ["a.sqlite"]
    listed = service.list_files()
    assert listed["enabled"] is True
    assert listed["files"][0] | {"modified_at": None} == {
        "name": "a.sqlite",
        "size": len(data),
        "modified_at": None,
        "state": "loaded",
        "error": None,
        "rows": 4,
    }


def test_a_file_that_is_not_sqlite_is_refused_and_leaves_nothing(folder: Path) -> None:
    with pytest.raises(service.NeemFolderError) as exc:
        _upload("a.sqlite", b"hello world" * 100)
    assert exc.value.status_code == 400
    assert list(folder.iterdir()) == []


def test_an_oversized_upload_is_refused_and_leaves_nothing(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEEM_MAX_UPLOAD_MB", "1")
    with pytest.raises(service.NeemFolderError) as exc:
        _upload("big.sqlite", b"\x00" * (1024 * 1024 + 1), chunk=64 * 1024)
    assert exc.value.status_code == 413
    assert list(folder.iterdir()) == []


@pytest.mark.parametrize("name", ["../x.sqlite", ".x.sqlite", "x.exe"])
def test_unsafe_names_are_refused(folder: Path, name: str) -> None:
    with pytest.raises(service.NeemFolderError) as exc:
        _upload(name, _sqlite_bytes(folder))
    assert exc.value.status_code == 400


def test_a_sql_dump_upload_is_accepted(folder: Path) -> None:
    _upload("run.sql", b'BEGIN TRANSACTION;\nCREATE TABLE "x" (a INTEGER);\nCOMMIT;\n')
    assert (folder / "run.sql").exists()


def test_delete_removes_the_file_and_404s_when_missing(folder: Path) -> None:
    _upload("a.sqlite", _sqlite_bytes(folder))
    service.delete_file("a.sqlite")
    assert list(folder.iterdir()) == []
    with pytest.raises(service.NeemFolderError) as exc:
        service.delete_file("a.sqlite")
    assert exc.value.status_code == 404


def test_without_a_folder_the_list_says_so_and_uploads_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEEM_DATA_DIR", raising=False)
    assert service.list_files()["enabled"] is False
    with pytest.raises(service.NeemFolderError) as exc:
        _upload("a.sqlite", b"x")
    assert exc.value.status_code == 503
