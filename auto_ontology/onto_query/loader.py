# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parse OWL/RDF into an :class:`~.model.Ontology`.

Reads anything rdflib reads (Turtle, RDF/XML, N-Triples, N3, JSON-LD, TriG).
OWL Manchester and functional syntax are not RDF and are rejected; convert them
with ROBOT or Protégé first.

Labels and definitions are taken from the vocabularies ontologies actually use
-- RDFS, SKOS, OBO (IAO / oboInOwl) and Dublin Core -- with English or untagged
literals preferred. Anonymous class expressions (restrictions, intersections,
unions) are rendered in a Manchester-like syntax so they can be read by people,
embedded and handed to an LLM.
"""

from __future__ import annotations

import logging
import re
from pathlib import PurePath

from rdflib import Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS, XSD

from auto_ontology.onto_query.model import Element, ElementKind, Ontology
from auto_ontology.onto_query.text import humanize, local_name

logger = logging.getLogger(__name__)

OBO = "http://purl.obolibrary.org/obo/"
OBO_IN_OWL = "http://www.geneontology.org/formats/oboInOwl#"
IAO_DEFINITION = URIRef(OBO + "IAO_0000115")

LABEL_PREDICATES = (SKOS.prefLabel, RDFS.label)
ALT_LABEL_PREDICATES = (
    SKOS.altLabel,
    URIRef(OBO_IN_OWL + "hasExactSynonym"),
    URIRef(OBO_IN_OWL + "hasRelatedSynonym"),
    URIRef(OBO_IN_OWL + "hasBroadSynonym"),
    URIRef(OBO_IN_OWL + "hasNarrowSynonym"),
)
DEFINITION_PREDICATES = (
    SKOS.definition,
    IAO_DEFINITION,
    DCTERMS.description,
    DC.description,
)

#: Namespaces whose terms are vocabulary, never elements of the ontology.
RESERVED_NAMESPACES = (
    str(RDF),
    str(RDFS),
    str(OWL),
    str(XSD),
    str(SKOS),
    str(DC),
    str(DCTERMS),
    OBO_IN_OWL,
    "http://www.w3.org/ns/shacl#",
)

_FORMAT_BY_SUFFIX = {
    ".ttl": "turtle",
    ".turtle": "turtle",
    ".owl": "xml",
    ".rdf": "xml",
    ".xml": "xml",
    ".nt": "nt",
    ".n3": "n3",
    ".jsonld": "json-ld",
    ".json": "json-ld",
    ".trig": "trig",
}
_FALLBACK_FORMATS = ("turtle", "xml", "nt", "json-ld", "n3")

_CHARACTERISTICS = {
    OWL.FunctionalProperty: "functional",
    OWL.InverseFunctionalProperty: "inverse functional",
    OWL.TransitiveProperty: "transitive",
    OWL.SymmetricProperty: "symmetric",
    OWL.AsymmetricProperty: "asymmetric",
    OWL.ReflexiveProperty: "reflexive",
    OWL.IrreflexiveProperty: "irreflexive",
}

#: How many property assertions of one individual to keep.
_MAX_ASSERTIONS = 25
#: Class expressions nest; past this depth they are cut short with "...".
_MAX_EXPRESSION_DEPTH = 6


class OntologyParseError(ValueError):
    """The source could not be read as RDF; the message says why."""


def is_reserved(iri: str) -> bool:
    return iri.startswith(RESERVED_NAMESPACES)


def new_graph() -> Graph:
    """A graph with only the core prefixes bound, so the prefixes it reports
    are the ones the source declared, not rdflib's two dozen defaults."""
    return Graph(bind_namespaces="core")


def parse_graph(
    data: bytes | str, *, filename: str = "", rdf_format: str = ""
) -> Graph:
    """Parse *data* into a graph, guessing the format when none is given."""
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig")
    stripped = data.lstrip()
    if stripped.startswith(("Prefix:", "Ontology:")) or stripped.startswith(
        "Ontology("
    ):
        raise OntologyParseError(
            "This looks like OWL Manchester or functional syntax, which is not "
            "RDF. Save it as Turtle or RDF/XML (Protégé: File -> Save as) first."
        )
    suffix = PurePath(filename).suffix.lower() if filename else ""
    candidates: list[str] = []
    for fmt in (rdf_format, _FORMAT_BY_SUFFIX.get(suffix, "")):
        if fmt and fmt not in candidates:
            candidates.append(fmt)
    if stripped.startswith("<?xml") or stripped.startswith("<rdf:RDF"):
        candidates.insert(0, "xml")
    candidates.extend(f for f in _FALLBACK_FORMATS if f not in candidates)

    errors: list[str] = []
    for fmt in candidates:
        graph = new_graph()
        try:
            graph.parse(data=data, format=fmt)
        except Exception as exc:  # noqa: BLE001 -- try the next format
            errors.append(f"{fmt}: {str(exc)[:200]}")
            continue
        if len(graph):
            return graph
        errors.append(f"{fmt}: parsed but produced no triples")
    raise OntologyParseError(
        "Could not read the ontology as RDF. Tried " + "; ".join(errors)
    )


