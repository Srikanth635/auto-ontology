# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The in-memory view of a loaded ontology."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Iterable

from auto_ontology.onto_query.text import humanize, local_name, normalize_label

if TYPE_CHECKING:
    from rdflib import Graph


class ElementKind(StrEnum):
    CLASS = "class"
    OBJECT_PROPERTY = "object_property"
    DATATYPE_PROPERTY = "datatype_property"
    ANNOTATION_PROPERTY = "annotation_property"
    INDIVIDUAL = "individual"

    @property
    def title(self) -> str:
        return self.value.replace("_", " ").capitalize()

    @property
    def is_property(self) -> bool:
        return self in PROPERTY_KINDS


PROPERTY_KINDS = frozenset(
    {
        ElementKind.OBJECT_PROPERTY,
        ElementKind.DATATYPE_PROPERTY,
        ElementKind.ANNOTATION_PROPERTY,
    }
)


@dataclass
class Element:
    """One named class, property or individual, with what describes it.

    IRIs are kept as strings. ``domain``, ``range``, ``restrictions`` and
    ``equivalents`` may hold either an IRI or a rendered class expression such
    as ``hasTopping some CheeseTopping``; :meth:`Ontology.name` turns an IRI
    into its label for display and leaves an expression alone.
    """

    iri: str
    kind: ElementKind
    label: str = ""
    alt_labels: list[str] = field(default_factory=list)
    definition: str = ""
    comment: str = ""
    #: Direct named superclasses (classes) or superproperties (properties).
    parents: list[str] = field(default_factory=list)
    #: Direct named subclasses / subproperties; filled in after loading.
    children: list[str] = field(default_factory=list)
    equivalents: list[str] = field(default_factory=list)
    disjoint_with: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    domain: list[str] = field(default_factory=list)
    range: list[str] = field(default_factory=list)
    inverse_of: list[str] = field(default_factory=list)
    characteristics: list[str] = field(default_factory=list)
    #: Asserted classes of an individual.
    types: list[str] = field(default_factory=list)
    #: ``(property IRI, value)`` assertions on an individual.
    assertions: list[tuple[str, str]] = field(default_factory=list)
    deprecated: bool = False

    @property
    def name(self) -> str:
        return self.label or humanize(local_name(self.iri))

    @property
    def all_labels(self) -> list[str]:
        seen: list[str] = []
        for label in [self.name, humanize(local_name(self.iri)), *self.alt_labels]:
            if label and label not in seen:
                seen.append(label)
        return seen

    @property
    def description(self) -> str:
        return self.definition or self.comment

    def to_dict(self, ontology: Ontology | None = None) -> dict:
        """JSON-ready view; with *ontology*, IRIs gain their display names."""

        def refs(values: Iterable[str]) -> list[dict[str, str]] | list[str]:
            values = list(values)
            if ontology is None:
                return values
            return [{"iri": v, "name": ontology.name(v)} for v in values]

        return {
            "iri": self.iri,
            "kind": self.kind.value,
            "name": self.name,
            "alt_labels": self.alt_labels,
            "definition": self.definition,
            "comment": self.comment,
            "parents": refs(self.parents),
            "children": refs(self.children),
            "equivalents": refs(self.equivalents),
            "disjoint_with": refs(self.disjoint_with),
            "restrictions": self.restrictions,
            "domain": refs(self.domain),
            "range": refs(self.range),
            "inverse_of": refs(self.inverse_of),
            "characteristics": self.characteristics,
            "types": refs(self.types),
            "assertions": [
                {
                    "property": p,
                    "property_name": ontology.name(p) if ontology else p,
                    "value": ontology.name(v) if ontology else v,
                }
                for p, v in self.assertions
            ],
            "deprecated": self.deprecated,
        }


@dataclass
class Ontology:
    """A parsed ontology: the rdflib graph plus one :class:`Element` per name."""

    id: str
    title: str
    graph: Graph
    elements: dict[str, Element]
    ontology_iri: str = ""
    #: ``prefix -> namespace`` as declared in the source, for SPARQL prompts.
    prefixes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._by_label: dict[str, list[str]] = {}
        for element in self.elements.values():
            for label in element.all_labels:
                key = normalize_label(label)
                if key:
                    self._by_label.setdefault(key, []).append(element.iri)

    def get(self, iri: str) -> Element | None:
        return self.elements.get(iri)

    def name(self, iri_or_expression: str) -> str:
        """The display name of an element IRI; anything else comes back as is."""
        element = self.elements.get(iri_or_expression)
        if element is not None:
            return element.name
        if iri_or_expression.startswith(("http://", "https://", "urn:")):
            return humanize(local_name(iri_or_expression))
        return iri_or_expression

    def by_label(self, label: str) -> list[Element]:
        """Elements one of whose labels normalises to the same key as *label*."""
        return [
            self.elements[iri] for iri in self._by_label.get(normalize_label(label), [])
        ]

    def of_kind(self, *kinds: ElementKind) -> list[Element]:
        wanted = set(kinds)
        return [e for e in self.elements.values() if e.kind in wanted]

    def ancestors(self, iri: str, *, max_depth: int = 32) -> list[str]:
        """Every named ancestor of *iri*, nearest first, cycle-safe."""
        seen: list[str] = []
        frontier = list(self.elements[iri].parents) if iri in self.elements else []
        depth = 0
        while frontier and depth < max_depth:
            nxt: list[str] = []
            for parent in frontier:
                if parent in seen or parent == iri:
                    continue
                seen.append(parent)
                element = self.elements.get(parent)
                if element is not None:
                    nxt.extend(element.parents)
            frontier = nxt
            depth += 1
        return seen

    def descendants(self, iri: str, *, limit: int = 10_000) -> list[str]:
        seen: list[str] = []
        frontier = list(self.elements[iri].children) if iri in self.elements else []
        while frontier and len(seen) < limit:
            child = frontier.pop(0)
            if child in seen or child == iri:
                continue
            seen.append(child)
            element = self.elements.get(child)
            if element is not None:
                frontier.extend(element.children)
        return seen

    def parent_path(self, iri: str, *, max_depth: int = 12) -> list[str]:
        """Labels from *iri* up its first-parent chain: ``[self, parent, ...]``."""
        path: list[str] = []
        current = self.elements.get(iri)
        visited: set[str] = set()
        while current is not None and current.iri not in visited:
            visited.add(current.iri)
            path.append(current.name)
            if len(path) > max_depth or not current.parents:
                break
            current = self.elements.get(current.parents[0])
        return path

    def stats(self) -> dict[str, int]:
        counts = {kind.value: 0 for kind in ElementKind}
        for element in self.elements.values():
            counts[element.kind.value] += 1
        counts["triples"] = len(self.graph)
        return counts
