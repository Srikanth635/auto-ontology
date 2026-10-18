# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Align two loaded ontologies: which source element matches which target.

For each source element, candidates come from three signals -- identical
normalised labels, the source element's vector against the target's vectors,
and the source labels as a keyword query on the target. The fused top few are
then judged by the chat model in batches, which assigns the relation:

* ``equivalent`` -> ``owl:equivalentClass`` / ``owl:equivalentProperty``
* ``broader``    -> the target is more general: ``rdfs:subClassOf`` target
* ``narrower``   -> the target is more specific
* ``related``    -> ``skos:relatedMatch``

Results come back as JSON, SSSOM TSV (the standard mapping exchange format)
and Turtle. ``judge=False`` skips the model and returns the best candidate by
retrieval alone, which is quick and a reasonable first pass.
"""

from __future__ import annotations

import logging
from typing import Literal as TypingLiteral

from pydantic import BaseModel, Field

from auto_ontology.onto_query import ai
from auto_ontology.onto_query.model import ElementKind
from auto_ontology.onto_query.registry import LoadedOntology
from auto_ontology.onto_query.retrieval import render_element

logger = logging.getLogger(__name__)

_BATCH = 8

_PREDICATES = {
    "equivalent": "skos:exactMatch",
    "broader": "skos:broadMatch",
    "narrower": "skos:narrowMatch",
    "related": "skos:relatedMatch",
}


class MappingJudgement(BaseModel):
    source: str
    target: str = Field(
        default="", description="Chosen target IRI, empty if none fits."
    )
    relation: TypingLiteral["equivalent", "broader", "narrower", "related", "none"] = (
        Field(
            description="How the TARGET relates to the source: broader = target is more general."
        )
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class MappingBatch(BaseModel):
    mappings: list[MappingJudgement] = Field(default_factory=list)


_SYSTEM = """You align two ontologies. For each source element pick the single best
target among its candidates and say how the TARGET relates to the source:
equivalent (same meaning), broader (target more general), narrower (target more
specific), related, or none. Judge by definitions, parents and axioms, not labels
alone; similar labels with different meanings are 'none'. Use IRIs exactly."""


def _candidates(
    source: LoadedOntology,
    target: LoadedOntology,
    iri: str,
    kinds: set[ElementKind],
    k: int,
) -> list[tuple[str, float, bool]]:
    """``(target iri, fused score, label match)`` best first."""
    element = source.ontology.elements[iri]
    label_hits: list[str] = []
    for label in element.all_labels:
        for match in target.ontology.by_label(label):
            if match.kind in kinds and match.iri not in label_hits:
                label_hits.append(match.iri)
    dense: list[tuple[str, float]] = []
    vector = source.index.vector(iri)
    if (
        vector is not None
        and target.index.vectors is not None
        and source.index.space == target.index.space
    ):
        dense = target.index.dense_ranking_by_vector(vector, depth=k * 4, kinds=kinds)
    query = " ".join(element.all_labels[:3]) + " " + element.description[:200]
    keyword = target.index.keyword_ranking(query, depth=k * 4, kinds=kinds)
    fused = target.index.fuse(dense, keyword, k=k * 2)
    out: list[tuple[str, float, bool]] = [(i, 1.0, True) for i in label_hits]
    for hit in fused:
        if hit.iri not in label_hits:
            out.append((hit.iri, hit.score, False))
    return out[:k]


def align(
    source: LoadedOntology,
    target: LoadedOntology,
    *,
    kinds: set[ElementKind] | None = None,
    source_iris: list[str] | None = None,
    k: int = 5,
    judge: bool = True,
    max_sources: int = 100,
    offset: int = 0,
    min_confidence: float = 0.5,
) -> dict:
    kinds = kinds or {ElementKind.CLASS}
    if source_iris:
        pool = [i for i in source_iris if i in source.ontology.elements]
    else:
        pool = sorted(
            e.iri
            for e in source.ontology.elements.values()
            if e.kind in kinds and not e.deprecated
        )
    total = len(pool)
    batch_iris = pool[offset : offset + max_sources]
    warnings: list[str] = []
    if source.index.vectors is None or target.index.vectors is None:
        warnings.append(
            "Without embeddings on both sides, candidates come from labels only."
        )
    elif source.index.space != target.index.space:
        warnings.append(
            "The two ontologies were embedded with different models; reindex both "
            "so their vectors can be compared."
        )

    candidates = {iri: _candidates(source, target, iri, kinds, k) for iri in batch_iris}
    mappings: list[dict] = []

    def record(
        src: str,
        tgt: str,
        relation: str,
        confidence: float,
        reason: str,
        label_match: bool,
    ) -> None:
        mappings.append(
            {
                "source": {"iri": src, "name": source.ontology.name(src)},
                "target": {"iri": tgt, "name": target.ontology.name(tgt)},
                "relation": relation,
                "confidence": round(confidence, 3),
                "reason": reason,
                "label_match": label_match,
                "kind": source.ontology.elements[src].kind.value,
            }
        )

    if judge:
        todo = [iri for iri in batch_iris if candidates[iri]]
        for start in range(0, len(todo), _BATCH):
            chunk = todo[start : start + _BATCH]
            blocks = []
            for iri in chunk:
                lines = [
                    "SOURCE "
                    + render_element(source.ontology, source.ontology.elements[iri]),
                    "CANDIDATES:",
                ]
                lines.extend(
                    render_element(target.ontology, target.ontology.elements[c])
                    for c, _, _ in candidates[iri]
                )
                blocks.append("\n".join(lines))
            try:
                batch = ai.structured(
                    _SYSTEM, "\n\n=====\n\n".join(blocks), MappingBatch
                )
            except ai.OntoQueryModelError as exc:
                warnings.append(
                    f"Model review failed ({exc}); falling back to retrieval."
                )
                judge = False
                break
            for m in batch.mappings:
                allowed = {c for c, _, _ in candidates.get(m.source, [])}
                if (
                    m.source not in candidates
                    or m.relation == "none"
                    or m.target not in allowed
                ):
                    continue
                if m.confidence < min_confidence:
                    continue
                label_match = any(
                    c == m.target and lm for c, _, lm in candidates[m.source]
                )
                record(
                    m.source, m.target, m.relation, m.confidence, m.reason, label_match
                )
    if not judge:
        mappings = [
            m for m in mappings if m["reason"]
        ]  # keep anything judged before a failure
        judged_sources = {m["source"]["iri"] for m in mappings}
        for iri in batch_iris:
            if iri in judged_sources or not candidates[iri]:
                continue
            tgt, score, label_match = candidates[iri][0]
            record(
                iri,
                tgt,
                "equivalent" if label_match else "related",
                1.0 if label_match else min(1.0, score * 30),
                "",
                label_match,
            )
    return {
        "source": source.id,
        "target": target.id,
        "judged": judge,
        "total_sources": total,
        "offset": offset,
        "processed": len(batch_iris),
        "next_offset": offset + len(batch_iris)
        if offset + len(batch_iris) < total
        else None,
        "mappings": mappings,
        "unmatched": [
            {"iri": i, "name": source.ontology.name(i)}
            for i in batch_iris
            if i not in {m["source"]["iri"] for m in mappings}
        ],
        "warnings": warnings,
        "sssom_tsv": to_sssom(source, target, mappings),
        "turtle": to_turtle(mappings),
    }


def to_sssom(
    source: LoadedOntology, target: LoadedOntology, mappings: list[dict]
) -> str:
    header = [
        "# curie_map:",
        "#   skos: http://www.w3.org/2004/02/skos/core#",
        "#   semapv: https://w3id.org/semapv/vocab/",
        f"# subject_source: {source.ontology.ontology_iri or source.id}",
        f"# object_source: {target.ontology.ontology_iri or target.id}",
        "subject_id\tsubject_label\tpredicate_id\tobject_id\tobject_label\t"
        "mapping_justification\tconfidence\tcomment",
    ]
    rows = []
    for m in mappings:
        justification = (
            "semapv:LexicalMatching"
            if m["label_match"] and not m["reason"]
            else "semapv:SemanticSimilarityThresholdMatching"
            if not m["reason"]
            else "semapv:CompositeMatching"
        )
        comment = (m["reason"] or "").replace("\t", " ").replace("\n", " ")
        rows.append(
            "\t".join(
                [
                    m["source"]["iri"],
                    m["source"]["name"],
                    _PREDICATES[m["relation"]],
                    m["target"]["iri"],
                    m["target"]["name"],
                    justification,
                    str(m["confidence"]),
                    comment,
                ]
            )
        )
    return "\n".join(header + rows) + "\n"


def to_turtle(mappings: list[dict]) -> str:
    lines = [
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "",
    ]
    for m in mappings:
        s, t = f"<{m['source']['iri']}>", f"<{m['target']['iri']}>"
        is_class = m.get("kind", "class") == "class"
        equivalent = "owl:equivalentClass" if is_class else "owl:equivalentProperty"
        sub = "rdfs:subClassOf" if is_class else "rdfs:subPropertyOf"
        if m["relation"] == "equivalent" and m.get("kind") != "individual":
            lines.append(f"{s} {equivalent} {t} .")
        elif m["relation"] == "broader" and m.get("kind") != "individual":
            lines.append(f"{s} {sub} {t} .")
        elif m["relation"] == "narrower" and m.get("kind") != "individual":
            lines.append(f"{t} {sub} {s} .")
        elif m["relation"] == "equivalent":
            lines.append(f"{s} owl:sameAs {t} .")
        else:
            lines.append(f"{s} skos:relatedMatch {t} .")
    return "\n".join(lines) + "\n"
