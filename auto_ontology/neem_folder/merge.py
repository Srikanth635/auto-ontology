# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Merge SQLite NEEMs into one Postgres database.

Every NEEM is a SQLite database produced by the same ORM, so they share most of
their schema and all of their surrogate keys start at 1. Merging them into one
database therefore has three problems to solve, and this module's rules are the
answer to each:

**Keys would collide.** Each file gets an *id offset*: every single-column
integer primary key, and every foreign key pointing at one, is shifted by it on
the way in. The first file gets offset 0 and keeps its original ids; each later
one starts past the highest id range in use. Joins stay single-column and
correct, which is what matters to generated SQL -- a composite join that one
forgot to qualify would silently mix NEEMs instead of failing.

**Some keys are not ids.** A primary key or ``UNIQUE`` constraint that is not
made up of shifted columns (a name, a composite of plain integers) cannot be
made unique by an offset, so in Postgres it gets ``neem_source_id`` appended:
it is unique *within one NEEM*, which is what it meant in the source. A
foreign key into such a key carries ``neem_source_id`` on both sides.

**Rows have to be removable per file.** Every table gets a ``neem_source_id``
column naming the ``neem_sources`` row it came from, so deleting or replacing a
file deletes exactly its rows. It also lets a question be scoped to one NEEM.

The schema grows as files arrive -- a table or column first seen in a later NEEM
is created then -- and never shrinks: a table every remaining file lacks is left
in place, empty. Columns are nullable apart from primary keys, because a column
added for one NEEM is absent from the ones loaded before it.

Foreign keys are ``DEFERRABLE INITIALLY DEFERRED``: a file is loaded in one
transaction, table by table in name order, and the check runs at commit.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import tempfile
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from auto_ontology.neem_folder import config
from auto_ontology.neem_folder.files import NeemFile, sha256

logger = logging.getLogger(__name__)

SOURCES_TABLE = "neem_sources"
SOURCE_COLUMN = "neem_source_id"

# Postgres truncates identifiers longer than this silently, which would merge
# two distinct long names into one. Refuse instead.
_MAX_IDENTIFIER_BYTES = 63

# Serialises loads and removals across processes. An arbitrary constant: the
# merged database holds nothing else that takes advisory locks.
_LOCK_KEY = 7_465_736_001


class NeemLoadError(Exception):
    """A NEEM file that cannot be merged, with a message meant for the user."""


# --- Reading the SQLite side --------------------------------------------------


@dataclass(frozen=True)
class SqliteForeignKey:
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


@dataclass
class SqliteTable:
    name: str
    #: ``(column name, declared type)`` in definition order.
    columns: list[tuple[str, str]]
    primary_key: tuple[str, ...]
    foreign_keys: list[SqliteForeignKey] = field(default_factory=list)
    uniques: list[tuple[str, ...]] = field(default_factory=list)

    def declared_type(self, column: str) -> str:
        return next((t for name, t in self.columns if name == column), "")


