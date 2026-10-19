# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Listing, uploading and removing database files in the data folder."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from auto_ontology.infra.data_files import error_marker
from auto_ontology.server.connections import files


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The stored connections and per-database table counts, as the DAL returns them."""
    state: dict[str, Any] = {"connections": [], "tables": {}, "deleted": []}
    monkeypatch.setattr(files, "list_connections", lambda: state["connections"])
    monkeypatch.setattr(files, "table_counts_by_database", lambda: state["tables"])

    def delete(name: str) -> dict[str, str]:
        state["deleted"].append(name)
        return {"database_name": name}

    monkeypatch.setattr(files.service, "delete_connection", delete)
    return state


def _sqlite_bytes(path: Path) -> bytes:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE t (id INTEGER)")
    connection.commit()
    connection.close()
    data = path.read_bytes()
    path.unlink()
    return data


async def _chunks(data: bytes, size: int = 1024) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


def _upload(name: str, data: bytes) -> dict[str, Any]:
    return asyncio.run(files.save_upload(name, _chunks(data)))


def test_an_uploaded_database_lands_in_the_folder(
    folder: Path, catalog: dict[str, Any]
) -> None:
    data = _sqlite_bytes(folder / "src.sqlite")

    row = _upload("../sneaky/neem 1.sqlite", data)

    assert (folder / "neem 1.sqlite").read_bytes() == data
    assert row["name"] == "neem 1.sqlite"
    assert row["status"] == "pending"
    assert [p.name for p in folder.iterdir()] == ["neem 1.sqlite"]  # no temp left


def test_a_file_that_is_not_a_database_is_refused(
    folder: Path, catalog: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="not a valid sqlite"):
        _upload("fake.sqlite", b"id,name\n1,x\n")

    assert list(folder.iterdir()) == []


def test_an_unsupported_name_and_an_empty_file_are_refused(
    folder: Path, catalog: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        _upload("data.csv", b"x")
    with pytest.raises(ValueError, match="empty"):
        _upload("a.sqlite", b"")
    assert list(folder.iterdir()) == []


def test_an_upload_over_the_limit_is_refused(
    folder: Path, catalog: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")

    with pytest.raises(files.UploadTooLarge):
        _upload("big.sql", b"x" * (2 * 1024 * 1024))

    assert list(folder.iterdir()) == []


def test_a_dump_can_be_uploaded(folder: Path, catalog: dict[str, Any]) -> None:
    row = _upload("neem.sql", b"CREATE TABLE a (id INTEGER);")

    assert row["kind"] == "sql"
    assert row["status"] == "converting"


def test_status_follows_the_catalog(folder: Path, catalog: dict[str, Any]) -> None:
    data = _sqlite_bytes(folder / "src.sqlite")
    for name in ("new.sqlite", "reading.sqlite", "done.sqlite"):
        (folder / name).write_bytes(data)
    for name in ("reading", "done"):
        catalog["connections"].append(
            {"type": "sqlite", "database": name, "path": str(folder / f"{name}.sqlite")}
        )
    catalog["tables"] = {"done": 12}

    by_name = {row["name"]: row["status"] for row in files.list_files()}

    assert by_name == {
        "done.sqlite": "ready",
        "new.sqlite": "pending",
        "reading.sqlite": "ingesting",
    }


def test_errors_and_missing_files_are_reported(
    folder: Path, catalog: dict[str, Any]
) -> None:
    bad = folder / "bad.sqlite"
    bad.write_text("nope")
    error_marker(bad).write_text("Not a valid SQLite or DuckDB database file.")
    catalog["connections"].append(
        {"type": "sqlite", "database": "gone", "path": str(folder / "gone.sqlite")}
    )

    rows = {row["name"]: row for row in files.list_files()}

    assert rows["bad.sqlite"]["status"] == "failed"
    assert "Not a valid" in rows["bad.sqlite"]["error"]
    assert rows["gone.sqlite"]["status"] == "missing"
    assert rows["gone.sqlite"]["size_bytes"] is None
    assert ".bad.sqlite.error" not in rows


def test_a_converted_dump_is_listed_once(folder: Path, catalog: dict[str, Any]) -> None:
    (folder / "neem.sql").write_text("CREATE TABLE a (id INTEGER);")
    (folder / "neem.sqlite").write_bytes(_sqlite_bytes(folder / "x.sqlite"))

    assert [row["name"] for row in files.list_files()] == ["neem.sqlite"]


def test_removing_a_file_removes_its_database_too(
    folder: Path, catalog: dict[str, Any]
) -> None:
    path = folder / "neem.sqlite"
    path.write_bytes(_sqlite_bytes(folder / "x.sqlite"))
    (folder / "neem.sql").write_text("CREATE TABLE a (id INTEGER);")
    catalog["connections"].append(
        {"type": "sqlite", "database": "neem", "path": str(path)}
    )

    assert files.remove_file("neem.sqlite") is True

    assert list(folder.iterdir()) == []  # the dump would only be converted again
    assert catalog["deleted"] == ["neem"]


def test_removing_something_unknown_reports_not_found(
    folder: Path, catalog: dict[str, Any]
) -> None:
    assert files.remove_file("nothing.sqlite") is False
    for hostile in ("../etc/passwd", "sub/neem.sqlite", ".hidden.sqlite"):
        with pytest.raises(ValueError):
            files.remove_file(hostile)
