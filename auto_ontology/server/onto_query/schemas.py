# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request bodies for the OntoQuerying routes."""

from __future__ import annotations

from pydantic import BaseModel, Field

_KINDS_HELP = (
    "Restrict to element kinds: class, property (all three property kinds), "
    "object_property, datatype_property, annotation_property, individual."
)


class OntologyText(BaseModel):
    """An ontology sent as text rather than as a file upload."""

    content: str = Field(description="The ontology source (Turtle, RDF/XML, ...).")
    filename: str = Field(
        default="", description="Used to guess the format, e.g. 'x.ttl'."
    )
    title: str = ""
    id: str = Field(
        default="", description="Optional id; derived from the title if empty."
    )
    format: str = Field(default="", description="rdflib format name, e.g. turtle, xml.")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=10, ge=1, le=100)
    kinds: list[str] | None = Field(default=None, description=_KINDS_HELP)
    rerank: bool = True
    include_deprecated: bool = False


class CandidatesRequest(BaseModel):
    description: str = Field(min_length=1, description="What you are looking for.")
    k: int = Field(default=8, ge=1, le=30)
    kinds: list[str] | None = Field(default=None, description=_KINDS_HELP)
    judge: bool = Field(
        default=True, description="Have the chat model judge each candidate."
    )
    include_unrelated: bool = False


class ContextRequest(BaseModel):
    question: str = Field(min_length=1)
    max_elements: int = Field(default=40, ge=1, le=200)
    hops: int = Field(default=1, ge=0, le=3)


_REASONER_HELP = "auto (HermiT if Java is present, else OWL RL), owlrl or hermit."


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    use_inferences: bool = Field(
        default=False, description="Query the reasoner's inferred graph."
    )
    reasoner: str = Field(default="auto", description=_REASONER_HELP)
    max_attempts: int = Field(default=3, ge=1, le=6)
    max_elements: int = Field(default=40, ge=5, le=200)


class SparqlRequest(BaseModel):
    query: str = Field(min_length=1)
    use_inferences: bool = Field(
        default=False, description="Query the reasoner's inferred graph."
    )
    reasoner: str = Field(default="auto", description=_REASONER_HELP)


class ReasonRequest(BaseModel):
    backend: str = Field(default="auto", description=_REASONER_HELP)


class PlacementRequest(BaseModel):
    name: str = Field(min_length=1, description="The new concept's name.")
    description: str = ""


class ChildrenRequest(BaseModel):
    iri: str
    limit: int = Field(default=5, ge=1, le=20)


class DefinitionsRequest(BaseModel):
    iris: list[str] | None = Field(
        default=None, description="Elements to define; empty = classes lacking one."
    )
    limit: int = Field(default=20, ge=1, le=50)


class IssuesRequest(BaseModel):
    duplicate_threshold: float = Field(default=0.92, ge=0.5, le=1.0)
    max_pairs: int = Field(default=50, ge=1, le=500)
    confirm_duplicates: bool = Field(
        default=False, description="Have the chat model review the duplicate pairs."
    )


class AdditionsRequest(BaseModel):
    turtle: str = Field(
        min_length=1,
        description="Triples to add, in Turtle. The ontology's prefixes are predeclared.",
    )


class AlignRequest(BaseModel):
    source_id: str
    target_id: str
    kinds: list[str] | None = Field(
        default=None, description=_KINDS_HELP + " Default: class."
    )
    source_iris: list[str] | None = Field(
        default=None, description="Align only these source elements."
    )
    k: int = Field(default=5, ge=1, le=20, description="Candidates per source element.")
    judge: bool = True
    max_sources: int = Field(default=100, ge=1, le=2000)
    offset: int = Field(default=0, ge=0)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RulesRequest(BaseModel):
    rules: list[str] = Field(min_length=1, max_length=30)


class ValidateRequest(BaseModel):
    data: str = Field(
        default="",
        description="RDF data to validate; empty = the ontology's own individuals.",
    )
    data_format: str = Field(default="", description="rdflib format; guessed if empty.")
    shapes: str = Field(default="", description="Extra SHACL shapes in Turtle.")
    use_derived: bool = Field(
        default=True,
        description="Also apply shapes derived from the ontology's axioms.",
    )
    explain: bool = Field(
        default=False, description="Summarise the results in plain language."
    )
