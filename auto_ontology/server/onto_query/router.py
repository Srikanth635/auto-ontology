# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP routes for OntoQuerying: load an ontology, then search, ask, grow,
align and validate against it. See :mod:`auto_ontology.onto_query`."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from auto_ontology.onto_query import align as align_mod
from auto_ontology.onto_query import candidates as candidates_mod
from auto_ontology.onto_query import grow, qa, shapes
from auto_ontology.onto_query.ai import OntoQueryModelError
from auto_ontology.onto_query.loader import OntologyParseError
from auto_ontology.onto_query.registry import (
    EXPORT_FORMATS,
    LoadedOntology,
    OntologyNotFoundError,
    get_registry,
)
from auto_ontology.onto_query.rerank import backend_name
from auto_ontology.onto_query.retrieval import parse_kinds, retrieve_context, search
from auto_ontology.onto_query.sparql import check_query, run_query
from auto_ontology.server.onto_query.schemas import (
    AdditionsRequest,
    AlignRequest,
    AskRequest,
    CandidatesRequest,
    ChildrenRequest,
    ContextRequest,
    DefinitionsRequest,
    IssuesRequest,
    OntologyText,
    PlacementRequest,
    RulesRequest,
    SearchRequest,
    SparqlRequest,
    ValidateRequest,
)

router = APIRouter(prefix="/ontologies")


@contextmanager
def _errors() -> Iterator[None]:
    """Map the package's errors onto HTTP statuses."""
    try:
        yield
    except OntologyNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"No ontology {exc.args[0]!r}."
        ) from exc
    except OntologyParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OntoQueryModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"No element {exc.args[0]!r}."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _get(ontology_id: str) -> LoadedOntology:
    with _errors():
        return get_registry().get(ontology_id)


