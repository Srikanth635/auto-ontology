# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""From a question to the small piece of the ontology it is about.

1. **Mentions** -- the fast model lists the concepts the question names.
2. **Search** -- each mention, and the whole question, goes through hybrid
   search and the reranker.
3. **Expansion** -- the hits (the *seeds*) grow by a hop or two: parents and
   children, properties whose domain or range touches them, the properties and
   classes their restrictions use, the classes of an individual.
4. **Rendering** -- the result becomes a compact text block with full IRIs,
   which is all a downstream prompt ever sees of the ontology.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from auto_ontology.onto_query import ai
from auto_ontology.onto_query.index import Hit
from auto_ontology.onto_query.model import Element, ElementKind, Ontology
from auto_ontology.onto_query.registry import LoadedOntology
from auto_ontology.onto_query.rerank import rerank

logger = logging.getLogger(__name__)

_RESTRICTION_RE = re.compile(r"^\(?(.+?) (some|only|value|min|max|exactly|Self)\b")

KIND_GROUPS: dict[str, set[ElementKind]] = {
    "class": {ElementKind.CLASS},
    "property": {
        ElementKind.OBJECT_PROPERTY,
        ElementKind.DATATYPE_PROPERTY,
        ElementKind.ANNOTATION_PROPERTY,
    },
    "individual": {ElementKind.INDIVIDUAL},
}


def parse_kinds(values: list[str] | None) -> set[ElementKind] | None:
    """``["class", "object_property", "property"]`` -> a set of kinds; ``None`` = all."""
    if not values:
        return None
    kinds: set[ElementKind] = set()
    for value in values:
        if value in KIND_GROUPS:
            kinds |= KIND_GROUPS[value]
        else:
            kinds.add(ElementKind(value))
    return kinds


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@dataclass
class SearchOutcome:
    hits: list[Hit]
    reranker: str

    def to_dict(self, loaded: LoadedOntology) -> dict:
        ontology = loaded.ontology
        return {
            "reranker": self.reranker,
            "dense": loaded.index.vectors is not None,
            "results": [
                {
                    **hit.to_dict(),
                    "name": ontology.name(hit.iri),
                    "kind": ontology.elements[hit.iri].kind.value,
                    "definition": ontology.elements[hit.iri].description,
                    "path": ontology.parent_path(hit.iri),
                }
                for hit in self.hits
                if hit.iri in ontology.elements
            ],
        }


def search(
    loaded: LoadedOntology,
    query: str,
    *,
    k: int = 10,
    kinds: set[ElementKind] | None = None,
    use_rerank: bool = True,
    include_deprecated: bool = False,
) -> SearchOutcome:
    """Hybrid search, then (optionally) rerank the top ``2k`` and keep *k*."""
    pool = loaded.index.search(
        query,
        k=k * 2 if use_rerank else k,
        kinds=kinds,
        include_deprecated=include_deprecated,
    )
    backend = "none"
    if use_rerank:
        pool, backend = rerank(loaded.index, query, pool)
    return SearchOutcome(hits=pool[:k], reranker=backend)


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------


class Mention(BaseModel):
    text: str = Field(description="The phrase as it appears, or a close paraphrase.")
    kind: str = Field(
        description="What it most likely names: class, property, individual or any."
    )


class Mentions(BaseModel):
    mentions: list[Mention] = Field(default_factory=list)


_MENTION_SYSTEM = """You find the ontology concepts a question refers to.
List every distinct concept, relation or named thing the question mentions,
including implied ones (e.g. "what can cut bread" implies a cutting capability and bread).
Use short noun phrases. Do not answer the question. At most 8 mentions."""


def extract_mentions(question: str) -> list[Mention]:
    try:
        result = ai.structured(
            _MENTION_SYSTEM, f"Question: {question}", Mentions, fast=True
        )
    except ai.OntoQueryModelError as exc:
        logger.info("Mention extraction unavailable (%s); using the question", exc)
        return []
    seen: set[str] = set()
    out: list[Mention] = []
    for mention in result.mentions[:8]:
        key = mention.text.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(mention)
    return out


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class Context:
    """The retrieved piece of the ontology."""

    seeds: list[Hit]
    iris: list[str]
    mentions: list[Mention] = field(default_factory=list)
    reranker: str = "none"

    def to_dict(self, ontology: Ontology) -> dict:
        return {
            "mentions": [m.model_dump() for m in self.mentions],
            "reranker": self.reranker,
            "seeds": [
                {**h.to_dict(), "name": ontology.name(h.iri)} for h in self.seeds
            ],
            "elements": [
                {
                    "iri": iri,
                    "name": ontology.name(iri),
                    "kind": ontology.elements[iri].kind.value,
                }
                for iri in self.iris
                if iri in ontology.elements
            ],
        }


def _property_names(ontology: Ontology) -> dict[str, str]:
    from auto_ontology.onto_query.text import normalize_label

    names: dict[str, str] = {}
    for element in ontology.elements.values():
        if element.kind.is_property:
            for label in element.all_labels:
                names.setdefault(normalize_label(label), element.iri)
    return names


