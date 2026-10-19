# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auto_ontology.onto_query.loader import load_ontology
from auto_ontology.onto_query.reasoning import (
    ReasonerUnavailableError,
    hermit_available,
    reason,
    resolve_backend,
)
from auto_ontology.server.onto_query.router import router

E = "http://e.org/r#"

TBOX = f"""
@prefix : <{E}> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://e.org/r> a owl:Ontology .
:Object a owl:Class . :Tool a owl:Class ; rdfs:subClassOf :Object .
:Food a owl:Class ; rdfs:subClassOf :Object ; owl:disjointWith :Tool .
:Agent a owl:Class ; rdfs:subClassOf :Object .
:Edge a owl:Class .
:hasEdge a owl:ObjectProperty .
:holds a owl:ObjectProperty ; rdfs:domain :Agent ; rdfs:range :Object .
:isHeldBy a owl:ObjectProperty ; owl:inverseOf :holds .
# A defined class: anything that is a Tool with some Edge is a SharpTool.
:SharpTool a owl:Class ; owl:equivalentClass [ owl:intersectionOf ( :Tool
    [ a owl:Restriction ; owl:onProperty :hasEdge ; owl:someValuesFrom :Edge ] ) ] .
:Blade a owl:Class ; rdfs:subClassOf :Tool ,
    [ a owl:Restriction ; owl:onProperty :hasEdge ; owl:someValuesFrom :Edge ] .
# Unsatisfiable: both Food and Tool, which are disjoint.
:EdibleSpoon a owl:Class ; rdfs:subClassOf :Food , :Tool .
:alice a owl:NamedIndividual ; :holds :b1 .
:b1 a owl:NamedIndividual , :Blade .
"""


@pytest.fixture
def onto():  # noqa: ANN201
    return load_ontology(TBOX, ontology_id="r", rdf_format="turtle")


def test_owlrl_infers_types_and_inverses(onto) -> None:  # noqa: ANN001
    result = reason(onto, "owlrl")
    assert result.backend == "owlrl" and result.consistent
    assert (E + "alice", E + "Agent") in result.new_types  # from the domain of holds
    assert (E + "b1", E + "isHeldBy", E + "alice") in result.new_property_values
    # inherited types are already implied by b1's asserted Blade, so not "new"
    assert (E + "b1", E + "Tool") not in result.new_types
    # ...but they are in the inferred graph, so plain rdf:type queries find them
    from rdflib import URIRef
    from rdflib.namespace import RDF

    assert (URIRef(E + "b1"), RDF.type, URIRef(E + "Object")) in result.graph
    assert (
        f"<{E}alice> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{E}Agent> ."
        in result.turtle()
    )


def test_owlrl_detects_inconsistency() -> None:
    bad = load_ontology(
        TBOX + f"\n<{E}x> a <{E}Food> , <{E}Tool> .",
        ontology_id="bad",
        rdf_format="turtle",
    )
    result = reason(bad, "owlrl")
    assert not result.consistent and result.graph is None
    assert "Disjoint" in result.errors[0]


@pytest.mark.skipif(not hermit_available(), reason="HermiT needs Java")
def test_hermit_classifies_and_finds_unsatisfiable(onto) -> None:  # noqa: ANN001
    result = reason(onto, "hermit")
    assert result.backend == "hermit" and result.consistent
    assert (E + "Blade", E + "SharpTool") in result.new_superclasses
    assert E + "EdibleSpoon" in result.unsatisfiable
    # b1 is a Blade, so the inferred graph types it a SharpTool too
    from rdflib import URIRef
    from rdflib.namespace import RDF

    assert (URIRef(E + "b1"), RDF.type, URIRef(E + "SharpTool")) in result.graph


def test_backend_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_ontology.onto_query import reasoning

    monkeypatch.setattr(reasoning, "hermit_available", lambda: False)
    assert resolve_backend("auto") == "owlrl"
    with pytest.raises(ReasonerUnavailableError):
        resolve_backend("hermit")
    with pytest.raises(ValueError):
        resolve_backend("pellet")
    monkeypatch.setenv("ONTO_QUERY_REASONER", "owlrl")
    monkeypatch.setattr(reasoning, "hermit_available", lambda: True)
    assert resolve_backend("auto") == "owlrl"


def test_kept_result_is_replaced_for_another_backend(
    registry, embeddings, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    from auto_ontology.onto_query import reasoning

    monkeypatch.setattr(reasoning, "hermit_available", lambda: True)
    calls: list[str] = []

    class Fake:
        def __init__(self, backend: str) -> None:
            self.backend = backend

    def fake_reason(ontology, backend: str = "auto"):  # noqa: ANN001, ANN202
        calls.append(backend)
        return Fake(backend)

    monkeypatch.setattr(reasoning, "reason", fake_reason)
    loaded = registry.create(TBOX.encode(), filename="r.ttl")
    assert loaded.inferred("owlrl").backend == "owlrl"
    assert loaded.inferred("owlrl").backend == "owlrl"  # kept, not rerun
    assert loaded.inferred("hermit").backend == "hermit"
    assert calls == ["owlrl", "hermit"]


def test_routes(registry, embeddings) -> None:  # noqa: ANN001
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    created = client.post(
        "/api/ontologies", json={"content": TBOX, "filename": "r.ttl", "id": "r"}
    )
    assert created.status_code == 201
    assert "owlrl" in client.get("/api/ontologies/reasoners").json()["backends"]
    assert client.get("/api/ontologies/r/reason").json() == {"result": None}

    query = f"SELECT ?t WHERE {{ <{E}b1> a ?t }}"
    plain = client.post("/api/ontologies/r/sparql", json={"query": query}).json()
    assert {r["t"]["value"] for r in plain["result"]["rows"]} == {
        E + "Blade",
        "http://www.w3.org/2002/07/owl#NamedIndividual",
    }
    # use_inferences runs the reasoner on first use
    inferred = client.post(
        "/api/ontologies/r/sparql",
        json={"query": query, "use_inferences": True, "reasoner": "owlrl"},
    ).json()
    assert inferred["reasoning"] == {"backend": "owlrl", "consistent": True}
    assert {E + "Tool", E + "Object"} <= {
        r["t"]["value"] for r in inferred["result"]["rows"]
    }

    ran = client.post("/api/ontologies/r/reason", json={"backend": "owlrl"}).json()
    assert ran["consistent"] and ran["counts"]["new_types"] >= 1
    element = client.get(
        "/api/ontologies/r/element", params={"iri": E + "alice"}
    ).json()
    assert element["inferred"]["types"] == [{"iri": E + "Agent", "name": "Agent"}]
    summary = client.get("/api/ontologies/r").json()
    assert summary["reasoning"]["backend"] == "owlrl"

    # any change drops the stale result
    client.post("/api/ontologies/r/additions", json={"turtle": ":Fork a owl:Class ."})
    assert client.get("/api/ontologies/r/reason").json() == {"result": None}
    bad = client.post("/api/ontologies/r/reason", json={"backend": "pellet"})
    assert bad.status_code == 422