def _kinds(values: list[str] | None):  # noqa: ANN202
    try:
        return parse_kinds(values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown kind: {exc}") from exc


# -- ontologies ---------------------------------------------------------------


@router.get("")
def list_ontologies() -> dict:
    """Every stored ontology, with counts and index status once loaded."""
    return {"ontologies": get_registry().list(), "reranker": backend_name()}


@router.post("/upload", status_code=201)
async def upload_ontology(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    id: str = Form(default=""),
    format: str = Form(default=""),
    embed: bool = Query(default=True),
) -> dict:
    """Upload an OWL/RDF file (Turtle, RDF/XML, N-Triples, JSON-LD, N3), parse
    and index it. Indexing embeds every element, so large files take a while."""
    data = await file.read()

    def _create() -> dict:
        with _errors():
            loaded = get_registry().create(
                data,
                filename=file.filename or "",
                title=title,
                ontology_id=id,
                rdf_format=format,
                embed=embed,
            )
            return loaded.summary()

    return await run_in_threadpool(_create)


@router.post("", status_code=201)
def create_ontology(body: OntologyText, embed: bool = Query(default=True)) -> dict:
    """Create an ontology from source text in the request body."""
    with _errors():
        loaded = get_registry().create(
            body.content.encode("utf-8"),
            filename=body.filename,
            title=body.title,
            ontology_id=body.id,
            rdf_format=body.format,
            embed=embed,
        )
        return loaded.summary()


@router.get("/{ontology_id}")
def get_ontology(ontology_id: str) -> dict:
    """Counts, prefixes and index status of one ontology."""
    loaded = _get(ontology_id)
    return {**loaded.summary(), "prefixes": loaded.ontology.prefixes}


@router.delete("/{ontology_id}", status_code=204)
def delete_ontology(ontology_id: str) -> Response:
    """Delete an ontology, its stored files and its vectors."""
    with _errors():
        get_registry().delete(ontology_id)
    return Response(status_code=204)


@router.post("/{ontology_id}/reindex")
def reindex_ontology(ontology_id: str) -> dict:
    """Rebuild the index, e.g. after changing the embedding model."""
    with _errors():
        return get_registry().reindex(ontology_id).to_dict()


@router.get("/{ontology_id}/export")
def export_ontology(
    ontology_id: str, format: str = Query(default="turtle", enum=list(EXPORT_FORMATS))
) -> Response:
    """Download the working copy, including any additions."""
    with _errors():
        content, media_type, ext = get_registry().export(ontology_id, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{ontology_id}.{ext}"'},
    )


@router.get("/{ontology_id}/elements")
def list_elements(
    ontology_id: str,
    kind: list[str] | None = Query(default=None),
    q: str = Query(default="", description="Case-insensitive substring of the name."),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Browse elements by kind and name."""
    loaded = _get(ontology_id)
    kinds = _kinds(kind)
    needle = q.lower()
    items = [
        e
        for e in sorted(loaded.ontology.elements.values(), key=lambda e: e.name.lower())
        if (not kinds or e.kind in kinds) and (not needle or needle in e.name.lower())
    ]
    return {
        "total": len(items),
        "elements": [
            {
                "iri": e.iri,
                "name": e.name,
                "kind": e.kind.value,
                "definition": e.description,
            }
            for e in items[offset : offset + limit]
        ],
    }


@router.get("/{ontology_id}/element")
def get_element(ontology_id: str, iri: str = Query(...)) -> dict:
    """Everything known about one element, with its indexed document."""
    loaded = _get(ontology_id)
    element = loaded.ontology.get(iri)
    if element is None:
        raise HTTPException(status_code=404, detail=f"No element {iri!r}.")
    return {
        **element.to_dict(loaded.ontology),
        "path": loaded.ontology.parent_path(iri),
        "document": loaded.index.document(iri),
    }


# -- retrieval ----------------------------------------------------------------


@router.post("/{ontology_id}/search")
def search_ontology(ontology_id: str, body: SearchRequest) -> dict:
    """Hybrid (embedding + BM25) search, reranked when a reranker is available."""
    loaded = _get(ontology_id)
    with _errors():
        outcome = search(
            loaded,
            body.query,
            k=body.k,
            kinds=_kinds(body.kinds),
            use_rerank=body.rerank,
            include_deprecated=body.include_deprecated,
        )
    return {"query": body.query, **outcome.to_dict(loaded)}


@router.post("/{ontology_id}/candidates")
def find_candidates(ontology_id: str, body: CandidatesRequest) -> dict:
    """Elements that fit a description, each judged exact/broader/narrower/related."""
    loaded = _get(ontology_id)
    with _errors():
        return candidates_mod.find_candidates(
            loaded,
            body.description,
            k=body.k,
            kinds=_kinds(body.kinds),
            judge=body.judge,
            include_unrelated=body.include_unrelated,
        )


@router.post("/{ontology_id}/context")
def question_context(ontology_id: str, body: ContextRequest) -> dict:
    """The piece of the ontology a question is about, as used by /ask."""
    loaded = _get(ontology_id)
    with _errors():
        context = retrieve_context(
            loaded, body.question, max_elements=body.max_elements, hops=body.hops
        )
    return context.to_dict(loaded.ontology)


@router.post("/{ontology_id}/ask")
def ask(ontology_id: str, body: AskRequest) -> dict:
    """Answer a question: retrieve context, write and check SPARQL, run, answer."""
    loaded = _get(ontology_id)
    with _errors():
        return qa.answer_question(
            loaded,
            body.question,
            max_attempts=body.max_attempts,
            max_elements=body.max_elements,
        )


@router.post("/{ontology_id}/sparql")
def run_sparql(ontology_id: str, body: SparqlRequest) -> dict:
    """Check and run a read-only SPARQL query against the ontology graph."""
    loaded = _get(ontology_id)
    check = check_query(loaded.ontology, body.query)
    if not check.ok:
        return {"check": check.to_dict(), "result": None}
    with _errors():
        result = run_query(loaded.ontology, check)
    return {"check": check.to_dict(), "result": result}


# -- growing ------------------------------------------------------------------


@router.post("/{ontology_id}/grow/placement")
def suggest_placement(ontology_id: str, body: PlacementRequest) -> dict:
    """Where a new concept belongs (or that it already exists), with Turtle."""
    loaded = _get(ontology_id)
    with _errors():
        return grow.suggest_placement(loaded, body.name, body.description)


@router.post("/{ontology_id}/grow/children")
def suggest_children(ontology_id: str, body: ChildrenRequest) -> dict:
    """Subclasses a class is likely missing, with Turtle."""
    loaded = _get(ontology_id)
    with _errors():
        return grow.suggest_children(loaded, body.iri, limit=body.limit)


@router.post("/{ontology_id}/grow/definitions")
def draft_definitions(ontology_id: str, body: DefinitionsRequest) -> dict:
    """Draft definitions for given elements or for classes lacking one."""
    loaded = _get(ontology_id)
    with _errors():
        return grow.draft_definitions(loaded, body.iris, limit=body.limit)


@router.post("/{ontology_id}/grow/issues")
def find_issues(ontology_id: str, body: IssuesRequest) -> dict:
    """Duplicates, missing definitions/labels, orphans, untyped properties, cycles."""
    loaded = _get(ontology_id)
    with _errors():
        return grow.find_issues(
            loaded,
            duplicate_threshold=body.duplicate_threshold,
            max_pairs=body.max_pairs,
            confirm_duplicates=body.confirm_duplicates,
        )


@router.post("/{ontology_id}/additions")
def add_triples(ontology_id: str, body: AdditionsRequest) -> dict:
    """Add reviewed Turtle (e.g. from a /grow suggestion) to the working copy."""
    with _errors():
        loaded, added = get_registry().add_triples(ontology_id, body.turtle)
    return {"added_triples": added, **loaded.summary()}


# -- alignment ----------------------------------------------------------------


@router.post("/align")
def align_ontologies(body: AlignRequest) -> dict:
    """Match a source ontology's elements to a target's, as JSON, SSSOM and Turtle."""
    source, target = _get(body.source_id), _get(body.target_id)
    with _errors():
        return align_mod.align(
            source,
            target,
            kinds=_kinds(body.kinds),
            source_iris=body.source_iris,
            k=body.k,
            judge=body.judge,
            max_sources=body.max_sources,
            offset=body.offset,
            min_confidence=body.min_confidence,
        )


# -- shapes and validation ----------------------------------------------------


@router.get("/{ontology_id}/shapes/derived")
def derived_shapes(ontology_id: str) -> dict:
    """SHACL shapes derived from the ontology's own axioms."""
    loaded = _get(ontology_id)
    graph, notes = shapes.derive_shapes(loaded.ontology)
    return {"turtle": shapes.shapes_to_turtle(graph), "rules": notes}


@router.post("/{ontology_id}/shapes/from-rules")
def shapes_from_rules(ontology_id: str, body: RulesRequest) -> dict:
    """Turn plain-language rules into SHACL using the ontology's terms."""
    loaded = _get(ontology_id)
    with _errors():
        return shapes.rules_to_shapes(loaded, body.rules)


@router.post("/{ontology_id}/validate")
def validate_data(ontology_id: str, body: ValidateRequest) -> dict:
    """Validate RDF data (or the ontology's individuals) with SHACL."""
    loaded = _get(ontology_id)
    with _errors():
        return shapes.validate(
            loaded,
            data=body.data,
            data_format=body.data_format,
            shapes_turtle=body.shapes,
            use_derived=body.use_derived,
            explain=body.explain,
        )
