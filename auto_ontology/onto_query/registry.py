# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Loaded ontologies: kept on disk, parsed and indexed once per process.

Layout under :func:`~.config.data_dir`::

    <id>/manifest.json   id, title, original filename, timestamps
    <id>/original.<ext>  the file as uploaded, never changed
    <id>/current.ttl     the working copy, which additions are written to
    <id>/vectors.npy     cached embeddings (see :mod:`.index`)
    <id>/vectors.json

The working copy is what gets loaded, so additions survive a restart and the
upload can always be compared against.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePath

from auto_ontology.onto_query import config
from auto_ontology.onto_query.index import IndexStatus, OntologyIndex
from auto_ontology.onto_query.loader import (
    OntologyParseError,
    build_ontology,
    load_ontology,
    new_graph,
    parse_graph,
)
from auto_ontology.onto_query.model import Ontology

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
#: Route segments under /api/ontologies that an id must not shadow.
_RESERVED_IDS = frozenset({"upload", "align"})

EXPORT_FORMATS = {
    "turtle": ("text/turtle", "ttl"),
    "xml": ("application/rdf+xml", "owl"),
    "nt": ("application/n-triples", "nt"),
    "json-ld": ("application/ld+json", "jsonld"),
}


class OntologyNotFoundError(KeyError):
    """No ontology with that id has been loaded."""


