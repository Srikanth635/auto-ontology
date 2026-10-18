# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from auto_ontology.onto_query.documents import element_document
from auto_ontology.onto_query.loader import OntologyParseError, load_ontology
from auto_ontology.onto_query.model import ElementKind
from auto_ontology.onto_query.tests.conftest import FIXTURES, K


@pytest.fixture
def onto():  # noqa: ANN201
    return load_ontology(
        (FIXTURES / "kitchen.ttl").read_bytes(),
        ontology_id="kitchen",
        filename="kitchen.ttl",
    )


def test_counts_and_title(onto) -> None:  # noqa: ANN001
    stats = onto.stats()
    assert stats["class"] == 16
    assert stats["object_property"] == 3
    assert stats["datatype_property"] == 1
    assert stats["individual"] == 3
    assert onto.title == "Kitchen ontology"
    assert onto.ontology_iri == "http://example.org/kitchen"
    assert "" in onto.prefixes and "brick" not in onto.prefixes


def test_class_description(onto) -> None:  # noqa: ANN001
    knife = onto.get(K + "Knife")
    assert knife.kind == ElementKind.CLASS
    assert knife.name == "Knife"
    assert knife.alt_labels == ["blade"]
    assert knife.parents == [K + "CuttingTool"]
    assert K + "BreadKnife" in knife.children
    assert onto.parent_path(K + "BreadKnife") == [
        "Bread Knife",
        "Knife",
        "Cutting Tool",
        "Tool",
        "Physical object",
    ]
    cutting = onto.get(K + "CuttingTool")
    assert cutting.restrictions == ["has capability some Cutting Capability"]
    assert onto.get(K + "Food").disjoint_with == [K + "Tool"]
    assert onto.get(K + "Tool").disjoint_with == [K + "Food"]


def test_property_and_individual(onto) -> None:  # noqa: ANN001
    weight = onto.get(K + "hasWeight")
    assert weight.kind == ElementKind.DATATYPE_PROPERTY
    assert weight.characteristics == ["functional"]
    assert weight.domain == [K + "PhysicalObject"]
    knife1 = onto.get(K + "knife1")
    assert knife1.kind == ElementKind.INDIVIDUAL
    assert knife1.types == [K + "BreadKnife"]
    assert (K + "locatedIn", K + "drawer1") in knife1.assertions


def test_document_includes_path_and_restrictions(onto) -> None:  # noqa: ANN001
    doc = element_document(onto, onto.get(K + "CuttingTool"))
    assert "Is a: Cutting Tool -> Tool -> Physical object" in doc
    assert "Restrictions: has capability some Cutting Capability" in doc


def test_intersection_gives_named_parent() -> None:
    ttl = """
    @prefix : <http://e.org/p#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :Pizza a owl:Class . :Topping a owl:Class . :hasTopping a owl:ObjectProperty .
    :CheesyPizza a owl:Class ; owl:equivalentClass [ owl:intersectionOf ( :Pizza
        [ a owl:Restriction ; owl:onProperty :hasTopping ; owl:someValuesFrom :Topping ] ) ] .
    """
    onto = load_ontology(ttl, ontology_id="p", rdf_format="turtle")
    cheesy = onto.get("http://e.org/p#CheesyPizza")
    assert cheesy.parents == ["http://e.org/p#Pizza"]
    assert cheesy.equivalents == ["Pizza and (has topping some Topping)"]


def test_non_english_labels_fall_back_to_local_name() -> None:
    ttl = """
    @prefix : <http://e.org/p#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :MozzarellaTopping a owl:Class ; rdfs:label "CoberturaDeMozzarella"@pt .
    :C0001 a owl:Class ; rdfs:label "Queijo"@pt .
    """
    onto = load_ontology(ttl, ontology_id="p", rdf_format="turtle")
    topping = onto.get("http://e.org/p#MozzarellaTopping")
    assert topping.name == "Mozzarella Topping"
    assert "CoberturaDeMozzarella" in topping.alt_labels
    assert onto.get("http://e.org/p#C0001").name == "Queijo"


def test_rdf_xml_is_read() -> None:
    xml = """<?xml version="1.0"?>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
             xmlns:owl="http://www.w3.org/2002/07/owl#"
             xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
      <owl:Class rdf:about="http://e.org/x#A"><rdfs:label>A thing</rdfs:label></owl:Class>
    </rdf:RDF>"""
    onto = load_ontology(xml, ontology_id="x", filename="x.owl")
    assert onto.get("http://e.org/x#A").name == "A thing"


def test_rejects_manchester_and_empty() -> None:
    with pytest.raises(OntologyParseError, match="Manchester"):
        load_ontology(
            "Prefix: : <http://e.org/>\nOntology: <http://e.org/>", ontology_id="m"
        )
    with pytest.raises(OntologyParseError, match="no classes"):
        load_ontology(
            '<http://e.org/a> <http://www.w3.org/2000/01/rdf-schema#label> "x" .',
            ontology_id="e",
            rdf_format="nt",
        )
    with pytest.raises(OntologyParseError, match="Could not read"):
        load_ontology("this is not rdf {", ontology_id="bad")
