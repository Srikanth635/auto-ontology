# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small synthetic NEEMs and a throwaway merged database for the tests.

The NEEMs mimic what the real ones look like: ORM-generated tables named
``*DAO``, an integer ``database_id`` surrogate key starting at 1 in every file,
joined-table inheritance (a child's primary key is also a foreign key to its
parent), a unique natural key, and the SQLite storage quirks -- booleans as
0/1, JSON and UUIDs as text.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from auto_ontology.neem_folder import config, merge
from auto_ontology.neem_folder.files import NeemFile

SCHEMA = """
CREATE TABLE "AgentDAO" (
    database_id INTEGER NOT NULL,
    name VARCHAR(255),
    PRIMARY KEY (database_id),
    UNIQUE (name)
);
CREATE TABLE "RobotDAO" (
    database_id INTEGER NOT NULL,
    active BOOLEAN,
    PRIMARY KEY (database_id),
    FOREIGN KEY(database_id) REFERENCES "AgentDAO" (database_id)
);
CREATE TABLE "TaskDAO" (
    database_id INTEGER NOT NULL,
    agent_id INTEGER,
    payload JSON,
    uid UUID,
    started DATETIME,
    PRIMARY KEY (database_id),
    FOREIGN KEY(agent_id) REFERENCES "AgentDAO" (database_id)
);
CREATE TABLE "EmptyDAO" (
    database_id INTEGER NOT NULL,
    PRIMARY KEY (database_id)
);
"""


def make_neem(
    path: Path,
    *,
    robot: str = "pr2",
    tasks: int = 2,
    extra_column: bool = False,
    extra_table: bool = False,
) -> NeemFile:
    """Write a NEEM with one robot (agent id 1) and *tasks* tasks it ran."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    if extra_column:
        conn.execute('ALTER TABLE "TaskDAO" ADD COLUMN outcome VARCHAR(255)')
    if extra_table:
        conn.execute(
            'CREATE TABLE "GripperDAO" (database_id INTEGER NOT NULL, '
            "robot_id INTEGER, PRIMARY KEY (database_id), "
            'FOREIGN KEY(robot_id) REFERENCES "RobotDAO" (database_id))'
        )
        conn.execute('INSERT INTO "GripperDAO" VALUES (1, 1)')
    conn.execute('INSERT INTO "AgentDAO" VALUES (1, ?)', (robot,))
    conn.execute('INSERT INTO "RobotDAO" VALUES (1, 1)')
    for i in range(tasks):
        values = [
            i + 2,
            1,
            '{"step": %d}' % i,
            uuid.uuid4().hex,
            "2026-10-14 12:56:59.465872",
        ]
        if extra_column:
            values.append("success")
        conn.execute(
            f'INSERT INTO "TaskDAO" VALUES ({", ".join("?" * len(values))})', values
        )
    conn.commit()
    conn.close()
    return as_neem_file(path)


def as_neem_file(path: Path) -> NeemFile:
    stat = path.stat()
    return NeemFile(path.name, path, stat.st_size, stat.st_mtime_ns)


def dump(source: Path, target: Path) -> NeemFile:
    """Write *source* as a ``sqlite3 .dump``-style SQL script."""
    conn = sqlite3.connect(source)
    target.write_text("\n".join(conn.iterdump()), encoding="utf-8")
    conn.close()
    return as_neem_file(target)


@pytest.fixture
def neem_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A merged database of its own for one test, dropped afterwards."""
    if not os.environ.get("POSTGRES_USER"):
        pytest.skip("POSTGRES_* not set")
    name = f"neem_test_{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("NEEM_DATABASE", name)
    try:
        merge.ensure_database()
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    yield name
    with psycopg.connect(config.maintenance_conninfo(), autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(name)
            )
        )


def query(statement: str, *params: object) -> list[tuple]:
    """Run a read against the test's merged database."""
    with psycopg.connect(config.connection_string()) as conn:
        return conn.execute(statement, params).fetchall()
