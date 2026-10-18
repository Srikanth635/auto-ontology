# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Candidates, growth, alignment and SHACL."""

from __future__ import annotations

from rdflib import URIRef
from rdflib.namespace import RDFS

from auto_ontology.onto_query import grow, shapes
from auto_ontology.onto_query.align import align
from auto_ontology.onto_query.candidates import find_candidates
from auto_ontology.onto_query.tests.conftest import H, K, iris_in

# -- candidates ---------------------------------------------------------------


def test_candidates_are_judged_and_ordered(kitchen, llm) -> None:  # noqa: ANN001
    def judge(user: str) -> dict:
        listed = iris_in(user)
        assert K + "Cup" in listed
        return {
            "judgements": [
                {
                    "iri": K + "Container",
                    "relation": "broader",
                    "confidence": 0.8,
                    "reason": "r",
                },
                {
                    "iri": K + "Cup",
                    "relation": "exact",
                    "confidence": 0.9,
                    "reason": "r",
                },
                {
                    "iri": K + "Bread",
                    "relation": "unrelated",
                    "confidence": 0.9,
                    "reason": "r",
                },
                {
                    "iri": "http://invented#X",
                    "relation": "exact",
                    "confidence": 1,
                    "reason": "r",
                },
            ],
            "suitable_exists": True,
            "summary": "Cup fits.",
        }

    llm.on("CandidateVerdict", judge)
    out = find_candidates(kitchen, "a small container to drink coffee from")
    assert out["judged"] and out["suitable_exists"]
    assert [c["iri"] for c in out["candidates"]] == [K + "Cup", K + "Container"]
    assert out["candidates"][0]["relation"] == "exact"


def test_candidates_without_a_model(kitchen, llm) -> None:  # noqa: ANN001
    out = find_candidates(kitchen, "drinking cup")
    assert not out["judged"] and out["warnings"]
    assert out["candidates"][0]["iri"] == K + "Cup"


# -- growing ------------------------------------------------------------------


def test_placement_produces_applicable_turtle(registry, kitchen, llm) -> None:  # noqa: ANN001
    llm.on(
        "PlacementProposal",
        lambda user: {
            "parents": [{"iri": K + "Tool", "reason": "a spatula is a tool"}],
            "label": "Spatula",
            "definition": "A tool with a broad flat blade for lifting food.",
            "alt_labels": ["turner"],
            "confidence": 0.8,
        },
    )
    out = grow.suggest_placement(kitchen, "spatula", "flat tool to flip pancakes")
    assert out["existing_equivalent"] is None
    assert out["proposed_iri"] == K + "Spatula"
    assert out["parents"][0]["path"] == ["Tool", "Physical object"]
    loaded, added = registry.add_triples(kitchen.id, out["turtle"])
    assert added == 5
    spatula = loaded.ontology.get(K + "Spatula")
    assert spatula.parents == [K + "Tool"] and spatula.alt_labels == ["turner"]
    assert spatula.definition.startswith("A tool with")
    assert (
        URIRef(K + "Spatula"),
        RDFS.subClassOf,
        URIRef(K + "Tool"),
    ) in loaded.ontology.graph


def test_placement_recognises_an_existing_class(kitchen, llm) -> None:  # noqa: ANN001
    llm.on(
        "PlacementProposal",
        lambda user: {
            "parents": [{"iri": K + "Container", "reason": "r"}],
            "label": "Mug",
            "definition": "A cup.",
            "confidence": 0.5,
        },
    )
    out = grow.suggest_placement(kitchen, "mug")
    assert out["existing_equivalent"]["iri"] in (K + "Mug", K + "Cup")
    assert out["turtle"] == ""


def test_children_and_definitions(kitchen, llm) -> None:  # noqa: ANN001
    llm.on(
        "ChildSuggestions",
        lambda user: {
            "suggestions": [
                {
                    "label": "Paring Knife",
                    "definition": "A small knife.",
                    "reason": "common",
                },
                {"label": "Bread Knife", "definition": "dup", "reason": "dup"},
            ]
        },
    )
    children = grow.suggest_children(kitchen, K + "Knife")
    assert children["suggestions"][0]["proposed_iri"] == K + "ParingKnife"
    assert children["suggestions"][1]["possibly_existing"][0]["iri"] == K + "BreadKnife"

    llm.on(
        "DraftDefinitions",
        lambda user: {
            "definitions": [
                {
                    "iri": K + "Mug",
                    "definition": "A container with a handle for hot drinks.",
                },
                {"iri": K + "Bread", "definition": "should be ignored: not a target"},
            ]
        },
    )
    drafts = grow.draft_definitions(kitchen)
    assert [d["iri"] for d in drafts["definitions"]] == [K + "Mug"]
    assert drafts["predicate"].endswith("core#definition")
    assert "skos/core#definition>" in drafts["definitions"][0]["turtle"]