def _quote_sqlite(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def read_schema(conn: sqlite3.Connection) -> dict[str, SqliteTable]:
    """Tables, keys and unique constraints of a SQLite database."""
    names = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    tables: dict[str, SqliteTable] = {}
    for name in names:
        quoted = _quote_sqlite(name)
        # cid, name, type, notnull, dflt_value, pk (1-based position, 0 = not in pk)
        info = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
        primary_key = tuple(
            row[1] for row in sorted((r for r in info if r[5]), key=lambda r: r[5])
        )
        table = SqliteTable(
            name=name,
            columns=[(row[1], row[2] or "") for row in info],
            primary_key=primary_key,
        )

        # id, seq, table, from, to, on_update, on_delete, match
        grouped: dict[int, list[Any]] = defaultdict(list)
        for row in conn.execute(f"PRAGMA foreign_key_list({quoted})"):
            grouped[row[0]].append(row)
        for rows in grouped.values():
            rows.sort(key=lambda r: r[1])
            table.foreign_keys.append(
                SqliteForeignKey(
                    columns=tuple(r[3] for r in rows),
                    ref_table=rows[0][2],
                    # `to` is NULL when the key references the primary key implicitly.
                    ref_columns=tuple(r[4] for r in rows if r[4] is not None),
                )
            )

        # seq, name, unique, origin, partial
        for row in conn.execute(f"PRAGMA index_list({quoted})"):
            if row[2] and row[3] == "u":
                cols = conn.execute(
                    f"PRAGMA index_info({_quote_sqlite(row[1])})"
                ).fetchall()
                table.uniques.append(
                    tuple(c[2] for c in sorted(cols, key=lambda c: c[0]))
                )
        tables[name] = table

    for table in tables.values():
        for i, fk in enumerate(table.foreign_keys):
            if not fk.ref_columns and fk.ref_table in tables:
                table.foreign_keys[i] = SqliteForeignKey(
                    fk.columns, fk.ref_table, tables[fk.ref_table].primary_key
                )
    return tables


def _is_integer_type(declared: str) -> bool:
    return "INT" in declared.upper()


def offset_columns(schema: dict[str, SqliteTable]) -> dict[str, set[str]]:
    """The columns shifted by a file's id offset, per table.

    Single-column integer primary keys, then every foreign key whose target
    columns are all shifted. A composite integer key is left alone: its parts
    are not necessarily ids, and shifting a plain number corrupts it.
    """
    shifted: dict[str, set[str]] = defaultdict(set)
    for table in schema.values():
        pk = table.primary_key
        if len(pk) == 1 and _is_integer_type(table.declared_type(pk[0])):
            shifted[table.name].add(pk[0])
    for table in schema.values():
        for fk in table.foreign_keys:
            targets = shifted.get(fk.ref_table, set())
            if fk.ref_columns and all(c in targets for c in fk.ref_columns):
                shifted[table.name].update(fk.columns)
    return dict(shifted)


def _check_identifiers(schema: dict[str, SqliteTable]) -> None:
    for table in schema.values():
        names = [table.name, *(c for c, _ in table.columns)]
        for name in names:
            if len(name.encode()) > _MAX_IDENTIFIER_BYTES:
                raise NeemLoadError(
                    f"Name longer than {_MAX_IDENTIFIER_BYTES} bytes, which "
                    f"Postgres cannot hold: {name!r} (table {table.name!r})"
                )
        if any(c == SOURCE_COLUMN for c, _ in table.columns):
            raise NeemLoadError(
                f"Table {table.name!r} already has a {SOURCE_COLUMN!r} column, "
                "which the merge reserves"
            )
    if SOURCES_TABLE in schema:
        raise NeemLoadError(
            f"The NEEM has a table named {SOURCES_TABLE!r}, which the merge reserves"
        )


def _id_span(conn: sqlite3.Connection, shifted: dict[str, set[str]]) -> int:
    """One past the largest shifted id in the file: the width of its id range."""
    highest = -1
    for table_name, columns in shifted.items():
        for column in columns:
            q = _quote_sqlite(column)
            low, high = conn.execute(
                f"SELECT MIN({q}), MAX({q}) FROM {_quote_sqlite(table_name)}"
            ).fetchone()
            if low is None:
                continue
            if not isinstance(low, int) or not isinstance(high, int):
                raise NeemLoadError(
                    f"Column {table_name}.{column} is an integer key but holds "
                    "non-integer values"
                )
            if low < 0:
                raise NeemLoadError(
                    f"Column {table_name}.{column} holds negative ids, which "
                    "cannot be shifted into a range of their own"
                )
            highest = max(highest, high)
    return max(highest + 1, 1)


@contextmanager
def open_sqlite(file: NeemFile) -> Iterator[sqlite3.Connection]:
    """A read-only connection to a NEEM, converting a ``.sql`` dump on the way.

    A dump is replayed into a temporary database outside the watched folder, so
    the folder never sees an intermediate file.
    """
    if not file.is_dump:
        uri = file.path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.DatabaseError as exc:
            conn.close()
            raise NeemLoadError(f"Not a readable SQLite database: {exc}") from exc
        try:
            yield conn
        finally:
            conn.close()
        return

    with tempfile.TemporaryDirectory(prefix="neem-") as tmp:
        conn = sqlite3.connect(Path(tmp) / "dump.sqlite")
        try:
            try:
                script = file.path.read_text(encoding="utf-8")
                conn.executescript(script)
            except (sqlite3.Error, UnicodeDecodeError) as exc:
                raise NeemLoadError(
                    f"Could not replay the SQL dump as SQLite: {exc}. Only dumps "
                    "made by `sqlite3 <file> .dump` are supported."
                ) from exc
            yield conn
        finally:
            conn.close()


# --- The Postgres side --------------------------------------------------------


def pg_type(declared: str) -> str:
    """The Postgres column type for a SQLite declared type."""
    t = declared.strip().upper()
    if _is_integer_type(t):
        return "BIGINT"
    if t.startswith(("FLOAT", "REAL", "DOUBLE", "NUMERIC", "DECIMAL")):
        return "DOUBLE PRECISION"
    if t in ("BOOLEAN", "BOOL"):
        return "BOOLEAN"
    if t == "JSON":
        return "JSONB"
    if t == "UUID":
        return "UUID"
    if t == "BLOB":
        return "BYTEA"
    if t in ("DATETIME", "TIMESTAMP"):
        return "TIMESTAMP"
    if t == "DATE":
        return "DATE"
    return "TEXT"


def _constraint_name(table: str, kind: str, parts: tuple[str, ...]) -> str:
    """A deterministic constraint name that fits in 63 bytes."""
    digest = hashlib.sha1("\0".join((table, kind, *parts)).encode()).hexdigest()[:10]
    prefix = table.encode()[:40].decode(errors="ignore")
    return f"{prefix}_{digest}_{kind}"


def _key_needs_source(key: tuple[str, ...], shifted: set[str]) -> bool:
    """Whether a key is only unique within one NEEM and needs ``neem_source_id``."""
    return not key or not all(c in shifted for c in key)


def _idents(names: list[str] | tuple[str, ...]) -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(n) for n in names)


