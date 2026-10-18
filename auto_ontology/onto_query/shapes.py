# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SHACL shapes from the ontology or from plain-language rules, and validation.

OWL is open-world: an individual with no ``hasTopping`` does not contradict
"every pizza has some topping", it is just incomplete. Data validation wants
the closed-world reading, which is what SHACL gives. Shapes come from:

* :func:`derive_shapes` -- deterministic, from the ontology's own axioms:
  domains and ranges, functional properties, ``only`` / ``some`` /
  cardinality restrictions and disjointness. ``some`` and minimum
  cardinalities become warnings, since OWL never required them to be stated.
* :func:`rules_to_shapes` -- the chat model turns rules such as "every robot
  must be located in exactly one room" into SHACL, using only the ontology's
  own IRIs, checked and repaired like a SPARQL query.

:func:`validate` runs pySHACL with the ontology as the vocabulary graph and
RDFS inference, so a ``BreadKnife`` counts as a ``Knife``.
"""

from __future__ import annotations

import hashlib
import logging

from pydantic import BaseModel, Field
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from auto_ontology.onto_query import ai
from auto_ontology.onto_query.loader import OntologyParseError, is_reserved, parse_graph
from auto_ontology.onto_query.model import ElementKind, Ontology
from auto_ontology.onto_query.registry import LoadedOntology
from auto_ontology.onto_query.retrieval import render_context, retrieve_context

logger = logging.getLogger(__name__)

SH = Namespace("http://www.w3.org/ns/shacl#")
SHAPES = Namespace("urn:onto-query:shape:")

MAX_RESULTS = 500


def _shape_iri(*parts: str) -> URIRef:
    digest = hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]
    return SHAPES[digest]


def _is_datatype(iri: URIRef) -> bool:
    return str(iri).startswith(str(XSD)) or iri in (RDFS.Literal, RDF.langString)


# ---------------------------------------------------------------------------
# Derived shapes
# ---------------------------------------------------------------------------


def derive_shapes(ontology: Ontology) -> tuple[Graph, list[str]]:
    """``(shapes graph, notes)``; each note says what one shape enforces."""
    src = ontology.graph
    shapes = Graph()
    shapes.bind("sh", SH)
    shapes.bind("xsd", XSD)
    notes: list[str] = []

    def property_shape(node_shape: URIRef, path: URIRef) -> BNode:
        ps = BNode()
        shapes.add((node_shape, SH.property, ps))
        shapes.add((ps, SH.path, path))
        return ps

    for prop in ontology.elements.values():
        if prop.kind not in (
            ElementKind.OBJECT_PROPERTY,
            ElementKind.DATATYPE_PROPERTY,
        ):
            continue
        p = URIRef(prop.iri)
        domains = [URIRef(d) for d in prop.domain if d in ontology.elements]
        ranges = [URIRef(r) for r in prop.range if r.startswith(("http", "urn"))]
        functional = "functional" in prop.characteristics
        if not (domains or ranges or functional):
            continue
        shape = _shape_iri("prop", prop.iri)
        shapes.add((shape, RDF.type, SH.NodeShape))
        shapes.add((shape, SH.targetSubjectsOf, p))
        shapes.add((shape, RDFS.label, Literal(f"Use of {prop.name}")))
        if len(domains) == 1:
            shapes.add((shape, SH["class"], domains[0]))
            notes.append(
                f"Subjects of {prop.name} must be {ontology.name(str(domains[0]))}."
            )
        elif domains:
            # Several rdfs:domain statements mean the intersection.
            for d in domains:
                shapes.add((shape, SH["class"], d))
            notes.append(
                f"Subjects of {prop.name} must be all of "
                + ", ".join(ontology.name(str(d)) for d in domains)
                + "."
            )
        if ranges or functional:
            ps = property_shape(shape, p)
            for r in ranges:
                if _is_datatype(r):
                    if r != RDFS.Literal:
                        shapes.add((ps, SH.datatype, r))
                    notes.append(
                        f"Values of {prop.name} must be {ontology.name(str(r))}."
                    )
                elif str(r) in ontology.elements:
                    shapes.add((ps, SH["class"], r))
                    notes.append(
                        f"Values of {prop.name} must be {ontology.name(str(r))}."
                    )
            if functional:
                shapes.add((ps, SH.maxCount, Literal(1)))
                notes.append(f"{prop.name} has at most one value (functional).")

    for cls in ontology.of_kind(ElementKind.CLASS):
        c = URIRef(cls.iri)
        restrictions = [
            r for r in src.objects(c, RDFS.subClassOf) if isinstance(r, BNode)
        ]
        disjoint = [URIRef(d) for d in cls.disjoint_with]
        if not restrictions and not disjoint:
            continue
        shape = _shape_iri("class", cls.iri)
        added = False
        for r in restrictions:
            on = src.value(r, OWL.onProperty)
            if not isinstance(on, URIRef):
                continue
            only = src.value(r, OWL.allValuesFrom)
            some = src.value(r, OWL.someValuesFrom)
            has_value = src.value(r, OWL.hasValue)
            filler = src.value(r, OWL.onClass) or src.value(r, OWL.onDataRange)
            pname = ontology.name(str(on))
            if isinstance(only, URIRef):
                ps = property_shape(shape, on)
                shapes.add(
                    (ps, SH.datatype if _is_datatype(only) else SH["class"], only)
                )
                notes.append(
                    f"Every {cls.name}: all {pname} values are {ontology.name(str(only))}."
                )
                added = True
            elif isinstance(some, URIRef):
                ps = property_shape(shape, on)
                q = BNode()
                shapes.add(
                    (q, SH.datatype if _is_datatype(some) else SH["class"], some)
                )
                shapes.add((ps, SH.qualifiedValueShape, q))
                shapes.add((ps, SH.qualifiedMinCount, Literal(1)))
                shapes.add((ps, SH.severity, SH.Warning))
                notes.append(
                    f"Every {cls.name} should state some {pname} that is "
                    f"{ontology.name(str(some))} (warning)."
                )
                added = True
            elif has_value is not None:
                ps = property_shape(shape, on)
                shapes.add((ps, SH.hasValue, has_value))
                notes.append(
                    f"Every {cls.name} has {pname} {ontology.name(str(has_value))}."
                )
                added = True
            for pred, kind in (
                (OWL.cardinality, "exact"),
                (OWL.qualifiedCardinality, "exact"),
                (OWL.minCardinality, "min"),
                (OWL.minQualifiedCardinality, "min"),
                (OWL.maxCardinality, "max"),
                (OWL.maxQualifiedCardinality, "max"),
            ):
                n = src.value(r, pred)
                if n is None:
                    continue
                ps = property_shape(shape, on)
                target = ps
                if isinstance(filler, URIRef):
                    q = BNode()
                    shapes.add(
                        (
                            q,
                            SH.datatype if _is_datatype(filler) else SH["class"],
                            filler,
                        )
                    )
                    shapes.add((ps, SH.qualifiedValueShape, q))
                    lo, hi = SH.qualifiedMinCount, SH.qualifiedMaxCount
                else:
                    lo, hi = SH.minCount, SH.maxCount
                count = Literal(int(n))
                if kind in ("exact", "min"):
                    shapes.add((target, lo, count))
                    shapes.add((target, SH.severity, SH.Warning))
                if kind in ("exact", "max"):
                    shapes.add((target, hi, count))
                notes.append(f"Every {cls.name}: {kind} {int(n)} {pname}.")
                added = True
        for d in disjoint:
            # One shape per disjoint pair, on the alphabetically first class.
            if str(d) not in ontology.elements or str(d) < cls.iri:
                continue
            neg = BNode()
            shapes.add((neg, SH["class"], d))
            shapes.add((shape, SH["not"], neg))
            notes.append(f"Nothing is both {cls.name} and {ontology.name(str(d))}.")
            added = True
        if added:
            shapes.add((shape, RDF.type, SH.NodeShape))
            shapes.add((shape, SH.targetClass, c))
            shapes.add((shape, RDFS.label, Literal(f"{cls.name} constraints")))
    return shapes, notes


# ---------------------------------------------------------------------------
# Shapes from rules
# ---------------------------------------------------------------------------


class ShapeDraft(BaseModel):
    turtle: str = Field(description="SHACL shapes in Turtle, with @prefix lines.")
    notes: list[str] = Field(
        default_factory=list,
        description="One line per rule: how it was expressed, or why it could not be.",
    )


_RULES_SYSTEM = """You write SHACL (W3C Shapes Constraint Language) in Turtle.
Turn each plain-language rule into node/property shapes over the ontology below.
- Use only the ontology's IRIs as listed (full <...> IRIs) plus sh:, rdf:, rdfs:,
  xsd:, owl:. Declare every prefix. Name shapes under <urn:onto-query:shape:>.
