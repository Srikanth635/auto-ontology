# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from auto_ontology.onto_query.qa import answer_question
from auto_ontology.onto_query.sparql import check_query, run_query
from auto_ontology.onto_query.tests.conftest import K

SUBCLASSES = f"""PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?c WHERE {{ ?c rdfs:subClassOf+ <{K}Tool> }}"""


def test_check_and_run(kitchen) -> None:  # noqa: ANN001
    check = check_query(kitchen.ontology, SUBCLASSES)
    assert check.ok, check.errors
    result = run_query(kitchen.ontology, check)
    names = {row["c"]["name"] for row in result["rows"]}
    assert names == {"Cutting Tool", "Knife", "Bread Knife"}


def test_unknown_iri_names_the_closest(kitchen) -> None:  # noqa: ANN001
    check = check_query(kitchen.ontology, f"SELECT ?x WHERE {{ ?x a <{K}knife> }}")
    assert not check.ok
    assert f"<{K}Knife>" in check.errors[0]


def test_read_only_and_local(kitchen) -> None:  # noqa: ANN001
    for query in (
        "INSERT DATA { <http://a> <http://b> <http://c> }",
        "SELECT * WHERE { SERVICE <http://dbpedia.org/sparql> { ?s ?p ?o } }",
        "SELECT * FROM <http://evil.example/x.ttl> WHERE { ?s ?p ?o }",
    ):
        assert not check_query(kitchen.ontology, query).ok, query
    # keywords inside names, variables and strings are fine
    ok = check_query(
        kitchen.ontology,
        'SELECT ?from WHERE { ?from <http://www.w3.org/2000/01/rdf-schema#label> "INSERT" }',
    )
    assert ok.ok, ok.errors


def test_domain_warning_and_ask(kitchen) -> None:  # noqa: ANN001
    check = check_query(
        kitchen.ontology, f"SELECT ?x WHERE {{ ?x a <{K}Bread> ; <{K}uses> ?t }}"
    )
    assert check.ok and "domain of uses" in check.warnings[0]
    ask = check_query(
        kitchen.ontology,
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
        f"ASK {{ <{K}BreadKnife> rdfs:subClassOf+ <{K}Tool> }}",
    )
    assert run_query(kitchen.ontology, ask) == {"type": "ask", "boolean": True}


def test_answer_repairs_an_invented_iri(kitchen, mentions_none) -> None:  # noqa: ANN001
    drafts = iter(
        [
            {
                "answerable": True,
                "sparql": f"SELECT ?c WHERE {{ ?c <{K}subToolOf> <{K}Tool> }}",
                "explanation": "first try",
            },
            {
                "answerable": True,
                "sparql": SUBCLASSES,
                "explanation": "subclasses of Tool",
            },
        ]
    )
    mentions_none.on("SparqlDraft", lambda user: next(drafts))
    mentions_none.on(
        "FinalAnswer", lambda user: {"answer": "Cutting tools, knives, bread knives."}
    )
    out = answer_question(kitchen, "What kinds of tools are there?")
    assert len(out["attempts"]) == 2
    assert not out["attempts"][0]["check"]["ok"]
    assert out["sparql"] == SUBCLASSES
    assert out["result"]["type"] == "select" and len(out["result"]["rows"]) == 3
    assert out["answer"].startswith("Cutting tools")
    # the repair prompt carried the rejection
    repair = [c for c in mentions_none.calls if c["schema"] == "SparqlDraft"][1]["user"]
    assert "subToolOf" in repair and "not in the ontology" in repair


def test_empty_result_gets_one_retry(kitchen, mentions_none) -> None:  # noqa: ANN001
    empty = f"SELECT ?x WHERE {{ ?x a <{K}Bowl> }}"
    mentions_none.on(
        "SparqlDraft",
        lambda user: {"answerable": True, "sparql": empty, "explanation": "bowls"},
    )
    mentions_none.on("FinalAnswer", lambda user: {"answer": "None are stated."})
    out = answer_question(kitchen, "Which bowls exist?")
    assert mentions_none.count("SparqlDraft") == 2
    assert out["result"]["rows"] == []
    assert out["answer"] == "None are stated."


def test_unanswerable(kitchen, mentions_none) -> None:  # noqa: ANN001
    mentions_none.on(
        "SparqlDraft",
        lambda user: {
            "answerable": False,
            "sparql": "",
            "explanation": "Nothing about prices.",
        },
    )
    out = answer_question(kitchen, "How much does a knife cost?")
    assert out["answerable"] is False
    assert "Nothing about prices" in out["answer"]


def test_context_reaches_the_prompt(kitchen, llm) -> None:  # noqa: ANN001
    llm.on(
        "Mentions",
        lambda user: {"mentions": [{"text": "bread knife", "kind": "class"}]},
    )
    llm.on(
        "SparqlDraft",
        lambda user: {"answerable": True, "sparql": SUBCLASSES, "explanation": "x"},
    )
    llm.on("FinalAnswer", lambda user: {"answer": "ok"})
    answer_question(kitchen, "Is a bread knife a tool?")
    prompt = next(c for c in llm.calls if c["schema"] == "SparqlDraft")["user"]
    assert f"<{K}BreadKnife>" in prompt
    assert "PREFIX rdfs:" in prompt
