# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Help an ontology grow: place new concepts, fill gaps, catch duplicates.

Every suggestion comes back as data plus a Turtle snippet. Nothing is changed
until the snippet is posted to the ontology's additions endpoint, so a person
always reviews what goes in.

* :func:`suggest_placement` -- where a new concept belongs, or that it exists.
* :func:`suggest_children` -- subclasses a class is likely missing.
* :func:`draft_definitions` -- genus-differentia definitions for classes.
* :func:`find_issues` -- duplicates, missing definitions, orphans, untyped
  properties, single-child classes and hierarchy cycles. Deterministic, with
  an optional model check of the duplicate pairs.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from typing import Literal as TypingLiteral

import numpy as np
from pydantic import BaseModel, Field
from rdflib import Literal, URIRef
from rdflib.namespace import RDFS, SKOS

from auto_ontology.onto_query import ai
from auto_ontology.onto_query.loader import IAO_DEFINITION, LABEL_PREDICATES
from auto_ontology.onto_query.model import ElementKind, Ontology
from auto_ontology.onto_query.registry import LoadedOntology
from auto_ontology.onto_query.retrieval import neighbours, render_context, search
from auto_ontology.onto_query.text import local_name, normalize_label

# ---------------------------------------------------------------------------
# Turtle helpers
# ---------------------------------------------------------------------------


def default_namespace(ontology: Ontology) -> str:
    """The namespace most of the ontology's elements share."""
    counts: Counter[str] = Counter()
    for iri in ontology.elements:
        name = local_name(iri)
        counts[iri[: len(iri) - len(name)]] += 1
    if counts:
        return counts.most_common(1)[0][0]
    base = ontology.ontology_iri or "http://example.org/ontology"
    return base if base.endswith(("#", "/")) else base + "#"


def mint_iri(ontology: Ontology, label: str, *, property_style: bool = False) -> str:
    """A fresh IRI in the ontology's namespace, in its naming style."""
    words = re.findall(r"[A-Za-z0-9]+", label) or ["NewConcept"]
    name = "".join(w[:1].upper() + w[1:] for w in words)
    if property_style:
        name = name[:1].lower() + name[1:]
    namespace = default_namespace(ontology)
    iri, n = namespace + name, 2
    while iri in ontology.elements or (URIRef(iri), None, None) in ontology.graph:
        iri, n = f"{namespace}{name}{n}", n + 1
    return iri


def definition_predicate(ontology: Ontology) -> URIRef:
    """The definition property this ontology already uses most."""
    g = ontology.graph
    counts = {
        SKOS.definition: sum(1 for _ in g.subject_objects(SKOS.definition)),
        IAO_DEFINITION: sum(1 for _ in g.subject_objects(IAO_DEFINITION)),
        RDFS.comment: sum(1 for _ in g.subject_objects(RDFS.comment)),
    }
    best = max(counts, key=counts.get)
    return best if counts[best] else SKOS.definition


def label_predicate(ontology: Ontology) -> URIRef:
    g = ontology.graph
    counts = {p: sum(1 for _ in g.subject_objects(p)) for p in LABEL_PREDICATES}
    best = max(counts, key=counts.get)
    return best if counts[best] else RDFS.label


def _lit(text: str) -> str:
    return Literal(text, lang="en").n3()


def class_turtle(
    ontology: Ontology,
    iri: str,
    *,
    label: str,
    parents: list[str],
    definition: str = "",
    alt_labels: list[str] | None = None,
) -> str:
    lines = [f"<{iri}> a <http://www.w3.org/2002/07/owl#Class>"]
    lines.extend(f"    <{RDFS.subClassOf}> <{p}>" for p in parents)
    lines.append(f"    <{label_predicate(ontology)}> {_lit(label)}")
    if definition:
        lines.append(f"    <{definition_predicate(ontology)}> {_lit(definition)}")
    for alt in alt_labels or []:
        lines.append(f"    <{SKOS.altLabel}> {_lit(alt)}")
    return " ;\n".join(lines) + " .\n"


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


class ParentChoice(BaseModel):
    iri: str
    reason: str