def _pick(literals: list[Literal]) -> str:
    """English or untagged first, then anything; whitespace collapsed."""
    if not literals:
        return ""

    def rank(lit: Literal) -> int:
        lang = (lit.language or "").lower()
        return 0 if lang in ("", "en") or lang.startswith("en-") else 1

    best = sorted(literals, key=lambda lit: (rank(lit), len(str(lit)), str(lit)))[0]
    return " ".join(str(best).split())


_OPAQUE_ID = re.compile(r"^[A-Za-z]{0,8}[_:]?\d+$")


def _is_english(lit: Literal) -> bool:
    lang = (lit.language or "").lower()
    return lang in ("", "en") or lang.startswith("en-")


def _choose_label(iri: str, labels: list[Literal]) -> str:
    """English or untagged label; failing that a readable local name.

    Ontologies with only non-English labels (the Pizza ontology labels in
    Portuguese) usually have English local names, which read better for an
    English question. Opaque ids (``IAO_0000115``, ``C12345``) never do, so
    those keep the foreign label.
    """
    english = [lit for lit in labels if _is_english(lit)]
    if english:
        return _pick(english)
    name = local_name(iri)
    if name and not _OPAQUE_ID.match(name):
        return humanize(name)
    return _pick(labels)


def _literals(graph: Graph, subject: URIRef, predicates: tuple) -> list[Literal]:
    out: list[Literal] = []
    for predicate in predicates:
        out.extend(
            o for o in graph.objects(subject, predicate) if isinstance(o, Literal)
        )
    return out


