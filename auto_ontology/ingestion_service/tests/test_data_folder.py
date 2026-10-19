# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The data folder watcher: what it registers, when, and what it leaves alone."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from auto_ontology.infra.data_files import error_marker
from auto_ontology.ingestion_service import data_folder
from auto_ontology.ingestion_service.data_folder import DataFolderWatcher


class _World:
    """The catalog's connections and what the watcher did to the outside."""

    def __init__(self) -> None:
        self.stored: dict[str, dict[str, Any]] = {}
        self.refreshes = 0
        self.ingested: list[str] = []
        self.clock = 1000.0


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _World:
    state = _World()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_FOLDER_SETTLE_SECONDS", "5")

    def insert(*, connection: str, database_name: str) -> dict[str, Any]:
        state.stored[database_name] = json.loads(connection)
        return {}

    def refresh() -> bool:
        state.refreshes += 1
        return True

    def trigger(connection: dict[str, Any], *, on_done: Any = None) -> None:
        state.ingested.append(str(connection["database"]))

    monkeypatch.setattr(
        data_folder, "list_connections", lambda: list(state.stored.values())
    )
    monkeypatch.setattr(data_folder, "insert_connection", insert)
    monkeypatch.setattr(data_folder, "refresh_api_server_caches", refresh)
    monkeypatch.setattr(
        "auto_ontology.ingestion_service.ingest.trigger_ingest", trigger
    )
    monkeypatch.setattr(data_folder.time, "monotonic", lambda: state.clock)
    return state


def _wait_for_refresh(world: _World) -> None:
    """At startup the refresh runs on a thread, so as not to hold the service up."""
    for _ in range(100):
        if world.refreshes:
            return
        time.sleep(0.05)
    raise AssertionError("the API server was never asked to refresh")


def _sqlite(path: Path, rows: int = 1) -> Path:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
    connection.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(rows)])
    connection.commit()
    connection.close()
    return path


def test_files_present_at_startup_are_registered_but_not_ingested(
    world: _World, tmp_path: Path
) -> None:
    """The data scheduler's own startup pass ingests them; doing it here too would double it."""
    path = _sqlite(tmp_path / "pickup_neem.sqlite")

    DataFolderWatcher().scan_once(startup=True)

    assert world.stored["pickup_neem"] == {
        "type": "sqlite",
        "database": "pickup_neem",
        "path": str(path),
    }
    assert world.ingested == []
    _wait_for_refresh(world)


def test_a_known_file_at_startup_is_left_alone(world: _World, tmp_path: Path) -> None:
    _sqlite(tmp_path / "a.sqlite")
    watcher = DataFolderWatcher()
    watcher.scan_once(startup=True)
    _wait_for_refresh(world)
    world.refreshes = 0

    DataFolderWatcher().scan_once(startup=True)

    assert world.refreshes == 0
    assert world.ingested == []


def test_a_new_file_waits_until_it_stops_changing(
    world: _World, tmp_path: Path
) -> None:
    watcher = DataFolderWatcher()
    watcher.scan_once(startup=True)

    path = _sqlite(tmp_path / "late.sqlite")
    watcher.scan_once(startup=False)
    assert world.stored == {}  # just appeared: might still be being copied

    world.clock += 3
    watcher.scan_once(startup=False)
    assert world.stored == {}  # not settled yet

    world.clock += 3
    watcher.scan_once(startup=False)
    assert world.stored["late"]["path"] == str(path)
    assert world.ingested == ["late"]


def test_a_file_that_keeps_growing_is_not_read(world: _World, tmp_path: Path) -> None:
    watcher = DataFolderWatcher()
    watcher.scan_once(startup=True)
    path = _sqlite(tmp_path / "copying.sqlite")

    for _ in range(4):
        watcher.scan_once(startup=False)
        world.clock += 3
        _sqlite(path)  # every poll sees a different size or time

    assert world.stored == {}


def test_a_changed_file_is_ingested_again(world: _World, tmp_path: Path) -> None:
    path = _sqlite(tmp_path / "a.sqlite")
    watcher = DataFolderWatcher()
    watcher.scan_once(startup=True)

    _sqlite(path, rows=50)
    watcher.scan_once(startup=False)
    world.clock += 6
    watcher.scan_once(startup=False)

    assert world.ingested == ["a"]
    world.clock += 6
    watcher.scan_once(startup=False)
    assert world.ingested == ["a"]  # settled and handled: no repeats


def test_a_file_that_is_not_a_database_is_flagged_not_registered(
    world: _World, tmp_path: Path
) -> None:
    bad = tmp_path / "notes.sqlite"
    bad.write_text("just text")

    DataFolderWatcher().scan_once(startup=True)

    assert world.stored == {}
    assert "not a valid" in error_marker(bad).read_text().lower()


def test_a_second_file_with_the_same_name_is_not_added(
    world: _World, tmp_path: Path
) -> None:
    _sqlite(tmp_path / "neem.sqlite")
    DataFolderWatcher().scan_once(startup=True)
    other = tmp_path / "neem.db"
    _sqlite(other)

    DataFolderWatcher().scan_once(startup=True)

    assert world.stored["neem"]["path"].endswith("neem.sqlite")
    assert "already exists" in error_marker(other).read_text()


def test_a_dump_is_converted_and_the_result_registered(
    world: _World, tmp_path: Path
) -> None:
    (tmp_path / "neem.sql").write_text("CREATE TABLE a (id INTEGER);")

    watcher = DataFolderWatcher()
    watcher.scan_once(startup=True)
    assert (tmp_path / "neem.sqlite").exists()

    watcher.scan_once(startup=True)  # the next poll
    assert "neem" in world.stored


def test_a_bad_dump_is_flagged(world: _World, tmp_path: Path) -> None:
    dump = tmp_path / "bad.sql"
    dump.write_text("NOPE;")

    DataFolderWatcher().scan_once(startup=True)

    assert world.stored == {}
    assert "Not a valid SQLite dump" in error_marker(dump).read_text()


def test_deleting_a_file_keeps_its_connection(world: _World, tmp_path: Path) -> None:
    path = _sqlite(tmp_path / "keep.sqlite")
    watcher = DataFolderWatcher()
    watcher.scan_once(startup=True)

    path.unlink()
    world.clock += 10
    watcher.scan_once(startup=False)

    assert "keep" in world.stored
    assert world.ingested == []


def test_a_missing_folder_is_not_an_error(
    world: _World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "nope"))
    DataFolderWatcher().scan_once(startup=True)
    assert world.stored == {}
