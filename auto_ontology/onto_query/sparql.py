# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Check and run SPARQL against a loaded ontology's graph.

Checks, in order:

1. **Read-only, local** -- updates, ``SERVICE`` and ``FROM`` are refused:
   rdflib would otherwise follow them to remote endpoints and URLs.
2. **Syntax** -- the query must parse.
3. **Vocabulary** -- every IRI must exist in the ontology or be standard
   RDF/RDFS/OWL/XSD/SKOS vocabulary. An invented IRI is the usual LLM mistake,
   so the error names the closest real elements to fix it with.
4. **Domain and range** -- a variable typed as a class that is disjoint from,
   or unrelated to, a property's domain or range gets a warning (not an
   error: a query may be deliberately asking for violations).
"""

from __future__ import annotations

import concurrent.futures
import re
from dataclasses import dataclass, field

from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.namespace import RDF
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.parserutils import CompValue

from auto_ontology.onto_query.loader import is_reserved
from auto_ontology.onto_query.model import Ontology
from auto_ontology.onto_query.text import local_name

#: Rows returned to callers (and shown to the model) at most.
MAX_ROWS = 200
#: Wall-clock cap on one query.
QUERY_TIMEOUT_S = 20.0

_FORBIDDEN = re.compile(
    # Keywords only: not a variable (?from), prefixed name (ex:add) or prefix (add:).
    r"(?<![\w?$:])(INSERT|DELETE|LOAD|CLEAR|CREATE|DROP|COPY|MOVE|ADD|SERVICE|FROM)\b(?![:\w])",
    re.IGNORECASE,
)
_STRINGS = re.compile(
    r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''
)
_IRIS = re.compile(r"<[^>\s]*>")
_COMMENTS = re.compile(r"#[^\n]*")

_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="sparql"
)


@dataclass
class Check:
    query: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    iris: list[str] = field(default_factory=list)
    prepared: object | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "iris": self.iris,
        }


def _strip_noise(query: str) -> str:
    """The query with strings, IRIs and comments blanked, for keyword checks."""
    text = _STRINGS.sub('""', query)
    text = _IRIS.sub("<>", text)
    return "\n".join(_COMMENTS.sub("", line) for line in text.splitlines())


def _collect(node: object, out: list, seen: set[int]) -> None:
    if id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, URIRef):
        out.append(node)
    elif isinstance(node, (CompValue, dict)):
        for value in node.values():
            _collect(value, out, seen)
    elif isinstance(node, (list, tuple, set)):
        for value in node:
            _collect(value, out, seen)


def _triples(node: object, out: list, seen: set[int]) -> None:
    if id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, CompValue):
        if node.name == "BGP":
            out.extend(node.get("triples") or [])
        for value in node.values():
            _triples(value, out, seen)
    elif isinstance(node, dict):
        for value in node.values():
            _triples(value, out, seen)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _triples(value, out, seen)


def _suggest(ontology: Ontology, iri: str) -> str:
    name = local_name(iri)
    exact = ontology.by_label(name)
    if exact:
        return f" Did you mean <{exact[0].iri}>?"
    key = name.lower()
    close = [
        e.iri
        for e in ontology.elements.values()
        if key
        and (key in local_name(e.iri).lower() or local_name(e.iri).lower() in key)
    ][:3]
    return (" Closest: " + ", ".join(f"<{c}>" for c in close) + ".") if close else ""


def _related(ontology: Ontology, a: str, b: str) -> bool:
    """Whether class *a* is *b*, under it, or above it."""
    return a == b or b in ontology.ancestors(a) or a in ontology.ancestors(b)


def check_query(ontology: Ontology, query: str) -> Check:
    check = Check(query=query.strip())
    if not check.query:
        check.errors.append("The query is empty.")
        return check
    forbidden = sorted(
        {m.group(1).upper() for m in _FORBIDDEN.finditer(_strip_noise(check.query))}
    )
    if forbidden:
        check.errors.append(
            "Only read-only queries against the loaded ontology are allowed; "
            f"remove {', '.join(forbidden)}."
        )
        return check
    try:
        prepared = prepareQuery(check.query, initNs=ontology.prefixes)
    except Exception as exc:  # noqa: BLE001 -- pyparsing raises many types
        check.errors.append(f"SPARQL syntax error: {str(exc)[:300]}")
        return check
    check.prepared = prepared

    found: list = []
    _collect(prepared.algebra, found, set())
    graph_terms = None
    for iri in dict.fromkeys(str(u) for u in found):
        check.iris.append(iri)
        if iri in ontology.elements or is_reserved(iri):
            continue
        if graph_terms is None:
            graph = ontology.graph
            graph_terms = set()
            for s, p, o in graph:
                graph_terms.update((s, p, o))
        if URIRef(iri) in graph_terms:
            continue
        check.errors.append(f"<{iri}> is not in the ontology.{_suggest(ontology, iri)}")

    triples: list = []
    _triples(prepared.algebra, triples, set())
    var_types: dict[Variable, set[str]] = {}
    for s, p, o in triples:
        if p == RDF.type and isinstance(s, Variable) and isinstance(o, URIRef):
            var_types.setdefault(s, set()).add(str(o))
    for s, p, o in triples:
        prop = ontology.elements.get(str(p)) if isinstance(p, URIRef) else None
        if prop is None or not prop.kind.is_property:
            continue
        for term, allowed, side in (
            (s, prop.domain, "domain"),
            (o, prop.range, "range"),
        ):
            named = [a for a in allowed if a in ontology.elements]
            if not named or not isinstance(term, Variable):
                continue
            for typ in var_types.get(term, ()):
                if typ in ontology.elements and not any(
                    _related(ontology, typ, a) for a in named
                ):
                    check.warnings.append(
                        f"?{term} is typed {ontology.name(typ)}, which is outside the "
                        f"{side} of {prop.name} ({', '.join(ontology.name(a) for a in named)})."
                    )
    return check


def _term(ontology: Ontology, value: object) -> dict | None:
    if value is None:
        return None
    if isinstance(value, URIRef):
        return {"type": "iri", "value": str(value), "name": ontology.name(str(value))}
    if isinstance(value, Literal):
        out = {"type": "literal", "value": str(value)}
        if value.datatype:
            out["datatype"] = str(value.datatype)
        if value.language:
            out["lang"] = value.language
        return out
    if isinstance(value, BNode):
        return {"type": "bnode", "value": str(value)}
    return {"type": "literal", "value": str(value)}


def run_query(ontology: Ontology, check: Check, graph: Graph | None = None) -> dict:
    """Execute a passing :class:`Check`; raises ``ValueError`` on failure.

    *graph* replaces the asserted graph, e.g. with a reasoner's inferred one.
    """
    if not check.ok or check.prepared is None:
        raise ValueError(
            "The query did not pass its checks: " + "; ".join(check.errors)
        )

    target = graph if graph is not None else ontology.graph

    def _execute():  # noqa: ANN202
        result = target.query(check.prepared)
        if result.type == "ASK":
            return {"type": "ask", "boolean": bool(result.askAnswer)}
        if result.type in ("CONSTRUCT", "DESCRIBE"):
            graph = result.graph
            triples = [
                [_term(ontology, t) for t in triple]
                for _, triple in zip(range(MAX_ROWS), graph)
            ]
            return {
                "type": "graph",
                "triple_count": len(graph),
                "triples": triples,
                "truncated": len(graph) > MAX_ROWS,
            }
        variables = [str(v) for v in result.vars or []]
        rows = []
        truncated = False
        for i, row in enumerate(result):
            if i >= MAX_ROWS:
                truncated = True
                break
            rows.append({var: _term(ontology, row[var]) for var in variables})
        return {
            "type": "select",
            "variables": variables,
            "rows": rows,
            "truncated": truncated,
        }

    future = _POOL.submit(_execute)
    try:
        return future.result(timeout=QUERY_TIMEOUT_S)
    except concurrent.futures.TimeoutError as exc:
        raise ValueError(
            f"The query ran longer than {QUERY_TIMEOUT_S:.0f}s; narrow it or add a LIMIT."
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"The query failed: {type(exc).__name__}: {str(exc)[:300]}"
        ) from exc


def result_size(result: dict) -> int:
    if result["type"] == "select":
        return len(result["rows"])
    if result["type"] == "graph":
        return result["triple_count"]
    return 1


def result_preview(result: dict, limit: int = 40) -> str:
    """Rows as compact text for a prompt."""
    if result["type"] == "ask":
        return f"ASK result: {result['boolean']}"
    if result["type"] == "graph":
        lines = [
            " ".join((t or {}).get("name") or (t or {}).get("value", "") for t in tr)
            for tr in result["triples"][:limit]
        ]
        return f"{result['triple_count']} triples:\n" + "\n".join(lines)
    lines = []
    for row in result["rows"][:limit]:
        cells = []
        for var in result["variables"]:
            term = row.get(var)
            if term is None:
                cells.append(f"{var}=(unbound)")
            elif term["type"] == "iri":
                cells.append(f"{var}={term['name']} <{term['value']}>")
            else:
                cells.append(f"{var}={term['value']}")
        lines.append("; ".join(cells))
    more = len(result["rows"]) - limit
    tail = f"\n(+{more} more rows)" if more > 0 else ""
    trunc = " (truncated)" if result.get("truncated") else ""
    return f"{len(result['rows'])} rows{trunc}:\n" + "\n".join(lines) + tail


__all__ = ["Check", "check_query", "result_preview", "result_size", "run_query"]
