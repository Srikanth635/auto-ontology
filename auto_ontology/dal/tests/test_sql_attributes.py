# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SqlAttribute reads and writes."""

from __future__ import annotations

import os
import uuid

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import select  # noqa: E402

from auto_ontology.dal import schema as s  # noqa: E402
from auto_ontology.dal import sql_attributes as sa  # noqa: E402
from auto_ontology.dal.session import store  # noqa: E402
from auto_ontology.semantic.constants import SQL_ATTR_SOURCE_BRIDGE  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def require_schema():
    if not os.environ.get("POSTGRES_USER"):
        pytest.skip("POSTGRES_* not set")
    try:
        store().query_read("SELECT 1 FROM sql_attribute LIMIT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"auto_ontology schema unavailable (alembic upgrade head): {exc}")


def _add(table, **values) -> str:
    return store().query_write(table.insert().values(**values).returning(table.c.id))[
        0
    ]["id"]


def _link(table, **values) -> None:
    store().query_write(table.insert().values(**values))


class World:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.database = _add(s.catalog_database, name=prefix)
        self.schema = _add(s.catalog_schema, database_id=self.database, name="public")
        self.tables: dict[str, str] = {}
        self.terms: dict[str, str] = {}
        self.attributes: dict[str, str] = {}
        self.queries: list[str] = []

    def table(self, name: str, columns: tuple[str, ...] = ("id",)) -> str:
        tid = _add(s.catalog_table, schema_id=self.schema, name=name)
        self.tables[name] = tid
        for position, column in enumerate(columns, start=1):
            _add(
                s.catalog_column,
                table_id=tid,
                name=column,
                data_type="integer",
                ordinal_position=position,
            )
        return tid

    def term(self, name: str) -> str:
        tid = _add(s.term, name=f"{self.prefix}-{name}")
        self.terms[name] = tid
        return tid

    def attribute(
        self,
        name: str,
        term: str,
        *,
        sql: str | None = None,
        tables: tuple[str, ...] = (),
        expression: str | None = None,
        source: str | None = None,
    ) -> str:
        aid = _add(
            s.sql_attribute,
            name=f"{self.prefix}-{name}",
            expression=expression,
            source=source,
        )
        self.attributes[name] = aid
        _link(s.sql_attribute__term, attribute_id=aid, term_id=self.terms[term])
        if sql is not None:
            qid = _add(s.sql_query, sql_full_query=sql)
            self.queries.append(qid)
            _link(s.sql_attribute__sql, attribute_id=aid, sql_query_id=qid)
            for table in tables:
                _link(s.sql_query__table, sql_query_id=qid, table_id=self.tables[table])
        return aid


@pytest.fixture
def world():
    w = World(f"q-{uuid.uuid4().hex[:8]}")
    yield w
    store().query_write(
        s.catalog_database.delete().where(s.catalog_database.c.id == w.database)
    )
    for table in (s.sql_attribute, s.term):
        store().query_write(table.delete().where(table.c.name.like(f"{w.prefix}%")))
    for query_id in w.queries:
        store().query_write(s.sql_query.delete().where(s.sql_query.c.id == query_id))


@pytest.fixture
def scoped(world):
    """Two tables and three attributes across them."""
    world.table("orders")
    world.table("secrets")
    world.term("Revenue")
    world.attribute("inside", "Revenue", sql="SELECT 1", tables=("orders",))
    world.attribute("outside", "Revenue", sql="SELECT 2", tables=("secrets",))
    world.attribute("both", "Revenue", sql="SELECT 3", tables=("orders", "secrets"))
    return world


def _names(rows) -> set[str]:
    return {r["name"] for r in rows}


# --------------------------------------------------------------------------
# Lists and counts
# --------------------------------------------------------------------------


def test_counts_use_the_same_scoping_as_the_list(scoped) -> None:
    """A badge that disagrees with its list is worse than no badge."""
    listed = sa.fetch_sql_attributes_by_term_id(scoped.terms["Revenue"])
    counted = sa.count_sql_attributes_by_term_id(scoped.terms["Revenue"])
    assert counted == len(listed) == 3


def test_per_term_counts_agree_with_the_list(scoped) -> None:
    counts = {r["term_id"]: r["count"] for r in sa.fetch_sql_attribute_counts()}
    assert counts.get(scoped.terms["Revenue"]) == 3


def test_per_term_counts_can_be_narrowed_to_a_page(scoped) -> None:
    """The Terms list passes only the ids it is about to render."""
    other = scoped.term("Unrelated")
    scoped.attribute("elsewhere", "Unrelated", sql="SELECT 4", tables=("orders",))

    everything = sa.fetch_sql_attribute_counts()
    assert {scoped.terms["Revenue"], other} <= {r["term_id"] for r in everything}

    narrowed = sa.fetch_sql_attribute_counts(term_ids=[other])
    assert [r["term_id"] for r in narrowed] == [other]


# --------------------------------------------------------------------------
# The shared traversal
# --------------------------------------------------------------------------


def test_an_attribute_with_no_sql_is_invisible(world) -> None:
    """Invisible to the list *and* to the counts, which is the point.

    A count that included it would render a badge promising rows the list
    cannot produce.
    """
    world.term("Revenue")
    world.attribute("orphan", "Revenue")
    world.attribute("real", "Revenue", sql="SELECT 1")

    assert _names(sa.list_sql_attributes()) & {
        f"{world.prefix}-orphan",
        f"{world.prefix}-real",
    } == {f"{world.prefix}-real"}
    assert sa.count_sql_attributes_by_term_id(world.terms["Revenue"]) == 1


def test_several_statements_still_yield_one_row(world) -> None:
    """`head(collect(sql))` after `ORDER BY sql.id`, as a scalar subquery.

    Without the collapse the rows outnumber the count the pager was handed, and
    the last attributes of a term become unreachable.
    """
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")
    second = _add(s.sql_query, sql_full_query="SELECT 2")
    world.queries.append(second)
    _link(s.sql_attribute__sql, attribute_id=attr, sql_query_id=second)

    rows = sa.fetch_sql_attributes_by_term_id(world.terms["Revenue"])
    assert len(rows) == 1
    assert sa.count_sql_attributes_by_term_id(world.terms["Revenue"]) == 1
    # Lowest id wins, and the same one each time.
    assert (
        rows[0]["sql"]
        == sa.fetch_sql_attributes_by_term_id(world.terms["Revenue"])[0]["sql"]
    )


def test_paging_is_stable_across_a_name_tie(world) -> None:
    """Same-named attributes are why the order carries `id` as a tiebreaker.

    On name alone the two tied rows can swap between requests, so page 1 and
    page 2 could show one twice and the other never. `sql_attribute.name` is
    unique, so the tie is built here on the *sort key* rather than the column:
    every name shares a prefix and differs only past it, and the assertion is
    that four distinct rows come back across two pages.
    """
    world.term("Revenue")
    for i in range(4):
        world.attribute(f"tied-{i}", "Revenue", sql=f"SELECT {i} -- {world.prefix}")

    seen: list[str] = []
    for skip in range(0, 4, 2):
        page = sa.fetch_sql_attributes_by_term_id(
            world.terms["Revenue"], skip=skip, limit=2
        )
        seen.extend(r["id"] for r in page)
    assert len(seen) == len(set(seen)) == 4


# --------------------------------------------------------------------------
# Conflict lookups
# --------------------------------------------------------------------------


def test_find_by_name_excludes_the_attribute_being_edited(world) -> None:
    """Without the exclusion, renaming an attribute to its own name conflicts."""
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")

    assert sa.find_attr_by_name(f"{world.prefix}-revenue", exclude_id=attr) is None
    found = sa.find_attr_by_name(f"{world.prefix}-revenue", exclude_id=None)
    assert found == {"id": attr, "name": f"{world.prefix}-revenue"}


def test_find_by_expression_ignores_case_and_whitespace(world) -> None:
    world.term("Revenue")
    attr = world.attribute(
        "revenue", "Revenue", sql="SELECT 1", expression="SELECT  sum(amount)\n FROM p"
    )

    hit = sa.find_attr_by_expression(
        term_id=world.terms["Revenue"],
        expression="select sum(amount) from p",
        exclude_id=None,
    )
    assert hit == {"id": attr, "name": f"{world.prefix}-revenue"}


def test_find_by_expression_is_scoped_to_the_term(world) -> None:
    """Two terms may legitimately define the same SQL."""
    world.term("Revenue")
    world.term("Profit")
    world.attribute("revenue", "Revenue", sql="SELECT 1", expression="SELECT 1")

    assert (
        sa.find_attr_by_expression(
            term_id=world.terms["Profit"], expression="SELECT 1", exclude_id=None
        )
        is None
    )


def test_get_by_id_is_an_existence_check(world) -> None:
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")
    assert sa.get_sql_attribute_by_id(attr) == attr
    assert sa.get_sql_attribute_by_id("no-such-attribute") is None


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------


def test_detaching_sql_leaves_the_statement_alone(world) -> None:
    """Sql rows are shared with query history; deleting one here is not ours."""
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")
    query_id = world.queries[-1]

    sa.detach_existing_sql_edges(attr)

    assert (
        store().query_read(
            select(s.sql_attribute__sql.c.sql_query_id).where(
                s.sql_attribute__sql.c.attribute_id == attr
            )
        )
        == []
    )
    assert store().query_read(
        select(s.sql_query.c.id).where(s.sql_query.c.id == query_id)
    )


def test_link_to_term_replaces_the_previous_link(world) -> None:
    world.term("Revenue")
    world.term("Profit")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")

    sa.link_to_term(attr, world.terms["Profit"])

    linked = store().query_read(
        select(s.sql_attribute__term.c.term_id).where(
            s.sql_attribute__term.c.attribute_id == attr
        )
    )
    assert [r["term_id"] for r in linked] == [world.terms["Profit"]]


def test_link_to_term_is_idempotent(world) -> None:
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")
    sa.link_to_term(attr, world.terms["Revenue"])
    sa.link_to_term(attr, world.terms["Revenue"])

    linked = store().query_read(
        select(s.sql_attribute__term.c.term_id).where(
            s.sql_attribute__term.c.attribute_id == attr
        )
    )
    assert len(linked) == 1


def test_update_leaves_omitted_fields_alone(world) -> None:
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1", source="manual")

    sa.update_sql_attribute(attr, description="first", certified=True)
    sa.update_sql_attribute(attr, expression="SELECT 2")

    row = store().query_read(
        select(s.sql_attribute).where(s.sql_attribute.c.id == attr)
    )[0]
    assert row["description"] == "first"
    assert row["certified"] is True
    assert row["expression"] == "SELECT 2"
    assert row["source"] == "manual"


def test_update_with_nothing_set_is_a_no_op(world) -> None:
    """Every argument None, which is what an empty PATCH body produces.

    Postgres cannot infer a type for a bare NULL inside `coalesce`, so this
    raises rather than doing nothing unless the parameter is typed.
    """
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1", source="manual")

    sa.update_sql_attribute(attr)

    row = store().query_read(
        select(s.sql_attribute).where(s.sql_attribute.c.id == attr)
    )[0]
    assert row["name"] == f"{world.prefix}-revenue"
    assert row["source"] == "manual"


def test_update_leaves_pii_processed_alone(world) -> None:
    """PII realign lives on the service, not on this row patch."""
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1", source="manual")
    store().query_write(
        s.sql_attribute.update()
        .where(s.sql_attribute.c.id == attr)
        .values(pii_processed=True)
    )

    sa.update_sql_attribute(attr, description="metadata only", expression="SELECT 2")

    row = store().query_read(
        select(s.sql_attribute.c.pii_processed).where(s.sql_attribute.c.id == attr)
    )[0]
    assert row["pii_processed"] is True


def test_description_suggestions_round_trip(world) -> None:
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")

    sa.set_sql_attribute_description_suggestion(attr, "a guess")
    assert (
        sa.fetch_sql_attributes_by_term_id(world.terms["Revenue"])[0][
            "description_suggestion"
        ]
        == "a guess"
    )

    sa.clear_sql_attribute_description_suggestion(attr)
    assert (
        sa.fetch_sql_attributes_by_term_id(world.terms["Revenue"])[0][
            "description_suggestion"
        ]
        is None
    )


def test_clearing_suggestions_for_a_term_clears_all_of_them(world) -> None:
    world.term("Revenue")
    first = world.attribute("one", "Revenue", sql="SELECT 1")
    second = world.attribute("two", "Revenue", sql="SELECT 2")
    for attr in (first, second):
        sa.set_sql_attribute_description_suggestion(attr, "a guess")

    sa.clear_sql_attribute_description_suggestions_for_term(world.terms["Revenue"])

    rows = sa.fetch_sql_attributes_by_term_id(world.terms["Revenue"])
    assert [r["description_suggestion"] for r in rows] == [None, None]


def test_delete_cascades_its_links(world) -> None:
    """`DETACH DELETE` moved into the schema, so a new link table cannot be
    added later and forgotten here."""
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")

    sa.delete_sql_attribute_node(attr)

    assert sa.get_sql_attribute_by_id(attr) is None
    for table, column in (
        (s.sql_attribute__term, s.sql_attribute__term.c.attribute_id),
        (s.sql_attribute__sql, s.sql_attribute__sql.c.attribute_id),
    ):
        assert store().query_read(select(column).where(column == attr)) == []


# --------------------------------------------------------------------------
# Retrieval helpers
# --------------------------------------------------------------------------


def test_with_sql_returns_one_row_per_attribute(world) -> None:
    world.term("Revenue")
    attr = world.attribute(
        "revenue", "Revenue", sql="SELECT 1", expression="sum(amount)"
    )

    rows = sa.fetch_sql_attributes_with_sql([attr])
    assert rows == [
        {
            "id": attr,
            "name": f"{world.prefix}-revenue",
            "description": "",
            "expression": "sum(amount)",
            "sql": "SELECT 1",
            "term_name": f"{world.prefix}-Revenue",
        }
    ]


def test_with_sql_is_empty_for_an_empty_list() -> None:
    assert sa.fetch_sql_attributes_with_sql([]) == []


def test_tables_from_attributes_dedupes_and_nests_columns(world) -> None:
    world.table("orders", columns=("id", "amount"))
    world.term("Revenue")
    first = world.attribute("one", "Revenue", sql="SELECT 1", tables=("orders",))
    second = world.attribute("two", "Revenue", sql="SELECT 2", tables=("orders",))

    tables = sa.fetch_tables_from_sql_attributes([first, second])
    assert len(tables) == 1
    assert tables[0]["name"] == "orders"
    assert [c["name"] for c in tables[0]["columns"]] == ["id", "amount"]


def test_tables_from_attributes_is_empty_for_an_empty_list() -> None:
    assert sa.fetch_tables_from_sql_attributes([]) == []


# --------------------------------------------------------------------------
# Embedding docs
# --------------------------------------------------------------------------


def test_doc_text_format_is_reproduced_exactly(world) -> None:
    """The text is what gets embedded.

    Changing a separator or reordering a part silently invalidates every stored
    vector for these attributes, and nothing downstream would fail — retrieval
    would just quietly get worse. So it is pinned literally.
    """
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")
    sa.update_sql_attribute(attr, description="total revenue")

    assert sa.fetch_sql_attribute_docs(attr) == [
        {
            "text": (
                f"sql_attribute: {world.prefix}-revenue, "
                f"description: total revenue, "
                f"term: {world.prefix}-Revenue, sql: SELECT 1"
            ),
            "name": f"{world.prefix}-revenue",
            "label": "SqlAttribute",
            "id": attr,
            # No source set, and the empty string is deliberate: it rides into
            # the VDB metadata, where a None would have to be special-cased by
            # every reader.
            "source": "",
        }
    ]


def test_doc_carries_the_attribute_source(world) -> None:
    """Retrieval filters bridge-table joins on this without a second read."""
    world.term("Revenue")
    attr = world.attribute(
        "bridge", "Revenue", sql="SELECT 1", source=SQL_ATTR_SOURCE_BRIDGE
    )

    assert sa.fetch_sql_attribute_docs(attr)[0]["source"] == SQL_ATTR_SOURCE_BRIDGE


def test_a_blank_description_is_omitted_not_rendered_empty(world) -> None:
    world.term("Revenue")
    attr = world.attribute("revenue", "Revenue", sql="SELECT 1")
    sa.update_sql_attribute(attr, description="   ")

    text = sa.fetch_sql_attribute_docs(attr)[0]["text"]
    assert "description:" not in text
    assert text.startswith(f"sql_attribute: {world.prefix}-revenue, term:")


def test_docs_are_empty_without_a_statement(world) -> None:
    world.term("Revenue")
    assert sa.fetch_sql_attribute_docs(world.attribute("orphan", "Revenue")) == []
