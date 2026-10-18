# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from auto_ontology.onto_query.model import ElementKind
from auto_ontology.onto_query.registry import OntologyRegistry
from auto_ontology.onto_query.retrieval import parse_kinds, retrieve_context, search
from auto_ontology.onto_query.tests.conftest import FIXTURES, K


def test_keyword_only_without_embeddings(
    registry: OntologyRegistry, no_embeddings
) -> None:  # noqa: ANN001
    loaded = registry.create(
        (FIXTURES / "kitchen.ttl").read_bytes(), filename="kitchen.ttl"
    )
    assert loaded.index.vectors is None
    assert any("keyword-only" in w for w in loaded.index.status.warnings)
    hits = search(loaded, "serrated bread knife", k=3).hits
    assert hits[0].iri == K + "BreadKnife"
    assert hits[0].dense_rank is None and hits[0].keyword_rank == 1


def test_hybrid_search_uses_both_rankings(kitchen) -> None:  # noqa: ANN001
    assert kitchen.index.status.dense
    hits = search(kitchen, "small container used for drinking", k=5).hits
    assert hits[0].iri == K + "Cup"
    assert hits[0].dense_rank is not None and hits[0].keyword_rank is not None


def test_kind_filter(kitchen) -> None:  # noqa: ANN001
    hits = search(
        kitchen, "weight of an object", k=5, kinds={ElementKind.DATATYPE_PROPERTY}
    ).hits
    assert [h.iri for h in hits] == [K + "hasWeight"]
    assert parse_kinds(["property"]) == {
        ElementKind.OBJECT_PROPERTY,
        ElementKind.DATATYPE_PROPERTY,
        ElementKind.ANNOTATION_PROPERTY,
    }


def test_vector_cache_is_reused_and_keyed_by_model(
    registry, kitchen, embeddings
) -> None:  # noqa: ANN001
    calls = embeddings["calls"]
    status = registry.reindex(kitchen.id)
    assert status.embedded == 0 and status.reused == len(kitchen.ontology.elements)
    assert embeddings["calls"] == calls
    embeddings["model"] = "fake-b"
    status = registry.reindex(kitchen.id)
    assert status.embedded == len(kitchen.ontology.elements)


def test_model_change_turns_dense_search_off(kitchen, embeddings) -> None:  # noqa: ANN001
    embeddings["model"] = "fake-b"
    hits = search(kitchen, "drinking mug", k=3).hits
    assert all(h.dense_rank is None for h in hits)


def test_restart_reads_from_disk(registry, kitchen, embeddings) -> None:  # noqa: ANN001
    fresh = OntologyRegistry(registry.root)
    calls = embeddings["calls"]
    loaded = fresh.get(kitchen.id)
    assert loaded.ontology.stats() == kitchen.ontology.stats()
    assert embeddings["calls"] == calls  # vectors came from the cache
    assert loaded.index.vectors is not None


def test_context_expands_neighbours(kitchen, llm) -> None:  # noqa: ANN001
    llm.on(
        "Mentions",
        lambda user: {"mentions": [{"text": "bread knife", "kind": "class"}]},
    )
    context = retrieve_context(kitchen, "Which tools can a robot use?", max_elements=30)
    assert K + "BreadKnife" in context.iris
    # one hop: the knife's parent, and properties whose domain/range touch Tool
    assert K + "Knife" in context.iris
    assert K + "uses" in context.iris
    assert context.mentions[0].text == "bread knife"


def test_context_survives_mention_failure(kitchen, llm) -> None:  # noqa: ANN001
    context = retrieve_context(kitchen, "what holds food", max_elements=10)
    assert context.mentions == []
    assert context.iris