class PlacementProposal(BaseModel):
    existing_equivalent: str = Field(
        default="",
        description="IRI of a listed class that already means this concept, else empty.",
    )
    existing_reason: str = ""
    parents: list[ParentChoice] = Field(
        default_factory=list,
        description="The most specific listed classes the new concept is a kind of.",
    )
    label: str
    definition: str = Field(
        description="Genus-differentia: 'A <parent> that <distinguishing feature>.'"
    )
    alt_labels: list[str] = Field(default_factory=list)
    suggested_restrictions: list[str] = Field(
        default_factory=list,
        description="Axioms worth adding, in Manchester syntax with listed properties.",
    )
    confidence: float = Field(ge=0.0, le=1.0)


_PLACEMENT_SYSTEM = """You are an ontology engineer placing a new concept in an existing
OWL class hierarchy. From the listed classes choose the MOST SPECIFIC parent(s)
the concept is truly a kind of (is-a, not part-of or used-for). Usually one parent.
If a listed class already means the same thing, give it as existing_equivalent.
Use IRIs exactly as listed. Write the definition in genus-differentia form."""


def suggest_placement(loaded: LoadedOntology, name: str, description: str = "") -> dict:
    ontology = loaded.ontology
    query = f"{name}. {description}".strip()
    hits = search(loaded, query, k=12, kinds={ElementKind.CLASS}).hits
    iris = [h.iri for h in hits]
    for iri in list(iris):
        for parent in ontology.elements[iri].parents:
            if parent not in iris and len(iris) < 30:
                iris.append(parent)
    exact = [e.iri for e in ontology.by_label(name) if e.kind == ElementKind.CLASS]

    proposal = ai.structured(
        _PLACEMENT_SYSTEM,
        f"New concept: {name}\nDescription: {description or '(none given)'}\n\n"
        f"Candidate classes:\n{render_context(ontology, iris)}",
        PlacementProposal,
    )
    parents = [p for p in proposal.parents if p.iri in ontology.elements]
    equivalent = (
        proposal.existing_equivalent
        if proposal.existing_equivalent in ontology.elements
        else (exact[0] if exact else "")
    )
    new_iri = mint_iri(ontology, proposal.label or name)
    turtle = (
        ""
        if equivalent
        else class_turtle(
            ontology,
            new_iri,
            label=proposal.label or name,
            parents=[p.iri for p in parents],
            definition=proposal.definition,
            alt_labels=proposal.alt_labels,
        )
    )
    return {
        "name": name,
        "existing_equivalent": (
            {
                "iri": equivalent,
                "name": ontology.name(equivalent),
                "reason": proposal.existing_reason
                or "A class with the same label already exists.",
            }
            if equivalent
            else None
        ),
        "proposed_iri": None if equivalent else new_iri,
        "label": proposal.label or name,
        "definition": proposal.definition,
        "alt_labels": proposal.alt_labels,
        "parents": [
            {
                "iri": p.iri,
                "name": ontology.name(p.iri),
                "path": ontology.parent_path(p.iri),
                "reason": p.reason,
            }
            for p in parents
        ],
        "suggested_restrictions": proposal.suggested_restrictions,
        "confidence": round(proposal.confidence, 3),
        "turtle": turtle,
        "considered": [{"iri": i, "name": ontology.name(i)} for i in iris],
    }


# ---------------------------------------------------------------------------
# Missing subclasses
# ---------------------------------------------------------------------------


class ChildSuggestion(BaseModel):
    label: str
    definition: str
    reason: str = Field(description="Why the ontology is likely to need it.")


class ChildSuggestions(BaseModel):
    suggestions: list[ChildSuggestion] = Field(default_factory=list)