@dataclass
class _PgState:
    """What the merged database already holds, read once per load."""

    #: table -> column -> information_schema data_type
    columns: dict[str, dict[str, str]]
    constraints: set[str]


def _read_pg_state(pg: psycopg.Connection) -> _PgState:
    columns: dict[str, dict[str, str]] = defaultdict(dict)
    for table, column, data_type in pg.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    ):
        columns[table][column] = data_type
    constraints = {
        row[0]
        for row in pg.execute(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname = 'public'"
        )
    }
    return _PgState(columns=dict(columns), constraints=constraints)


def _ensure_sources_table(pg: psycopg.Connection) -> None:
    pg.execute(
        sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {table} (
                {id} BIGINT PRIMARY KEY,
                file_name TEXT NOT NULL UNIQUE,
                file_size BIGINT NOT NULL,
                file_mtime_ns BIGINT NOT NULL,
                sha256 TEXT NOT NULL,
                id_offset BIGINT NOT NULL,
                id_span BIGINT NOT NULL,
                row_count BIGINT NOT NULL DEFAULT 0,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        ).format(table=sql.Identifier(SOURCES_TABLE), id=sql.Identifier(SOURCE_COLUMN))
    )
    pg.execute(
        sql.SQL(
            "COMMENT ON TABLE {} IS 'One row per NEEM file merged into this "
            "database. Every other table has a neem_source_id column naming the "
            "NEEM each row came from.'"
        ).format(sql.Identifier(SOURCES_TABLE))
    )