@dataclass
class LoadedOntology:
    ontology: Ontology
    index: OntologyIndex
    manifest: dict

    @property
    def id(self) -> str:
        return self.ontology.id

    def summary(self) -> dict:
        return {
            **self.manifest,
            "ontology_iri": self.ontology.ontology_iri,
            "counts": self.ontology.stats(),
            "index": self.index.status.to_dict(),
        }


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]
    return slug or "ontology"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class OntologyRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root
        self._loaded: dict[str, LoadedOntology] = {}
        self._lock = threading.RLock()

    @property
    def root(self) -> Path:
        root = self._root or config.data_dir()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _dir(self, ontology_id: str) -> Path:
        if not _ID_RE.match(ontology_id):
            raise OntologyNotFoundError(ontology_id)
        return self.root / ontology_id

    # -- listing --------------------------------------------------------------

    def list(self) -> list[dict]:
        out: list[dict] = []
        for manifest_path in sorted(self.root.glob("*/manifest.json")):
            try:
                manifest = json.loads(manifest_path.read_text())
            except Exception:  # noqa: BLE001 -- skip a half-written directory
                continue
            loaded = self._loaded.get(manifest.get("id", ""))
            out.append(loaded.summary() if loaded else {**manifest, "loaded": False})
        return out

    def exists(self, ontology_id: str) -> bool:
        try:
            return (self._dir(ontology_id) / "manifest.json").exists()
        except OntologyNotFoundError:
            return False

    # -- create / load --------------------------------------------------------

    def _unique_id(self, wanted: str) -> str:
        base = _slug(wanted)
        candidate, n = base, 2
        while self.exists(candidate) or candidate in _RESERVED_IDS:
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def create(
        self,
        data: bytes,
        *,
        filename: str = "",
        title: str = "",
        ontology_id: str = "",
        rdf_format: str = "",
        embed: bool = True,
    ) -> LoadedOntology:
        """Parse, store and index a new ontology. Raises :class:`OntologyParseError`."""
        if len(data) > config.max_upload_bytes():
            raise OntologyParseError(
                f"The file is larger than {config.max_upload_bytes() // (1024 * 1024)} MB "
                "(ONTO_QUERY_MAX_UPLOAD_MB)."
            )
        with self._lock:
            if ontology_id:
                if not _ID_RE.match(ontology_id):
                    raise OntologyParseError(
                        "An id is lower-case letters, digits, '-' and '_' (max 63)."
                    )
                if ontology_id in _RESERVED_IDS:
                    raise OntologyParseError(
                        f"'{ontology_id}' is reserved; choose another id."
                    )
                if self.exists(ontology_id):
                    raise OntologyParseError(
                        f"An ontology '{ontology_id}' already exists."
                    )
                new_id = ontology_id
            else:
                new_id = self._unique_id(title or PurePath(filename).stem or "ontology")
            ontology = load_ontology(
                data,
                ontology_id=new_id,
                title=title,
                filename=filename,
                rdf_format=rdf_format,
            )
            directory = self.root / new_id
            directory.mkdir(parents=True)
            suffix = PurePath(filename).suffix.lower() or ".rdf"
            (directory / f"original{suffix}").write_bytes(data)
            ontology.graph.serialize(directory / "current.ttl", format="turtle")
            manifest = {
                "id": new_id,
                "title": ontology.title,
                "filename": filename,
                "created_at": _now(),
                "updated_at": _now(),
            }
            (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
            index = OntologyIndex(ontology, directory)
            index.build(embed=embed)
            loaded = LoadedOntology(ontology, index, manifest)
            self._loaded[new_id] = loaded
            return loaded

    def get(self, ontology_id: str) -> LoadedOntology:
        """The loaded ontology, reading it from disk on first use."""
        with self._lock:
            if ontology_id in self._loaded:
                return self._loaded[ontology_id]
            directory = self._dir(ontology_id)
            manifest_path = directory / "manifest.json"
            if not manifest_path.exists():
                raise OntologyNotFoundError(ontology_id)
            manifest = json.loads(manifest_path.read_text())
            graph = new_graph()
            graph.parse(directory / "current.ttl", format="turtle")
            ontology = build_ontology(
                graph, ontology_id=ontology_id, title=manifest.get("title", "")
            )
            index = OntologyIndex(ontology, directory)
            index.build()
            loaded = LoadedOntology(ontology, index, manifest)
            self._loaded[ontology_id] = loaded
            return loaded

    def delete(self, ontology_id: str) -> None:
        with self._lock:
            loaded = self._loaded.pop(ontology_id, None)
            directory = self._dir(ontology_id)
            if not directory.exists():
                raise OntologyNotFoundError(ontology_id)
            if loaded is not None:
                loaded.index.drop_pgvector()
            shutil.rmtree(directory)

    def reindex(self, ontology_id: str) -> IndexStatus:
        with self._lock:
            loaded = self.get(ontology_id)
            return loaded.index.build()

    # -- changes --------------------------------------------------------------

    def add_triples(self, ontology_id: str, turtle: str) -> tuple[LoadedOntology, int]:
        """Add the triples in *turtle* (the ontology's prefixes are predeclared).

        Returns the reloaded ontology and how many triples were new. The graph
        is rebuilt and re-indexed; only elements whose text changed are
        re-embedded.
        """
        with self._lock:
            loaded = self.get(ontology_id)
            ontology = loaded.ontology
            header = "".join(
                f"@prefix {p}: <{ns}> .\n" for p, ns in ontology.prefixes.items()
            )
            try:
                addition = parse_graph(header + turtle, rdf_format="turtle")
            except OntologyParseError as exc:
                raise OntologyParseError(
                    f"The additions are not valid Turtle: {exc}"
                ) from exc
            before = len(ontology.graph)
            for triple in addition:
                ontology.graph.add(triple)
            added = len(ontology.graph) - before
            directory = self._dir(ontology_id)
            ontology.graph.serialize(directory / "current.ttl", format="turtle")
            loaded.manifest["updated_at"] = _now()
            (directory / "manifest.json").write_text(
                json.dumps(loaded.manifest, indent=2)
            )
            rebuilt = build_ontology(
                ontology.graph, ontology_id=ontology_id, title=ontology.title
            )
            index = OntologyIndex(rebuilt, directory)
            index.build()
            fresh = LoadedOntology(rebuilt, index, loaded.manifest)
            self._loaded[ontology_id] = fresh
            return fresh, added

    def export(
        self, ontology_id: str, rdf_format: str = "turtle"
    ) -> tuple[bytes, str, str]:
        """``(content, media type, file extension)`` of the working copy."""
        if rdf_format not in EXPORT_FORMATS:
            raise ValueError(
                f"Unknown format {rdf_format!r}; use one of {list(EXPORT_FORMATS)}"
            )
        loaded = self.get(ontology_id)
        media_type, ext = EXPORT_FORMATS[rdf_format]
        content = loaded.ontology.graph.serialize(format=rdf_format)
        data = content.encode("utf-8") if isinstance(content, str) else content
        return data, media_type, ext


_registry: OntologyRegistry | None = None


def get_registry() -> OntologyRegistry:
    global _registry
    if _registry is None:
        _registry = OntologyRegistry()
    return _registry


def set_registry(registry: OntologyRegistry | None) -> None:
    """Swap the process-wide registry (tests)."""
    global _registry
    _registry = registry