def suggest_children(loaded: LoadedOntology, iri: str, *, limit: int = 5) -> dict:
    ontology = loaded.ontology
    element = ontology.elements.get(iri)
    if element is None or element.kind != ElementKind.CLASS:
        raise KeyError(iri)
    context = [iri, *neighbours(ontology, element, children_limit=40)]
    for parent in element.parents:
        context.extend(
            c for c in ontology.elements[parent].children if c not in context
        )
    result = ai.structured(
        "You are an ontology engineer. Suggest direct subclasses the given class "
        "is missing, consistent with the ontology's scope, granularity and naming "
        "seen in its existing subclasses and siblings. Do not repeat existing "
        "classes or synonyms of them. Definitions in genus-differentia form.",
        f"Class: <{iri}> {element.name}\nSuggest at most {limit}.\n\n"
        f"Context:\n{render_context(ontology, context[:40])}",
        ChildSuggestions,
    )
    out = []
    for suggestion in result.suggestions[:limit]:
        existing = ontology.by_label(suggestion.label)
        new_iri = mint_iri(ontology, suggestion.label)
        out.append(
            {
                "label": suggestion.label,
                "definition": suggestion.definition,
                "reason": suggestion.reason,
                "possibly_existing": [{"iri": e.iri, "name": e.name} for e in existing],
                "proposed_iri": new_iri,
                "turtle": class_turtle(
                    ontology,
                    new_iri,
                    label=suggestion.label,
                    parents=[iri],
                    definition=suggestion.definition,
                ),
            }
        )
    return {"iri": iri, "name": element.name, "suggestions": out}


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------


class DraftDefinition(BaseModel):
    iri: str
    definition: str


class DraftDefinitions(BaseModel):
    definitions: list[DraftDefinition] = Field(default_factory=list)


def draft_definitions(
    loaded: LoadedOntology, iris: list[str] | None = None, *, limit: int = 20
) -> dict:
    """Definitions for *iris*, or for the first *limit* classes that lack one."""
    ontology = loaded.ontology
    if iris:
        targets = [i for i in iris if i in ontology.elements][:limit]
    else:
        targets = [
            e.iri
            for e in sorted(ontology.of_kind(ElementKind.CLASS), key=lambda e: e.name)
            if not e.description and not e.deprecated
        ][:limit]
    if not targets:
        return {"definitions": [], "predicate": str(definition_predicate(ontology))}
    context: list[str] = list(targets)
    for iri in targets:
        for n in neighbours(ontology, ontology.elements[iri], children_limit=4):
            if n not in context and len(context) < 80:
                context.append(n)
    result = ai.structured(
        "You write ontology definitions. For each target element write one "
        "genus-differentia definition ('A <parent> that ...') grounded in its "
        "parents, restrictions, properties and children as shown. Do not invent "
        "facts the context does not support; keep each under 40 words.",
        "Targets:\n"
        + "\n".join(f"<{i}>" for i in targets)
        + f"\n\nContext:\n{render_context(ontology, context)}",
        DraftDefinitions,
    )
    predicate = definition_predicate(ontology)
    out = []
    for draft in result.definitions:
        if draft.iri not in targets or not draft.definition.strip():
            continue
        out.append(
            {
                "iri": draft.iri,
                "name": ontology.name(draft.iri),
                "definition": draft.definition.strip(),
                "turtle": f"<{draft.iri}> <{predicate}> {_lit(draft.definition.strip())} .\n",
            }
        )
    return {"definitions": out, "predicate": str(predicate)}


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


class PairVerdict(BaseModel):
    a: str
    b: str
    verdict: TypingLiteral["same", "one_is_kind_of_other", "distinct"]
    reason: str


class PairVerdicts(BaseModel):
    verdicts: list[PairVerdict] = Field(default_factory=list)


def _relation(ontology: Ontology, a: str, b: str) -> str:
    if b in ontology.ancestors(a) or a in ontology.ancestors(b):
        return "ancestor/descendant"
    pa, pb = set(ontology.elements[a].parents), set(ontology.elements[b].parents)
    if pa & pb:
        return "siblings"
    return "elsewhere"