def _ensure_schema(
    pg: psycopg.Connection,
    schema: dict[str, SqliteTable],
    shifted: dict[str, set[str]],
    state: _PgState,
) -> None:
    """Create missing tables, columns and constraints for one NEEM's schema."""
    created: list[str] = []
    for table in schema.values():
        existing = state.columns.get(table.name)
        if existing is None:
            table_shifted = shifted.get(table.name, set())
            pk = table.primary_key
            pk_columns = (
                (*pk, SOURCE_COLUMN)
                if pk and _key_needs_source(pk, table_shifted)
                else pk
            )
            parts = [
                sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(pg_type(decl)))
                for name, decl in table.columns
            ]
            parts.append(
                sql.SQL("{} BIGINT NOT NULL").format(sql.Identifier(SOURCE_COLUMN))
            )
            if pk_columns:
                parts.append(sql.SQL("PRIMARY KEY ({})").format(_idents(pk_columns)))
            pg.execute(
                sql.SQL("CREATE TABLE {} ({})").format(
                    sql.Identifier(table.name), sql.SQL(", ").join(parts)
                )
            )
            pg.execute(
                sql.SQL(
                    "COMMENT ON COLUMN {}.{} IS 'The NEEM this row came from "
                    "(neem_sources.neem_source_id).'"
                ).format(sql.Identifier(table.name), sql.Identifier(SOURCE_COLUMN))
            )
            state.columns[table.name] = {
                **{name: pg_type(decl).lower() for name, decl in table.columns},
                SOURCE_COLUMN: "bigint",
            }
            created.append(table.name)
            continue
        for name, decl in table.columns:
            if name not in existing:
                pg.execute(
                    sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                        sql.Identifier(table.name),
                        sql.Identifier(name),
                        sql.SQL(pg_type(decl)),
                    )
                )
                existing[name] = pg_type(decl).lower()

    if created:
        logger.info("neem: created %d table(s)", len(created))

    # Constraints after every table exists, since a key may point at a table
    # created later in name order.
    for table in schema.values():
        table_shifted = shifted.get(table.name, set())
        for unique in table.uniques:
            key = (
                (*unique, SOURCE_COLUMN)
                if _key_needs_source(unique, table_shifted)
                else unique
            )
            name = _constraint_name(table.name, "uq", key)
            if name in state.constraints:
                continue
            pg.execute(
                sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} UNIQUE ({})").format(
                    sql.Identifier(table.name), sql.Identifier(name), _idents(key)
                )
            )
            state.constraints.add(name)

    for table in schema.values():
        for fk in table.foreign_keys:
            ref = schema.get(fk.ref_table)
            if ref is None or not fk.ref_columns:
                continue
            ref_shifted = shifted.get(ref.name, set())
            ref_keys = [ref.primary_key, *ref.uniques]
            if fk.ref_columns not in ref_keys:
                # Postgres needs a foreign key to land on a primary key or a
                # unique constraint; SQLite does not, and does not enforce them
                # by default. Leave such a reference undeclared.
                logger.debug(
                    "neem: skipping foreign key %s(%s) -> %s(%s): not a key there",
                    table.name,
                    ",".join(fk.columns),
                    ref.name,
                    ",".join(fk.ref_columns),
                )
                continue
            columns, ref_columns = fk.columns, fk.ref_columns
            if _key_needs_source(fk.ref_columns, ref_shifted):
                columns = (*columns, SOURCE_COLUMN)
                ref_columns = (*ref_columns, SOURCE_COLUMN)
            name = _constraint_name(
                table.name, "fk", (*columns, ref.name, *ref_columns)
            )
            if name in state.constraints:
                continue
            pg.execute(
                sql.SQL(
                    "ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) "
                    "REFERENCES {} ({}) DEFERRABLE INITIALLY DEFERRED"
                ).format(
                    sql.Identifier(table.name),
                    sql.Identifier(name),
                    _idents(columns),
                    sql.Identifier(ref.name),
                    _idents(ref_columns),
                )
            )
            state.constraints.add(name)


def _converter(data_type: str, offset: int | None) -> Callable[[Any], Any]:
    """Turn a SQLite value into one Postgres accepts for *data_type*.

    SQLite stores whatever it is given, so the declared type is a hint: a
    boolean arrives as 0/1 and an integer column may hold 3.0.
    """
    if offset is not None:

        def shift(value: Any) -> Any:
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            return value + offset if isinstance(value, int) else value

        return shift
    if data_type == "boolean":
        return lambda v: bool(v) if isinstance(v, (int, float)) else v
    if data_type == "bigint":
        return lambda v: int(v) if isinstance(v, float) and v.is_integer() else v
    return lambda v: v


