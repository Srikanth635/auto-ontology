# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Answer a natural-language question with SPARQL over the ontology.

retrieve context -> write SPARQL -> check -> run -> repair (up to
``max_attempts``) -> answer from the rows.

The graph holds asserted triples only; no reasoner runs. The prompt therefore
teaches the model the patterns that make asserted OWL queryable: property
paths for the class hierarchy and the blank-node shape of restrictions.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from auto_ontology.onto_query import ai
from auto_ontology.onto_query.registry import LoadedOntology
from auto_ontology.onto_query.retrieval import render_context, retrieve_context
from auto_ontology.onto_query.sparql import (
    check_query,
    result_preview,
    result_size,
    run_query,
)

logger = logging.getLogger(__name__)

STANDARD_PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}


class SparqlDraft(BaseModel):
    answerable: bool = Field(
        description="False if the ontology cannot answer this question at all."
    )
    sparql: str = Field(default="", description="A complete SPARQL 1.1 query.")
    explanation: str = Field(
        description="One or two sentences: what the query looks for, or why it "
        "cannot be answered."
    )


class FinalAnswer(BaseModel):
    answer: str = Field(description="The answer for the user, in plain language.")


_SYSTEM = """You translate questions about an OWL/RDF ontology into SPARQL 1.1.

The query runs in rdflib over the ontology's asserted triples. There is NO
reasoner, so:
- hierarchy: `?c rdfs:subClassOf* <Class>` (or `+` for strict subclasses);
- members of a class, including its subclasses: `?x rdf:type/rdfs:subClassOf* <Class>`;
- an OWL restriction is a blank node:
  `<Class> rdfs:subClassOf ?r . ?r owl:onProperty <prop> ; owl:someValuesFrom ?filler .`
  (also owl:allValuesFrom, owl:hasValue, owl:onClass with cardinalities); restrictions
  may also sit inside `owl:equivalentClass [ owl:intersectionOf (...) ]`, reached with
  `owl:equivalentClass/owl:intersectionOf/rdf:rest*/rdf:first ?r`;
- inherited restrictions need `<Class> rdfs:subClassOf* ?sup . ?sup rdfs:subClassOf ?r`;
- labels are optional: `OPTIONAL { ?x rdfs:label|skos:prefLabel ?label }`.

Rules:
- Use only IRIs from the context below, written in full as <...>, or the standard
  prefixes rdf, rdfs, owl, xsd, skos (declare every prefix you use).
- Read-only: SELECT, ASK, CONSTRUCT or DESCRIBE. No SERVICE, no FROM.
- Prefer SELECT with DISTINCT and readable variables; add LIMIT 100 unless counting.
- If the context lacks what the question needs, set answerable=false and explain."""


def _prompt(loaded: LoadedOntology, question: str, context_text: str) -> str:
    ontology = loaded.ontology
    prefixes = {**STANDARD_PREFIXES, **{p: ns for p, ns in ontology.prefixes.items()}}
    prefix_lines = "\n".join(
        f"PREFIX {p}: <{ns}>" for p, ns in sorted(prefixes.items())
    )
    return (
        f"Ontology: {ontology.title} <{ontology.ontology_iri}>\n"
        f"Available prefixes (declare the ones you use):\n{prefix_lines}\n\n"
        f"Relevant part of the ontology:\n{context_text}\n\n"
        f"Question: {question}"
    )


def answer_question(
    loaded: LoadedOntology,
    question: str,
    *,
    max_attempts: int = 3,
    max_elements: int = 40,
) -> dict:
    ontology = loaded.ontology
    context = retrieve_context(loaded, question, max_elements=max_elements)
    context_text = render_context(ontology, context.iris)
    base_prompt = _prompt(loaded, question, context_text)
    out: dict = {
        "question": question,
        "answerable": True,
        "answer": "",
        "sparql": "",
        "explanation": "",
        "result": None,
        "attempts": [],
        "context": context.to_dict(ontology),
    }

    feedback = ""
    retried_empty = False
    result: dict | None = None
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        draft = ai.structured(_SYSTEM, base_prompt + feedback, SparqlDraft)
        record: dict = {
            "attempt": attempt,
            "sparql": draft.sparql,
            "explanation": draft.explanation,
        }
        out["attempts"].append(record)
        if not draft.answerable or not draft.sparql.strip():
            out.update(answerable=False, explanation=draft.explanation)
            out["answer"] = (
                "The ontology does not seem to contain what this question needs. "
                + draft.explanation
            )
            return out
        check = check_query(ontology, draft.sparql)
        record["check"] = check.to_dict()
        if not check.ok:
            feedback = (
                "\n\nYour previous query:\n"
                + draft.sparql
                + "\nwas rejected:\n- "
                + "\n- ".join(check.errors)
                + "\nWrite a corrected query."
            )
            continue
        try:
            result = run_query(ontology, check)
        except ValueError as exc:
            record["error"] = str(exc)
            feedback = (
                f"\n\nYour previous query:\n{draft.sparql}\nfailed: {exc}\n"
                "Write a corrected query."
            )
            continue
        record["rows"] = result_size(result)
        out.update(sparql=draft.sparql, explanation=draft.explanation, result=result)
        if result_size(result) == 0 and result["type"] != "ask" and not retried_empty:
            retried_empty = True
            feedback = (
                f"\n\nYour previous query:\n{draft.sparql}\nran but returned nothing. "
                "If the answer could exist, reconsider: subclass closure with "
                "rdfs:subClassOf*, restrictions as blank nodes (also inside "
                "owl:equivalentClass intersections), inherited restrictions, and "
                "making labels OPTIONAL. If nothing is genuinely there, return the "
                "same query."
            )
            continue
        break

    if result is None:
        last = out["attempts"][-1] if out["attempts"] else {}
        problems = (last.get("check") or {}).get("errors") or [last.get("error", "")]
        out["answer"] = (
            f"I could not produce a working query in {max_attempts} attempts. "
            "Last problem: " + "; ".join(p for p in problems if p)
        )
        return out

    try:
        final = ai.structured(
            "You answer a question from the results of a SPARQL query over an "
            "ontology. Use only the results; name things by their labels; if the "
            "results are empty, say the ontology states nothing that answers it. "
            "Be concise.",
            f"Question: {question}\n\nQuery:\n{out['sparql']}\n\n"
            f"Results:\n{result_preview(result)}",
            FinalAnswer,
            fast=True,
        )
        out["answer"] = final.answer
    except ai.OntoQueryModelError as exc:
        logger.warning("Answer phrasing failed: %s", exc)
        out["answer"] = result_preview(result, limit=20)
    return out
