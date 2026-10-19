# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Merging NEEMs into one database.

The rules worth guarding are the ones a wrong answer would hide behind: ids
from two NEEMs must never meet in a join, a removal must take exactly one
file's rows, and a NEEM that cannot be merged must leave the database as it was.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from auto_ontology.neem_folder import merge
from auto_ontology.neem_folder.tests.neem_fixtures import (
    as_neem_file,
    dump,
    make_neem,
    neem_db,  # noqa: F401 -- fixture
    query,
)

pytestmark = pytest.mark.usefixtures("neem_db")


def test_the_first_neem_keeps_its_ids_and_later_ones_get_their_own_range(
    tmp_path: Path,
) -> None:
    first = merge.load_file(make_neem(tmp_path / "a.sqlite", tasks=2))
    second = merge.load_file(make_neem(tmp_path / "b.sqlite", tasks=3))

    assert first.id_offset == 0
    assert second.id_offset >= 4  # past a.sqlite's highest id (3)
    ids = query('SELECT neem_source_id, database_id FROM "TaskDAO" ORDER BY 2')
    assert [i for s, i in ids if s == first.source_id] == [2, 3]
    assert all(i > second.id_offset for s, i in ids if s == second.source_id)
    assert len({i for _, i in ids}) == len(ids)


def test_foreign_keys_are_shifted_with_the_keys_they_point_at(tmp_path: Path) -> None:
    merge.load_file(make_neem(tmp_path / "a.sqlite"))
    merge.load_file(make_neem(tmp_path / "b.sqlite"))

    crossing = query(
        'SELECT count(*) FROM "TaskDAO" t JOIN "AgentDAO" a '
        "ON a.database_id = t.agent_id WHERE a.neem_source_id <> t.neem_source_id"
    )
    joined = query(
        'SELECT count(*) FROM "TaskDAO" t JOIN "AgentDAO" a ON a.database_id = t.agent_id'
    )
    assert crossing == [(0,)]
    assert joined == [(4,)]


def test_a_unique_natural_key_is_unique_per_neem(tmp_path: Path) -> None:
    # Both NEEMs name their robot "pr2", which UNIQUE (name) allows per file.
    merge.load_file(make_neem(tmp_path / "a.sqlite", robot="pr2"))
    merge.load_file(make_neem(tmp_path / "b.sqlite", robot="pr2"))

    assert query('SELECT count(*) FROM "AgentDAO" WHERE name = %s', "pr2") == [(2,)]


def test_sqlite_storage_quirks_arrive_as_proper_postgres_types(tmp_path: Path) -> None:
    merge.load_file(make_neem(tmp_path / "a.sqlite", tasks=1))

    (active,) = query('SELECT active FROM "RobotDAO"')[0]
    payload, uid, started = query('SELECT payload, uid, started FROM "TaskDAO"')[0]
    assert active is True
    assert payload == {"step": 0}
    assert len(str(uid)) == 36
    assert started.year == 2026


def test_reloading_a_changed_file_replaces_its_rows_and_keeps_its_range(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.sqlite"
    merge.load_file(make_neem(tmp_path / "b.sqlite", tasks=1))
    before = merge.load_file(make_neem(path, tasks=3))
    path.unlink()
    after = merge.load_file(make_neem(path, tasks=2))

    assert after.source_id == before.source_id
    assert after.id_offset == before.id_offset
    counts = dict(query('SELECT neem_source_id, count(*) FROM "TaskDAO" GROUP BY 1'))
    assert counts[after.source_id] == 2


def test_removing_a_file_takes_exactly_its_rows(tmp_path: Path) -> None:
    keep = merge.load_file(make_neem(tmp_path / "keep.sqlite", tasks=2))
    merge.load_file(make_neem(tmp_path / "drop.sqlite", tasks=5))

    assert merge.remove_file("drop.sqlite") is True
    assert merge.remove_file("drop.sqlite") is False
    for table in ("AgentDAO", "RobotDAO", "TaskDAO"):
        sources = query(f'SELECT DISTINCT neem_source_id FROM "{table}"')
        assert sources == [(keep.source_id,)], table
    assert set(merge.loaded_sources()) == {"keep.sqlite"}


def test_the_schema_grows_with_tables_and_columns_from_later_neems(
    tmp_path: Path,
) -> None:
    merge.load_file(make_neem(tmp_path / "old.sqlite"))
    newer = merge.load_file(
        make_neem(tmp_path / "new.sqlite", extra_column=True, extra_table=True)
    )

    outcomes = query('SELECT neem_source_id, outcome FROM "TaskDAO" ORDER BY 1')
    assert {o for s, o in outcomes if s == newer.source_id} == {"success"}
    assert {o for s, o in outcomes if s != newer.source_id} == {None}
    assert query('SELECT count(*) FROM "GripperDAO"') == [(1,)]


def test_a_sql_dump_loads_like_the_database_it_came_from(tmp_path: Path) -> None:
    source = make_neem(tmp_path / "a.sqlite", tasks=2)
    result = merge.load_file(dump(source.path, tmp_path / "a_dump.sql"))

    assert result.rows == 1 + 1 + 2  # one agent, one robot, two tasks
    assert query('SELECT count(*) FROM "EmptyDAO"') == [(0,)]


def test_a_neem_that_breaks_its_own_foreign_keys_changes_nothing(
    tmp_path: Path,
) -> None:
    merge.load_file(make_neem(tmp_path / "good.sqlite"))
    bad_path = tmp_path / "bad.sqlite"
    make_neem(bad_path)
    conn = sqlite3.connect(bad_path)
    conn.execute('UPDATE "TaskDAO" SET agent_id = 99')
    conn.commit()
    conn.close()

    with pytest.raises(merge.NeemLoadError, match="foreign keys"):
        merge.load_file(as_neem_file(bad_path))
    assert set(merge.loaded_sources()) == {"good.sqlite"}
    assert query('SELECT count(*) FROM "TaskDAO"') == [(2,)]


def test_a_file_that_is_not_sqlite_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "junk.sqlite"
    path.write_bytes(b"not a database at all" * 100)

    with pytest.raises(merge.NeemLoadError, match="SQLite"):
        merge.load_file(as_neem_file(path))