def _copy_rows(
    pg: psycopg.Connection,
    conn: sqlite3.Connection,
    table: SqliteTable,
    pg_columns: dict[str, str],
    shifted: set[str],
    offset: int,
    source_id: int,
) -> int:
    names = [name for name, _ in table.columns]
    if not names:
        return 0
    converters = [
        _converter(pg_columns.get(name, "text"), offset if name in shifted else None)
        for name in names
    ]
    select = "SELECT {} FROM {}".format(
        ", ".join(_quote_sqlite(n) for n in names), _quote_sqlite(table.name)
    )
    copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table.name), _idents([*names, SOURCE_COLUMN])
    )
    count = 0
    with pg.cursor() as cur, cur.copy(copy_sql) as copy:
        for row in conn.execute(select):
            copy.write_row([fn(v) for fn, v in zip(converters, row)] + [source_id])
            count += 1
    return count


def _source_tables(pg: psycopg.Connection) -> list[str]:
    return [
        row[0]
        for row in pg.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = %s AND table_name <> %s",
            (SOURCE_COLUMN, SOURCES_TABLE),
        )
    ]


def _delete_source_rows(pg: psycopg.Connection, source_id: int) -> None:
    for table in _source_tables(pg):
        pg.execute(
            sql.SQL("DELETE FROM {} WHERE {} = %s").format(
                sql.Identifier(table), sql.Identifier(SOURCE_COLUMN)
            ),
            (source_id,),
        )


# --- Entry points -------------------------------------------------------------


@dataclass(frozen=True)
class LoadedSource:
    """A file the merged database holds, as recorded in ``neem_sources``."""

    source_id: int
    file_name: str
    file_size: int
    file_mtime_ns: int
    sha256: str
    row_count: int
    loaded_at: datetime


@dataclass(frozen=True)
class LoadResult:
    source_id: int
    tables: int
    rows: int
    id_offset: int


def ensure_database() -> None:
    """Create the merged database if it is not there yet."""
    if config.database_exists():
        return
    with psycopg.connect(config.maintenance_conninfo(), autocommit=True) as conn:
        try:
            conn.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(config.database_name())
                )
            )
            logger.info("neem: created database %s", config.database_name())
        except psycopg.errors.DuplicateDatabase:
            pass


def loaded_sources(conninfo: str | None = None) -> dict[str, LoadedSource]:
    """The files the merged database holds, by file name ({} before the first load)."""
    if conninfo is None:
        if not config.database_exists():
            return {}
        conninfo = config.connection_string()
    with psycopg.connect(conninfo, connect_timeout=3) as pg:
        exists = pg.execute("SELECT to_regclass(%s)", (SOURCES_TABLE,)).fetchone()
        if exists is None or exists[0] is None:
            return {}
        rows = pg.execute(
            sql.SQL(
                "SELECT {}, file_name, file_size, file_mtime_ns, sha256, row_count, "
                "loaded_at FROM {}"
            ).format(sql.Identifier(SOURCE_COLUMN), sql.Identifier(SOURCES_TABLE))
        ).fetchall()
    return {row[1]: LoadedSource(*row) for row in rows}


def update_fingerprint(file: NeemFile, conninfo: str | None = None) -> None:
    """Record a new size/mtime for a file whose content did not change."""
    with psycopg.connect(conninfo or config.connection_string()) as pg:
        pg.execute(
            sql.SQL(
                "UPDATE {} SET file_size = %s, file_mtime_ns = %s WHERE file_name = %s"
            ).format(sql.Identifier(SOURCES_TABLE)),
            (file.size, file.mtime_ns, file.name),
        )


