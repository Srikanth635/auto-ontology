# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Find the ontology elements that best fit a free-text description.

"Something to pour liquid from" -> Jug (exact), Container (broader), Cup
(related). Useful for tagging data with ontology terms, linking mentions in
text, or checking whether a concept exists before adding it.

Retrieval proposes; the chat model judges each proposal against the
description and says how it relates. Without a chat model the retrieval
ranking is returned unjudged.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from auto_ontology.onto_query import ai
from auto_ontology.onto_query.model import ElementKind
from auto_ontology.onto_query.registry import LoadedOntology
from auto_ontology.onto_query.retrieval import render_context, search

Relation = Literal["exact", "broader", "narrower", "related", "unrelated"]

_RELATION_ORDER = {
    "exact": 0,
    "narrower": 1,
    "broader": 2,
    "related": 3,
    "unrelated": 4,
}


class CandidateJudgement(BaseModel):
    iri: str
    relation: Relation = Field(
        description=(
            "exact: the element means what is described; broader: the element is "
            "more general; narrower: more specific; related: associated but "
            "different; unrelated: no real fit."
        )
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(description="One sentence, citing the definition or axioms.")


class CandidateVerdict(BaseModel):
    judgements: list[CandidateJudgement] = Field(default_factory=list)
    suitable_exists: bool = Field(
        description="True if an exact or near-exact element exists."
    )
    summary: str = Field(description="One or two sentences for the user.")


_SYSTEM = """You match a description against elements of an ontology.
Judge every listed element: how does it relate to what the description means?
Base the judgement on the definitions, parents and restrictions shown, not on
the label alone. Use the IRIs exactly as given. Be strict about "exact"."""


def find_candidates(
    loaded: LoadedOntology,
    description: str,
    *,
    k: int = 8,
    kinds: set[ElementKind] | None = None,
    judge: bool = True,
    include_unrelated: bool = False,
) -> dict:
    ontology = loaded.ontology
    pool_size = min(max(k * 2, 10), 30)
    outcome = search(loaded, description, k=pool_size, kinds=kinds)
    pool = [h for h in outcome.hits if h.iri in ontology.elements]
    result: dict = {
        "description": description,
        "reranker": outcome.reranker,
        "judged": False,
        "suitable_exists": None,
        "summary": "",
        "warnings": [],
    }

    def entry(iri: str, retrieval_rank: int) -> dict:
        element = ontology.elements[iri]
        return {
            "iri": iri,
            "name": element.name,
            "kind": element.kind.value,
            "definition": element.description,
            "path": ontology.parent_path(iri),
            "retrieval_rank": retrieval_rank,
        }

    ranks = {h.iri: i + 1 for i, h in enumerate(pool)}
    if judge and pool:
        try:
            verdict = ai.structured(
                _SYSTEM,
                f"Description: {description}\n\nElements:\n"
                + render_context(ontology, [h.iri for h in pool]),
                CandidateVerdict,
            )
        except ai.OntoQueryModelError as exc:
            result["warnings"].append(f"{exc} Showing the retrieval ranking unjudged.")
        else:
            judged = [j for j in verdict.judgements if j.iri in ranks]
            if not include_unrelated:
                judged = [j for j in judged if j.relation != "unrelated"]
            judged.sort(
                key=lambda j: (_RELATION_ORDER[j.relation], -j.confidence, ranks[j.iri])
            )
            result.update(
                judged=True,
                suitable_exists=verdict.suitable_exists,
                summary=verdict.summary,
                candidates=[
                    {
                        **entry(j.iri, ranks[j.iri]),
                        "relation": j.relation,
                        "confidence": round(j.confidence, 3),
                        "reason": j.reason,
                    }
                    for j in judged[:k]
                ],
            )
            return result
    result["candidates"] = [entry(h.iri, i + 1) for i, h in enumerate(pool[:k])]
    return result
