# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auto_ontology.onto_query.tests.conftest import FIXTURES, H, K
from auto_ontology.server.onto_query.router import router


@pytest.fixture
def client(registry, embeddings) -> TestClient:  # noqa: ANN001
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _create(client: TestClient, name: str) -> dict:
    path = FIXTURES / name
    response = client.post(
        "/api/ontologies/upload",
        files={"file": (path.name, path.read_bytes(), "text/turtle")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_lifecycle(client: TestClient) -> None:
    created = _create(client, "kitchen.ttl")
    assert created["id"] == "kitchen" and created["counts"]["class"] == 16
    assert client.get("/api/ontologies").json()["ontologies"][0]["id"] == "kitchen"
    assert client.get("/api/ontologies/kitchen").json()["prefixes"][""] == K

    elements = client.get(
        "/api/ontologies/kitchen/elements", params={"kind": "class", "q": "knife"}
    )
    assert {e["name"] for e in elements.json()["elements"]} == {"Knife", "Bread Knife"}
    element = client.get(
        "/api/ontologies/kitchen/element", params={"iri": K + "Knife"}
    ).json()
    assert element["parents"][0]["name"] == "Cutting Tool"
    assert element["document"].startswith("Class: Knife")

    search = client.post(
        "/api/ontologies/kitchen/search", json={"query": "bread knife", "k": 3}
    )
    assert search.json()["results"][0]["iri"] == K + "BreadKnife"

    sparql = client.post(
        "/api/ontologies/kitchen/sparql",
        json={"query": f"SELECT ?i WHERE {{ ?i a <{K}BreadKnife> }}"},
    ).json()
    assert sparql["result"]["rows"][0]["i"]["name"] == "knife 1"
    rejected = client.post(
        "/api/ontologies/kitchen/sparql", json={"query": "DROP ALL"}
    ).json()
    assert rejected["result"] is None and not rejected["check"]["ok"]

    added = client.post(
        "/api/ontologies/kitchen/additions",
        json={"turtle": ":Fork a owl:Class ; rdfs:subClassOf :Tool ."},
    ).json()
    assert added["added_triples"] == 2 and added["counts"]["class"] == 17
    exported = client.get("/api/ontologies/kitchen/export", params={"format": "nt"})
    assert exported.headers["content-type"].startswith("application/n-triples")
    assert f"<{K}Fork>" in exported.text

    derived = client.get("/api/ontologies/kitchen/shapes/derived").json()
    assert "sh:NodeShape" in derived["turtle"]
    validated = client.post("/api/ontologies/kitchen/validate", json={}).json()
    assert validated["conforms"]

    assert client.delete("/api/ontologies/kitchen").json() == {"deleted": "kitchen"}
    assert client.get("/api/ontologies/kitchen").status_code == 404


def test_create_from_text_and_errors(client: TestClient) -> None:
    body = {
        "content": (FIXTURES / "household.ttl").read_text(),
        "filename": "h.ttl",
        "id": "house",
    }
    assert client.post("/api/ontologies", json=body).status_code == 201
    assert client.post("/api/ontologies", json=body).status_code == 422  # duplicate id
    bad = client.post(
        "/api/ontologies", json={"content": "not rdf {", "filename": "x.ttl"}
    )
    assert bad.status_code == 422
    reserved = client.post("/api/ontologies", json={**body, "id": "align"})
    assert reserved.status_code == 422
    assert (
        client.post("/api/ontologies/missing/search", json={"query": "x"}).status_code
        == 404
    )
    bad_kind = client.post(
        "/api/ontologies/house/search", json={"query": "x", "kinds": ["thing"]}
    )
    assert bad_kind.status_code == 422
    # no chat model configured: model-backed routes say so
    placement = client.post(
        "/api/ontologies/house/grow/placement", json={"name": "spoon"}
    )
    assert placement.status_code == 503 and "model" in placement.json()["detail"]


def test_align_route(client: TestClient) -> None:
    _create(client, "kitchen.ttl")
    _create(client, "household.ttl")
    out = client.post(
        "/api/ontologies/align",
        json={
            "source_id": "kitchen",
            "target_id": "household",
            "judge": False,
            "source_iris": [K + "Knife"],
        },
    ).json()
    assert out["mappings"][0]["target"]["iri"] == H + "Knife"
    assert out["sssom_tsv"].startswith("# curie_map:")
