# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Which files in the NEEM folder count."""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_ontology.neem_folder import files


def _touch(directory: Path, name: str) -> None:
    (directory / name).write_bytes(b"x")


def test_scan_keeps_databases_and_dumps_and_skips_everything_else(
    tmp_path: Path,
) -> None:
    for name in (
        "a.sqlite",
        "b.db",
        "c.sqlite3",
        "d.sql",
        "notes.txt",
        ".a.sqlite.part",
    ):
        _touch(tmp_path, name)
    (tmp_path / "sub").mkdir()
    _touch(tmp_path / "sub", "nested.sqlite")

    assert [f.name for f in files.scan(tmp_path)] == [
        "a.sqlite",
        "b.db",
        "c.sqlite3",
        "d.sql",
    ]


def test_a_dump_beside_its_database_is_skipped(tmp_path: Path) -> None:
    _touch(tmp_path, "pickup.sqlite")
    _touch(tmp_path, "pickup.sql")
    _touch(tmp_path, "other.sql")

    assert [f.name for f in files.scan(tmp_path)] == ["other.sql", "pickup.sqlite"]


def test_scan_of_a_missing_folder_is_empty(tmp_path: Path) -> None:
    assert files.scan(tmp_path / "nope") == []


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("pickup_neem.sqlite", True),
        ("Run 3 - kitchen.db", True),
        ("x.SQL", True),
        ("../escape.sqlite", False),
        ("dir/x.sqlite", False),
        (".hidden.sqlite", False),
        ("x.txt", False),
        ("x.duckdb", False),
    ],
)
def test_valid_names(name: str, valid: bool) -> None:
    assert files.is_valid_name(name) is valid


def test_content_sniffing() -> None:
    assert files.looks_like_sqlite(files.SQLITE_MAGIC + b"\x10\x00")
    assert not files.looks_like_sqlite(b"BEGIN TRANSACTION;")
    assert files.looks_like_sql_dump(b'BEGIN TRANSACTION;\nCREATE TABLE "x" (a);')
    # A multi-byte character cut off by the end of the sample is still text.
    assert files.looks_like_sql_dump(b"caf\xc3")
    assert not files.looks_like_sql_dump(files.SQLITE_MAGIC)