- Prefer sh:targetClass, sh:property with sh:path, sh:class, sh:datatype,
  sh:minCount/sh:maxCount, sh:in, sh:pattern; give each shape an sh:message.
- sh:class already respects rdfs:subClassOf; do not expand subclasses by hand.
- If a rule cannot be expressed with the ontology's terms, say so in notes."""


def _unknown_iris(ontology: Ontology, shapes: Graph) -> list[str]:
    known_terms = set(ontology.graph.all_nodes()) | set(ontology.graph.predicates())
    out: list[str] = []
    for s, p, o in shapes:
        for term in (s, p, o):
            if not isinstance(term, URIRef):
                continue
            iri = str(term)
            if (
                iri in ontology.elements
                or is_reserved(iri)
                or iri.startswith(str(SHAPES))
                or term in known_terms
            ):
                continue
            if iri not in out:
                out.append(iri)
    return out


def rules_to_shapes(
    loaded: LoadedOntology, rules: list[str], *, max_attempts: int = 2
) -> dict:
    ontology = loaded.ontology
    iris: list[str] = []
    for rule in rules:
        for iri in retrieve_context(loaded, rule, max_elements=15).iris:
            if iri not in iris:
                iris.append(iri)
    prompt = (
        "Rules:\n"
        + "\n".join(f"{i + 1}. {r}" for i, r in enumerate(rules))
        + f"\n\nOntology elements:\n{render_context(ontology, iris[:60])}"
    )
    feedback = ""
    problems: list[str] = []
    draft: ShapeDraft | None = None
    for _ in range(max_attempts):
        draft = ai.structured(_RULES_SYSTEM, prompt + feedback, ShapeDraft)
        problems = []
        try:
            graph = parse_graph(draft.turtle, rdf_format="turtle")
        except OntologyParseError as exc:
            problems.append(f"Not valid Turtle: {exc}")
        else:
            if not any(graph.subjects(RDF.type, SH.NodeShape)) and not any(
                graph.subjects(SH.path, None)
            ):
                problems.append("No sh:NodeShape or property shape was defined.")
            unknown = _unknown_iris(ontology, graph)
            if unknown:
                problems.append(
                    "These IRIs are not in the ontology: "
                    + ", ".join(f"<{u}>" for u in unknown[:10])
                )
        if not problems:
            break
        feedback = (
            f"\n\nYour previous shapes:\n{draft.turtle}\nhad problems:\n- "
            + "\n- ".join(problems)
            + "\nReturn corrected shapes."
        )
    return {
        "rules": rules,
        "turtle": draft.turtle if draft else "",
        "notes": draft.notes if draft else [],
        "ok": not problems,
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _node(ontology: Ontology, value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def validate(
    loaded: LoadedOntology,
    *,
    data: str = "",
    data_format: str = "",
    shapes_turtle: str = "",
    use_derived: bool = True,
    explain: bool = False,
) -> dict:
    """Validate *data* (or the ontology's own individuals) against shapes."""
    from pyshacl import validate as shacl_validate

    ontology = loaded.ontology
    if data.strip():
        data_graph = parse_graph(data, rdf_format=data_format)
        source = "uploaded data"
    else:
        data_graph = Graph()
        for triple in ontology.graph:
            data_graph.add(triple)
        source = "the ontology's own individuals"

    shapes = Graph()
    notes: list[str] = []
    if use_derived:
        derived, notes = derive_shapes(ontology)
        shapes += derived
    if shapes_turtle.strip():
        shapes += parse_graph(shapes_turtle, rdf_format="turtle")
    if not len(shapes):
        raise ValueError(
            "No shapes to validate against: pass shapes or use_derived=true."
        )

    conforms, report, _ = shacl_validate(
        data_graph,
        shacl_graph=shapes,
        ont_graph=ontology.graph,
        inference="rdfs",
        abort_on_first=False,
        allow_warnings=True,
        advanced=True,
    )
    # pySHACL mixes the ontology into the data graph for inference, which
    # also puts the ontology's own individuals under validation. With uploaded
    # data, only nodes that data describes are reported.
    described = set(data_graph.subjects()) if data.strip() else None
    results = []
    for r in report.subjects(RDF.type, SH.ValidationResult):
        if len(results) >= MAX_RESULTS:
            break
        focus = report.value(r, SH.focusNode)
        if described is not None and focus not in described:
            continue
        path = report.value(r, SH.resultPath)
        value = report.value(r, SH.value)
        severity = report.value(r, SH.resultSeverity)
        results.append(
            {
                "focus_node": _node(ontology, focus),
                "focus_name": ontology.name(str(focus)) if focus is not None else None,
                "path": _node(ontology, path) if isinstance(path, URIRef) else None,
                "path_name": ontology.name(str(path))
                if isinstance(path, URIRef)
                else None,
                "value": _node(ontology, value),
                "severity": str(severity).rsplit("#", 1)[-1]
                if severity is not None
                else "Violation",
                "message": " ".join(
                    str(m) for m in report.objects(r, SH.resultMessage)
                ),
                "constraint": str(
                    report.value(r, SH.sourceConstraintComponent) or ""
                ).rsplit("#", 1)[-1],
                "shape": _node(ontology, report.value(r, SH.sourceShape)),
            }
        )
    results.sort(key=lambda x: (x["severity"] != "Violation", x["focus_name"] or ""))
    violations = sum(1 for x in results if x["severity"] == "Violation")
    out = {
        "source": source,
        "conforms": violations == 0 if described is not None else bool(conforms),
        "violations": violations,
        "warnings": sum(1 for x in results if x["severity"] == "Warning"),
        "results": results,
        "derived_rules": notes,
        "explanation": "",
    }
    if explain and results:

        class Explanation(BaseModel):
            summary: str

        lines = [
            f"{x['severity']}: {x['focus_name']} {x['path_name'] or ''} {x['value'] or ''} -- {x['message']}"
            for x in results[:60]
        ]
        try:
            out["explanation"] = ai.structured(
                "Summarise SHACL validation results for a person: what is wrong, "
                "grouped by cause, and how to fix the data. Be brief.",
                "\n".join(lines),
                Explanation,
                fast=True,
            ).summary
        except ai.OntoQueryModelError as exc:
            out["explanation"] = f"(No summary: {exc})"
    return out


def shapes_to_turtle(shapes: Graph) -> str:
    return shapes.serialize(format="turtle")


__all__ = [
    "derive_shapes",
    "rules_to_shapes",
    "shapes_to_turtle",
    "validate",
]