def neighbours(
    ontology: Ontology, element: Element, *, children_limit: int = 8
) -> list[str]:
    """One hop around *element*, most useful first."""
    from auto_ontology.onto_query.text import normalize_label

    out: list[str] = []

    def add(iri: str) -> None:
        if iri in ontology.elements and iri != element.iri and iri not in out:
            out.append(iri)

    if element.kind == ElementKind.CLASS:
        for parent in element.parents:
            add(parent)
        for child in element.children[:children_limit]:
            add(child)
        for eq in element.equivalents:
            add(eq)
        lineage = {element.iri, *ontology.ancestors(element.iri)}
        for prop in ontology.elements.values():
            if prop.kind.is_property and (lineage & set(prop.domain + prop.range)):
                add(prop.iri)
        prop_names = _property_names(ontology)
        for restriction in element.restrictions + element.equivalents:
            match = _RESTRICTION_RE.match(restriction)
            if match:
                prop = prop_names.get(normalize_label(match.group(1)))
                if prop:
                    add(prop)
            for other in ontology.by_label(restriction.rsplit(" ", 1)[-1].strip("()")):
                add(other.iri)
    elif element.kind.is_property:
        for iri in (
            element.domain + element.range + element.parents + element.inverse_of
        ):
            add(iri)
        for child in element.children[:children_limit]:
            add(child)
    else:
        for iri in element.types:
            add(iri)
        for prop, value in element.assertions:
            add(prop)
            add(value)
    return out


def retrieve_context(
    loaded: LoadedOntology,
    question: str,
    *,
    per_mention: int = 4,
    max_elements: int = 40,
    hops: int = 1,
    kinds: set[ElementKind] | None = None,
) -> Context:
    """Seeds from mentions and the whole question, expanded by *hops*."""
    ontology = loaded.ontology
    mentions = extract_mentions(question)
    seeds: dict[str, Hit] = {}
    reranker = "none"

    queries = [(question, 6)] + [(m.text, per_mention) for m in mentions]
    for query, k in queries:
        outcome = search(loaded, query, k=k, kinds=kinds)
        reranker = outcome.reranker if outcome.reranker != "none" else reranker
        for hit in outcome.hits:
            best = seeds.get(hit.iri)
            if best is None or hit.score > best.score:
                seeds[hit.iri] = hit
    ordered_seeds = sorted(seeds.values(), key=lambda h: h.score, reverse=True)

    iris: list[str] = [h.iri for h in ordered_seeds][:max_elements]
    frontier = list(iris)
    for _ in range(max(0, hops)):
        nxt: list[str] = []
        for iri in frontier:
            for neighbour in neighbours(ontology, ontology.elements[iri]):
                if neighbour not in iris and len(iris) < max_elements:
                    iris.append(neighbour)
                    nxt.append(neighbour)
        frontier = nxt
    return Context(seeds=ordered_seeds, iris=iris, mentions=mentions, reranker=reranker)


def render_element(ontology: Ontology, element: Element) -> str:
    """One element as prompt text, with full IRIs so a query can cite them."""

    def refs(values: list[str]) -> str:
        return ", ".join(
            f"<{v}> ({ontology.name(v)})" if v in ontology.elements else v
            for v in values[:10]
        )

    lines = [f'- <{element.iri}> [{element.kind.value}] "{element.name}"']
    if element.alt_labels:
        lines.append("  synonyms: " + ", ".join(element.alt_labels[:6]))
    if element.description:
        lines.append("  definition: " + element.description[:400])
    if element.parents:
        lines.append(
            (
                "  subClassOf: "
                if element.kind == ElementKind.CLASS
                else "  subPropertyOf: "
            )
            + refs(element.parents)
        )
    if element.equivalents:
        lines.append(
            "  equivalentTo: "
            + "; ".join(
                f"<{v}>" if v in ontology.elements else v
                for v in element.equivalents[:4]
            )
        )
    if element.restrictions:
        lines.append("  restrictions: " + "; ".join(element.restrictions[:8]))
    if element.disjoint_with:
        lines.append("  disjointWith: " + refs(element.disjoint_with))
    if element.domain:
        lines.append("  domain: " + refs(element.domain))
    if element.range:
        lines.append("  range: " + refs(element.range))
    if element.inverse_of:
        lines.append("  inverseOf: " + refs(element.inverse_of))
    if element.characteristics:
        lines.append("  characteristics: " + ", ".join(element.characteristics))
    if element.types:
        lines.append("  type: " + refs(element.types))
    for prop, value in element.assertions[:8]:
        lines.append(
            f"  <{prop}>: {value if value not in ontology.elements else f'<{value}>'}"
        )
    if element.children:
        more = len(element.children) - 8
        lines.append(
            "  direct subclasses/subproperties: "
            + refs(element.children[:8])
            + (f" (+{more} more)" if more > 0 else "")
        )
    return "\n".join(lines)


def render_context(ontology: Ontology, iris: list[str]) -> str:
    return "\n".join(
        render_element(ontology, ontology.elements[iri])
        for iri in iris
        if iri in ontology.elements
    )
