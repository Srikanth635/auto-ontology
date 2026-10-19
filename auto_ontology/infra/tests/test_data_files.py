# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The data folder's file rules: which files count, and how they map to connections."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from auto_ontology.connectors.connection_string_factory import build_connection_string
from auto_ontology.infra import data_files


@pytest.fixture(autouse=True)
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def _sqlite(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE t (id INTEGER)")
    connection.commit()
    connection.close()
    return path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("neem.sqlite", "neem.sqlite"),
        ("../../etc/neem.db", "neem.db"),
        ("C:\\Users\\me\\neem 1.duckdb", "neem 1.duckdb"),
        ("we!rd#name.SQL", "we_rd_name.SQL"),
        (".hidden.sqlite", "hidden.sqlite"),
    ],
)
def test_safe_filename_keeps_a_bare_supported_name(raw: str, expected: str) -> None:
    assert data_files.safe_filename(raw) == expected


@pytest.mark.parametrize("raw", ["notes.txt", "data.csv", "", "..", "noextension"])
def test_safe_filename_rejects_other_files(raw: str) -> None:
    with pytest.raises(ValueError):
        data_files.safe_filename(raw)


def test_a_file_connection_is_named_after_the_file(folder: Path) -> None:
    path = folder / "pickup_neem.sqlite"
    assert data_files.file_connection(path) == {
        "type": "sqlite",
        "database": "pickup_neem",
        "path": str(path),
    }
    assert data_files.connection_type(folder / "x.duckdb") == "duckdb"


def test_hidden_and_foreign_files_are_not_data_files(folder: Path) -> None:
    assert not data_files.is_data_file(folder / ".upload-1.tmp")
    assert not data_files.is_data_file(folder / ".x.sqlite")
    assert not data_files.is_data_file(folder / "readme.md")
    assert data_files.is_data_file(folder / "a.SQLITE")
    assert data_files.is_data_file(folder / "a.sql")


def test_header_check_matches_the_claimed_format(folder: Path) -> None:
    good = _sqlite(folder / "a.sqlite")
    fake = folder / "b.sqlite"
    fake.write_text("id,name\n1,x\n")
    duck = folder / "c.duckdb"
    duck.write_bytes(good.read_bytes())  # SQLite bytes under a DuckDB name

    assert data_files.looks_like_database(good)
    assert not data_files.looks_like_database(fake)
    assert not data_files.looks_like_database(duck)


def test_a_dump_becomes_a_sqlite_next_to_it(folder: Path) -> None:
    dump = folder / "neem.sql"
    dump.write_text("CREATE TABLE a (id INTEGER); INSERT INTO a VALUES (1), (2);")

    built = data_files.convert_dump(dump)

    assert built == folder / "neem.sqlite"
    connection = sqlite3.connect(built)
    assert connection.execute("SELECT count(*) FROM a").fetchone() == (2,)
    connection.close()
    # Nothing half-built is left behind, and an up-to-date result is not redone.
    assert [p.name for p in folder.iterdir() if p.name.startswith(".")] == []
    assert data_files.convert_dump(dump) is None


def test_a_bad_dump_raises_and_leaves_no_database(folder: Path) -> None:
    dump = folder / "bad.sql"
    dump.write_text("THIS IS NOT SQL;")

    with pytest.raises(sqlite3.Error):
        data_files.convert_dump(dump)

    assert not (folder / "bad.sqlite").exists()
    assert list(folder.glob(".*converting")) == []


def test_file_connections_must_point_inside_the_folder(folder: Path) -> None:
    inside = folder / "x.sqlite"
    assert build_connection_string(
        {"type": "sqlite", "database": "x", "path": str(inside)}
    ).startswith("sqlite:///")
    assert build_connection_string(
        {"type": "duckdb", "database": "x", "path": str(folder / "x.duckdb")}
    ).startswith("duckdb://")

    for elsewhere in ("/etc/passwd", str(folder / ".." / "other.sqlite")):
        with pytest.raises(ValueError, match="inside"):
            build_connection_string(
                {"type": "sqlite", "database": "x", "path": elsewhere}
            )