def find_issues(
    loaded: LoadedOntology,
    *,
    duplicate_threshold: float = 0.92,
    max_pairs: int = 50,
    confirm_duplicates: bool = False,
) -> dict:
    ontology = loaded.ontology
    classes = [e for e in ontology.of_kind(ElementKind.CLASS) if not e.deprecated]
    has_label = {
        str(s) for p in LABEL_PREDICATES for s in ontology.graph.subjects(p, None)
    }

    pairs: dict[tuple[str, str], dict] = {}
    by_key: dict[str, list[str]] = {}
    for element in ontology.elements.values():
        for label in element.all_labels:
            key = normalize_label(label)
            if key:
                by_key.setdefault(key, [])
                if element.iri not in by_key[key]:
                    by_key[key].append(element.iri)

    def group(iri: str) -> str:
        kind = ontology.elements[iri].kind
        return "property" if kind.is_property else kind.value

    for key, iris in by_key.items():
        for a, b in itertools.combinations(sorted(iris), 2):
            if group(a) != group(b):
                continue
            pairs.setdefault((a, b), {"evidence": []})["evidence"].append(
                f"shared label '{key}'"
            )

    index = loaded.index
    if index.vectors is not None and classes:
        positions = [
            index._position[e.iri] for e in classes if e.iri in index._position
        ]
        matrix = index.vectors[positions]
        sims = matrix @ matrix.T
        np.fill_diagonal(sims, -1.0)
        ii, jj = np.where(np.triu(sims) >= duplicate_threshold)
        order = np.argsort(-sims[ii, jj])[: max_pairs * 2]
        for k in order:
            a, b = sorted((index.iris[positions[ii[k]]], index.iris[positions[jj[k]]]))
            entry = pairs.setdefault((a, b), {"evidence": []})
            entry["similarity"] = round(float(sims[ii[k], jj[k]]), 4)
            entry["evidence"].append("near-identical embeddings")

    duplicates = [
        {
            "a": {"iri": a, "name": ontology.name(a)},
            "b": {"iri": b, "name": ontology.name(b)},
            "relation": _relation(ontology, a, b),
            **info,
        }
        for (a, b), info in pairs.items()
        if a in ontology.elements and b in ontology.elements
    ]
    duplicates.sort(key=lambda d: (-len(d["evidence"]), -(d.get("similarity") or 0)))
    duplicates = duplicates[:max_pairs]

    warnings: list[str] = []
    if index.vectors is None:
        warnings.append(
            "No embeddings, so only label-identical duplicates were checked."
        )
    if confirm_duplicates and duplicates:
        context: list[str] = []
        for d in duplicates[:25]:
            for side in ("a", "b"):
                if d[side]["iri"] not in context:
                    context.append(d[side]["iri"])
        try:
            verdicts = ai.structured(
                "You review possible duplicate concepts in an ontology. For each pair "
                "say whether they mean the same thing, one is a kind of the other, or "
                "they are distinct, citing definitions and axioms.",
                "Pairs:\n"
                + "\n".join(
                    f"<{d['a']['iri']}> vs <{d['b']['iri']}>" for d in duplicates[:25]
                )
                + f"\n\nContext:\n{render_context(ontology, context)}",
                PairVerdicts,
            )
            lookup = {tuple(sorted((v.a, v.b))): v for v in verdicts.verdicts}
            for d in duplicates:
                v = lookup.get(tuple(sorted((d["a"]["iri"], d["b"]["iri"]))))
                if v is not None:
                    d["verdict"], d["reason"] = v.verdict, v.reason
        except ai.OntoQueryModelError as exc:
            warnings.append(f"Duplicate pairs were not reviewed: {exc}")

    def ref(iri: str) -> dict:
        return {"iri": iri, "name": ontology.name(iri)}

    roots = [e for e in classes if not e.parents]
    cycles = [ref(e.iri) for e in classes if e.iri in ontology.ancestors(e.iri)]
    properties = [
        e
        for e in ontology.elements.values()
        if e.kind in (ElementKind.OBJECT_PROPERTY, ElementKind.DATATYPE_PROPERTY)
    ]
    deprecated_parents = sorted(
        {
            p
            for e in ontology.elements.values()
            for p in e.parents
            if getattr(ontology.get(p), "deprecated", False)
        }
    )
    return {
        "duplicates": duplicates,
        "missing_definitions": [ref(e.iri) for e in classes if not e.description],
        "missing_labels": [ref(e.iri) for e in classes if e.iri not in has_label],
        "root_classes": [ref(e.iri) for e in roots],
        "single_child_classes": [
            {**ref(e.iri), "child": ref(e.children[0])}
            for e in classes
            if len(e.children) == 1
        ],
        "properties_without_domain": [ref(e.iri) for e in properties if not e.domain],
        "properties_without_range": [ref(e.iri) for e in properties if not e.range],
        "hierarchy_cycles": cycles,
        "deprecated_parents": [ref(i) for i in deprecated_parents],
        "warnings": warnings,
    }