def load_file(
    file: NeemFile, conninfo: str | None = None, digest: str | None = None
) -> LoadResult:
    """Merge one NEEM file, replacing what an earlier version of it loaded.

    All or nothing: one transaction, so a failure leaves the database as it was.
    """
    conninfo = conninfo or config.connection_string()
    digest = digest or sha256(file.path)
    with open_sqlite(file) as conn:
        schema = read_schema(conn)
        if not schema:
            raise NeemLoadError("The file has no tables")
        _check_identifiers(schema)
        shifted = offset_columns(schema)
        span = _id_span(conn, shifted)

        with psycopg.connect(conninfo) as pg:
            pg.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
            _ensure_sources_table(pg)
            sources = sql.Identifier(SOURCES_TABLE)
            source_col = sql.Identifier(SOURCE_COLUMN)

            previous = pg.execute(
                sql.SQL(
                    "SELECT {}, id_offset, id_span FROM {} WHERE file_name = %s"
                ).format(source_col, sources),
                (file.name,),
            ).fetchone()
            if previous is not None:
                _delete_source_rows(pg, previous[0])
                pg.execute(
                    sql.SQL("DELETE FROM {} WHERE {} = %s").format(sources, source_col),
                    (previous[0],),
                )

            next_id, next_offset = pg.execute(
                sql.SQL(
                    "SELECT COALESCE(MAX({}), 0) + 1, COALESCE(MAX(id_offset + id_span), 0) "
                    "FROM {}"
                ).format(source_col, sources)
            ).fetchone()
            if previous is not None:
                source_id = previous[0]
                # Keep the old range when the new version fits in it, so the
                # rows of an edited NEEM keep their ids.
                offset = (
                    previous[1]
                    if span <= previous[2]
                    else max(next_offset, previous[1])
                )
            else:
                source_id, offset = next_id, next_offset

            pg.execute(
                sql.SQL(
                    "INSERT INTO {} ({}, file_name, file_size, file_mtime_ns, sha256, "
                    "id_offset, id_span) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                ).format(sources, source_col),
                (source_id, file.name, file.size, file.mtime_ns, digest, offset, span),
            )

            state = _read_pg_state(pg)
            _ensure_schema(pg, schema, shifted, state)

            rows = 0
            for table in schema.values():
                rows += _copy_rows(
                    pg,
                    conn,
                    table,
                    state.columns[table.name],
                    shifted.get(table.name, set()),
                    offset,
                    source_id,
                )
            pg.execute(
                sql.SQL("UPDATE {} SET row_count = %s WHERE {} = %s").format(
                    sources, source_col
                ),
                (rows, source_id),
            )
            try:
                pg.commit()
            except psycopg.errors.ForeignKeyViolation as exc:
                raise NeemLoadError(
                    f"The NEEM's foreign keys do not hold: {exc.diag.message_primary}"
                    f" ({exc.diag.message_detail})"
                ) from exc

    logger.info(
        "neem: loaded %s as source %d — %d table(s), %d row(s), id offset %d",
        file.name,
        source_id,
        len(schema),
        rows,
        offset,
    )
    return LoadResult(
        source_id=source_id, tables=len(schema), rows=rows, id_offset=offset
    )


def remove_file(file_name: str, conninfo: str | None = None) -> bool:
    """Delete everything a file loaded. Returns whether it had been loaded."""
    conninfo = conninfo or config.connection_string()
    with psycopg.connect(conninfo) as pg:
        pg.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        exists = pg.execute("SELECT to_regclass(%s)", (SOURCES_TABLE,)).fetchone()
        if exists is None or exists[0] is None:
            return False
        sources = sql.Identifier(SOURCES_TABLE)
        source_col = sql.Identifier(SOURCE_COLUMN)
        row = pg.execute(
            sql.SQL("SELECT {} FROM {} WHERE file_name = %s").format(
                source_col, sources
            ),
            (file_name,),
        ).fetchone()
        if row is None:
            return False
        _delete_source_rows(pg, row[0])
        pg.execute(
            sql.SQL("DELETE FROM {} WHERE {} = %s").format(sources, source_col),
            (row[0],),
        )
    logger.info("neem: removed %s (source %d)", file_name, row[0])
    return True