def test_issues(kitchen, llm) -> None:  # noqa: ANN001
    llm.on(
        "PairVerdicts",
        lambda user: {
            "verdicts": [
                {
                    "a": K + "Cup",
                    "b": K + "Mug",
                    "verdict": "same",
                    "reason": "Cup lists mug as a synonym",
                },
            ]
        },
    )
    issues = grow.find_issues(kitchen, confirm_duplicates=True)
    pair = next(
        d
        for d in issues["duplicates"]
        if {d["a"]["iri"], d["b"]["iri"]} == {K + "Cup", K + "Mug"}
    )
    assert pair["relation"] == "siblings" and pair["verdict"] == "same"
    # "hasCapability" and "Capability" are different names, and different kinds
    assert not any(
        K + "hasCapability" in (d["a"]["iri"], d["b"]["iri"])
        for d in issues["duplicates"]
    )
    missing = {r["iri"] for r in issues["missing_definitions"]}
    assert missing == {K + "Mug", K + "PouringCapability"}
    assert {r["iri"] for r in issues["root_classes"]} == {
        K + "PhysicalObject",
        K + "Capability",
    }
    assert issues["hierarchy_cycles"] == []


# -- alignment ----------------------------------------------------------------


def test_align_by_retrieval(kitchen, household) -> None:  # noqa: ANN001
    out = align(kitchen, household, judge=False, source_iris=[K + "Knife", K + "Cup"])
    by_source = {m["source"]["iri"]: m for m in out["mappings"]}
    assert by_source[K + "Knife"]["target"]["iri"] == H + "Knife"
    assert (
        by_source[K + "Knife"]["label_match"]
        and by_source[K + "Knife"]["relation"] == "equivalent"
    )
    assert f"<{K}Knife> owl:equivalentClass <{H}Knife> ." in out["turtle"]
    assert "skos:exactMatch" in out["sssom_tsv"]


def test_align_judged(kitchen, household, llm) -> None:  # noqa: ANN001
    def judge(user: str) -> dict:
        assert "SOURCE" in user
        return {
            "mappings": [
                {
                    "source": K + "Cup",
                    "target": H + "Teacup",
                    "relation": "narrower",
                    "confidence": 0.7,
                    "reason": "a teacup is a kind of cup",
                },
                {
                    "source": K + "Bread",
                    "target": H + "Loaf",
                    "relation": "related",
                    "confidence": 0.3,
                    "reason": "below threshold",
                },
            ]
        }

    llm.on("MappingBatch", judge)
    out = align(kitchen, household, source_iris=[K + "Cup", K + "Bread"])
    assert out["judged"]
    assert [(m["source"]["iri"], m["relation"]) for m in out["mappings"]] == [
        (K + "Cup", "narrower")
    ]
    assert f"<{H}Teacup> rdfs:subClassOf <{K}Cup> ." in out["turtle"]
    assert out["unmatched"] == [{"iri": K + "Bread", "name": "Bread"}]


# -- shapes -------------------------------------------------------------------

BAD_DATA = """@prefix : <http://example.org/kitchen#> .
:r1 a :Robot ; :hasWeight "heavy" .
:bread1 a :Bread , :Tool .
:t1 a :CuttingTool .
"""


def test_derived_shapes_validate_data(kitchen) -> None:  # noqa: ANN001
    _, notes = shapes.derive_shapes(kitchen.ontology)
    assert "has weight has at most one value (functional)." in notes
    assert sum("Nothing is both" in n for n in notes) == 1
    out = shapes.validate(kitchen, data=BAD_DATA, data_format="turtle")
    assert not out["conforms"]
    kinds = {(r["focus_name"], r["constraint"]) for r in out["results"]}
    assert ("r1", "DatatypeConstraintComponent") in kinds
    assert ("bread1", "NotConstraintComponent") in kinds
    assert ("t1", "QualifiedMinCountConstraintComponent") in kinds
    assert (
        out["violations"] == 2 and out["warnings"] == 1
    )  # only nodes the data describes


def test_ontology_individuals_conform(kitchen) -> None:  # noqa: ANN001
    out = shapes.validate(kitchen)
    assert out["conforms"] and out["source"] == "the ontology's own individuals"


def test_rules_to_shapes_repairs_unknown_iris(kitchen, llm) -> None:  # noqa: ANN001
    good = f"""@prefix sh: <http://www.w3.org/ns/shacl#> .
<urn:onto-query:shape:robotRoom> a sh:NodeShape ; sh:targetClass <{K}Robot> ;
  sh:property [ sh:path <{K}locatedIn> ; sh:minCount 1 ; sh:message "A robot must be somewhere." ] ."""
    drafts = iter(
        [
            {"turtle": good.replace(K + "locatedIn", K + "isIn"), "notes": ["first"]},
            {"turtle": good, "notes": ["robots need a location"]},
        ]
    )
    llm.on("Mentions", lambda user: {"mentions": []})
    llm.on("ShapeDraft", lambda user: next(drafts))
    out = shapes.rules_to_shapes(kitchen, ["Every robot must be located somewhere"])
    assert out["ok"] and out["notes"] == ["robots need a location"]
    assert llm.count("ShapeDraft") == 2
    result = shapes.validate(
        kitchen,
        data=f"<{K}r9> a <{K}Robot> .",
        data_format="turtle",
        shapes_turtle=out["turtle"],
        use_derived=False,
    )
    assert result["violations"] == 1
    assert result["results"][0]["message"] == "A robot must be somewhere."