class _Reader:
    """Walks one graph and builds its elements."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.elements: dict[str, Element] = {}

    # -- naming ---------------------------------------------------------------

    def short(self, node: object) -> str:
        """A readable name for *node* inside a rendered expression."""
        if isinstance(node, URIRef):
            label = _choose_label(
                str(node), _literals(self.graph, node, LABEL_PREDICATES)
            )
            return label or humanize(local_name(str(node)))
        if isinstance(node, Literal):
            return f'"{node}"'
        return self.expression(node)

    def ref(self, node: object) -> str:
        """An IRI for a named node, a rendered expression for a blank one."""
        if isinstance(node, URIRef):
            return str(node)
        return self.expression(node)

    def _list(self, node: object) -> list:
        try:
            return list(Collection(self.graph, node))
        except Exception:  # noqa: BLE001 -- malformed list
            return []

    def expression(self, node: object, depth: int = 0) -> str:
        """Render a class expression in a Manchester-like syntax."""
        g = self.graph
        if isinstance(node, URIRef):
            return self.short(node)
        if isinstance(node, Literal):
            return f'"{node}"'
        if depth > _MAX_EXPRESSION_DEPTH:
            return "..."

        def sub(n: object) -> str:
            text = self.expression(n, depth + 1)
            return f"({text})" if " " in text and not isinstance(n, URIRef) else text

        prop = g.value(node, OWL.onProperty)
        if prop is not None:
            p = self.short(prop)
            if (v := g.value(node, OWL.someValuesFrom)) is not None:
                return f"{p} some {sub(v)}"
            if (v := g.value(node, OWL.allValuesFrom)) is not None:
                return f"{p} only {sub(v)}"
            if (v := g.value(node, OWL.hasValue)) is not None:
                return f"{p} value {self.short(v)}"
            filler = g.value(node, OWL.onClass) or g.value(node, OWL.onDataRange)
            tail = f" {sub(filler)}" if filler is not None else ""
            for pred, word in (
                (OWL.cardinality, "exactly"),
                (OWL.qualifiedCardinality, "exactly"),
                (OWL.minCardinality, "min"),
                (OWL.minQualifiedCardinality, "min"),
                (OWL.maxCardinality, "max"),
                (OWL.maxQualifiedCardinality, "max"),
            ):
                if (n := g.value(node, pred)) is not None:
                    return f"{p} {word} {n}{tail}"
            if g.value(node, OWL.hasSelf) is not None:
                return f"{p} Self"
            return f"{p} (restriction)"
        if (lst := g.value(node, OWL.intersectionOf)) is not None:
            return " and ".join(sub(m) for m in self._list(lst))
        if (lst := g.value(node, OWL.unionOf)) is not None:
            return " or ".join(sub(m) for m in self._list(lst))
        if (c := g.value(node, OWL.complementOf)) is not None:
            return f"not {sub(c)}"
        if (lst := g.value(node, OWL.oneOf)) is not None:
            return "{" + ", ".join(self.short(m) for m in self._list(lst)) + "}"
        if (dt := g.value(node, OWL.onDatatype)) is not None:
            return self.short(dt) + "[...]"
        if (inv := g.value(node, OWL.inverseOf)) is not None:
            return f"inverse {self.short(inv)}"
        return "(anonymous)"

    # -- discovery ------------------------------------------------------------

    def _add(self, node: object, kind: ElementKind) -> None:
        if not isinstance(node, URIRef):
            return
        iri = str(node)
        if is_reserved(iri):
            return
        existing = self.elements.get(iri)
        # Properties typed twice keep the more specific kind; an IRI declared
        # both a class and an individual (OWL punning) stays a class.
        if existing is None or (
            existing.kind == ElementKind.ANNOTATION_PROPERTY and kind.is_property
        ):
            self.elements[iri] = Element(iri=iri, kind=kind)

    def discover(self) -> None:
        g = self.graph
        for cls in (OWL.Class, RDFS.Class):
            for s in g.subjects(RDF.type, cls):
                self._add(s, ElementKind.CLASS)
        for s, o in g.subject_objects(RDFS.subClassOf):
            self._add(s, ElementKind.CLASS)
            self._add(o, ElementKind.CLASS)
        for typ, kind in (
            (OWL.ObjectProperty, ElementKind.OBJECT_PROPERTY),
            (OWL.DatatypeProperty, ElementKind.DATATYPE_PROPERTY),
            (OWL.AnnotationProperty, ElementKind.ANNOTATION_PROPERTY),
        ):
            for s in g.subjects(RDF.type, typ):
                self._add(s, kind)
        for s in g.subjects(RDF.type, RDF.Property):
            if str(s) in self.elements:
                continue
            ranges = list(g.objects(s, RDFS.range))
            datatype = any(
                isinstance(r, URIRef)
                and (str(r).startswith(str(XSD)) or r == RDFS.Literal)
                for r in ranges
            )
            self._add(
                s,
                ElementKind.DATATYPE_PROPERTY
                if datatype
                else ElementKind.OBJECT_PROPERTY,
            )
        for s, o in g.subject_objects(RDFS.subPropertyOf):
            if str(s) not in self.elements:
                self._add(s, ElementKind.OBJECT_PROPERTY)
        for s in g.subjects(RDF.type, OWL.NamedIndividual):
            self._add(s, ElementKind.INDIVIDUAL)
        classes = {
            iri for iri, e in self.elements.items() if e.kind == ElementKind.CLASS
        }
        for s, o in g.subject_objects(RDF.type):
            if isinstance(o, URIRef) and str(o) in classes:
                self._add(s, ElementKind.INDIVIDUAL)

    # -- description ----------------------------------------------------------

    def describe(self, element: Element) -> None:
        g = self.graph
        node = URIRef(element.iri)
        element.label = _choose_label(element.iri, _literals(g, node, LABEL_PREDICATES))
        pref = {element.label}
        alts: list[str] = []
        for lit in _literals(g, node, ALT_LABEL_PREDICATES + LABEL_PREDICATES):
            text = " ".join(str(lit).split())
            if text and text not in pref and text not in alts:
                alts.append(text)
        element.alt_labels = alts[:20]
        element.definition = _pick(_literals(g, node, DEFINITION_PREDICATES))
        element.comment = _pick(_literals(g, node, (RDFS.comment,)))
        element.deprecated = any(
            str(v).lower() in ("true", "1") for v in g.objects(node, OWL.deprecated)
        )

        if element.kind == ElementKind.CLASS:
            self._describe_class(element, node)
        elif element.kind.is_property:
            self._describe_property(element, node)
        else:
            self._describe_individual(element, node)

    def _named_or_expression(self, values: list, into_parents: list[str]) -> list[str]:
        """Named values go to *into_parents*; blank ones are returned rendered."""
        rendered: list[str] = []
        for value in values:
            if isinstance(value, URIRef):
                if not is_reserved(str(value)) and str(value) not in into_parents:
                    into_parents.append(str(value))
            else:
                rendered.append(self.expression(value))
        return rendered

    def _describe_class(self, element: Element, node: URIRef) -> None:
        g = self.graph
        element.restrictions = self._named_or_expression(
            list(g.objects(node, RDFS.subClassOf)), element.parents
        )
        for eq in g.objects(node, OWL.equivalentClass):
            if isinstance(eq, URIRef):
                element.equivalents.append(str(eq))
                continue
            element.equivalents.append(self.expression(eq))
            # "A = B and (p some C)" makes B a named superclass of A.
            members = g.value(eq, OWL.intersectionOf)
            if members is not None:
                for member in self._list(members):
                    if (
                        isinstance(member, URIRef)
                        and not is_reserved(str(member))
                        and str(member) not in element.parents
                        and str(member) != element.iri
                    ):
                        element.parents.append(str(member))
        for eq in g.subjects(OWL.equivalentClass, node):
            if isinstance(eq, URIRef) and str(eq) not in element.equivalents:
                element.equivalents.append(str(eq))
        disjoint = set(g.objects(node, OWL.disjointWith)) | set(
            g.subjects(OWL.disjointWith, node)
        )
        for axiom in g.subjects(RDF.type, OWL.AllDisjointClasses):
            members = self._list(g.value(axiom, OWL.members))
            if node in members:
                disjoint.update(members)
        element.disjoint_with = sorted(
            str(d) for d in disjoint if isinstance(d, URIRef) and d != node
        )

    def _describe_property(self, element: Element, node: URIRef) -> None:
        g = self.graph
        self._named_or_expression(
            list(g.objects(node, RDFS.subPropertyOf)), element.parents
        )
        element.domain = [self.ref(d) for d in g.objects(node, RDFS.domain)]
        element.range = [self.ref(r) for r in g.objects(node, RDFS.range)]
        inverses = set(g.objects(node, OWL.inverseOf)) | set(
            g.subjects(OWL.inverseOf, node)
        )
        element.inverse_of = sorted(str(i) for i in inverses if isinstance(i, URIRef))
        element.characteristics = [
            word for typ, word in _CHARACTERISTICS.items() if (node, RDF.type, typ) in g
        ]

    def _describe_individual(self, element: Element, node: URIRef) -> None:
        g = self.graph
        element.types = [
            str(t)
            for t in g.objects(node, RDF.type)
            if isinstance(t, URIRef) and not is_reserved(str(t))
        ]
        for p, o in g.predicate_objects(node):
            if len(element.assertions) >= _MAX_ASSERTIONS:
                break
            if is_reserved(str(p)) or p in DEFINITION_PREDICATES:
                continue
            value = self.ref(o) if not isinstance(o, Literal) else str(o)
            element.assertions.append((str(p), value))

    def link_children(self) -> None:
        for element in self.elements.values():
            for parent in element.parents:
                target = self.elements.get(parent)
                if target is not None and element.iri not in target.children:
                    target.children.append(element.iri)

    def canonicalize(self) -> None:
        """Sort every list: rdflib's triple order changes between parses, and the
        documents (hence the vector cache keys) must not."""
        for e in self.elements.values():
            for name in (
                "alt_labels",
                "parents",
                "children",
                "equivalents",
                "restrictions",
                "domain",
                "range",
                "types",
            ):
                setattr(e, name, sorted(getattr(e, name)))
            e.assertions = sorted(e.assertions)


def build_ontology(graph: Graph, *, ontology_id: str, title: str = "") -> Ontology:
    """Turn a parsed *graph* into an :class:`Ontology`."""
    reader = _Reader(graph)
    reader.discover()
    for element in reader.elements.values():
        reader.describe(element)
    reader.link_children()
    reader.canonicalize()

    ontology_iri = ""
    declared_title = ""
    for s in graph.subjects(RDF.type, OWL.Ontology):
        if isinstance(s, URIRef):
            ontology_iri = str(s)
            declared_title = _pick(
                _literals(graph, s, (DCTERMS.title, DC.title, RDFS.label))
            )
            break
    prefixes = {
        prefix: str(ns)
        for prefix, ns in graph.namespaces()
        if not re.fullmatch(r"ns\d+", prefix) and prefix != "xml"
    }
    logger.info(
        "Loaded ontology %s: %d elements, %d triples",
        ontology_id,
        len(reader.elements),
        len(graph),
    )
    return Ontology(
        id=ontology_id,
        title=title or declared_title or ontology_id,
        graph=graph,
        elements=reader.elements,
        ontology_iri=ontology_iri,
        prefixes=prefixes,
    )


def load_ontology(
    data: bytes | str,
    *,
    ontology_id: str,
    title: str = "",
    filename: str = "",
    rdf_format: str = "",
) -> Ontology:
    """Parse *data* and build its :class:`Ontology` in one step."""
    graph = parse_graph(data, filename=filename, rdf_format=rdf_format)
    ontology = build_ontology(graph, ontology_id=ontology_id, title=title)
    if not ontology.elements:
        raise OntologyParseError(
            "The file parsed, but it declares no classes, properties or "
            "individuals outside the standard RDF/OWL vocabularies."
        )
    return ontology
