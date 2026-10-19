# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OWL reasoning: consistency, unsatisfiable classes and inferred facts.

Two backends, chosen per run:

* **owlrl** -- the OWL 2 RL rules in pure Python (the ``owlrl`` package).
  Always available. Sound but incomplete for OWL DL: it derives subclass,
  type, domain/range, inverse, symmetric and transitive consequences and
  catches disjointness clashes, but cannot classify a class under a defined
  class it only satisfies (``FourSeasons`` under ``CheeseyPizza``).
* **hermit** -- the HermiT OWL DL reasoner via ``owlready2``. Complete
  classification and satisfiability, but needs Java on the PATH.

``auto`` picks HermiT when Java is present, else OWL RL.

The result keeps only *meaningful* inferences -- new named superclasses,
equivalences, individual types and property values -- with trivia (``owl:Thing``,
reflexive axioms, everything already implied by the asserted hierarchy)
dropped. Those triples plus the asserted graph make the *inferred graph*,
which SPARQL can query instead of the asserted one.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from auto_ontology.onto_query import config
from auto_ontology.onto_query.loader import is_reserved, new_graph
from auto_ontology.onto_query.model import ElementKind, Ontology

logger = logging.getLogger(__name__)

BACKENDS = ("auto", "owlrl", "hermit")
_ERR = URIRef("http://www.daml.org/2002/03/agents/agent-ont#error")
#: Inferences listed per category at most (the inferred graph keeps them all).
_LIST_LIMIT = 500

_hermit_lock = threading.Lock()


class ReasonerUnavailableError(RuntimeError):
    """The requested backend cannot run here; the message says why."""


class InconsistentOntologyError(RuntimeError):
    """Raised by callers that need a consistent ontology."""


def java_available() -> bool:
    return shutil.which("java") is not None


def hermit_available() -> bool:
    if not java_available():
        return False
    try:
        import owlready2  # noqa: F401
    except ImportError:
        return False
    return True


def availability() -> dict:
    return {
        "default": config.default_reasoner(),
        "backends": {
            "owlrl": {
                "available": True,
                "profile": "OWL 2 RL (rule-based, pure Python)",
            },
            "hermit": {
                "available": hermit_available(),
                "profile": "OWL 2 DL (HermiT, complete classification)",
                **(
                    {}
                    if hermit_available()
                    else {"reason": "Java was not found on the PATH."}
                ),
            },
        },
    }


def resolve_backend(backend: str) -> str:
    backend = (backend or "auto").lower()
    if backend not in BACKENDS:
        raise ValueError(
            f"Unknown reasoner {backend!r}; use one of {', '.join(BACKENDS)}."
        )
    if backend == "auto":
        backend = config.default_reasoner()
    if backend == "auto":
        return "hermit" if hermit_available() else "owlrl"
    if backend == "hermit" and not hermit_available():
        raise ReasonerUnavailableError(
            "HermiT needs Java on the PATH (in Docker: build with INSTALL_JAVA=true). "
            "Use the owlrl reasoner instead."
        )
    return backend


@dataclass
class ReasoningResult:
    backend: str
    consistent: bool
    seconds: float
    #: asserted + meaningful inferred triples; ``None`` when inconsistent.
    graph: Graph | None
    unsatisfiable: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    new_superclasses: list[tuple[str, str]] = field(default_factory=list)
    new_equivalences: list[tuple[str, str]] = field(default_factory=list)
    new_types: list[tuple[str, str]] = field(default_factory=list)
    new_property_values: list[tuple[str, str, str]] = field(default_factory=list)
    new_superproperties: list[tuple[str, str]] = field(default_factory=list)
    inferred_triples: int = 0

    def superclasses_of(self, iri: str) -> list[str]:
        return [sup for sub, sup in self.new_superclasses if sub == iri]

    def types_of(self, iri: str) -> list[str]:
        return [t for ind, t in self.new_types if ind == iri]

    def to_dict(self, ontology: Ontology) -> dict:
        def ref(iri: str) -> dict:
            return {"iri": iri, "name": ontology.name(iri)}

        return {
            "backend": self.backend,
            "consistent": self.consistent,
            "seconds": round(self.seconds, 3),
            "errors": self.errors,
            "unsatisfiable": [ref(i) for i in self.unsatisfiable],
            "inferred_triples": self.inferred_triples,
            "new_superclasses": [
                {"sub": ref(a), "sup": ref(b)}
                for a, b in self.new_superclasses[:_LIST_LIMIT]
            ],
            "new_equivalences": [
                {"a": ref(a), "b": ref(b)}
                for a, b in self.new_equivalences[:_LIST_LIMIT]
            ],
            "new_types": [
                {"individual": ref(a), "type": ref(b)}
                for a, b in self.new_types[:_LIST_LIMIT]
            ],
            "new_property_values": [
                {"subject": ref(s), "property": ref(p), "object": ref(o)}
                for s, p, o in self.new_property_values[:_LIST_LIMIT]
            ],
            "new_superproperties": [
                {"sub": ref(a), "sup": ref(b)}
                for a, b in self.new_superproperties[:_LIST_LIMIT]
            ],
            "counts": {
                "new_superclasses": len(self.new_superclasses),
                "new_equivalences": len(self.new_equivalences),
                "new_types": len(self.new_types),
                "new_property_values": len(self.new_property_values),
                "new_superproperties": len(self.new_superproperties),
            },
            "turtle": self.turtle(),
        }

    def turtle(self) -> str:
        """The listed inferences as Turtle, ready for the additions endpoint."""
        lines: list[str] = []
        for a, b in self.new_superclasses:
            lines.append(f"<{a}> <{RDFS.subClassOf}> <{b}> .")
        for a, b in self.new_equivalences:
            lines.append(f"<{a}> <{OWL.equivalentClass}> <{b}> .")
        for a, b in self.new_superproperties:
            lines.append(f"<{a}> <{RDFS.subPropertyOf}> <{b}> .")
        for a, b in self.new_types:
            lines.append(f"<{a}> <{RDF.type}> <{b}> .")
        for s, p, o in self.new_property_values:
            lines.append(f"<{s}> <{p}> <{o}> .")
        return "\n".join(lines) + ("\n" if lines else "")


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


def _copy(graph: Graph) -> Graph:
    out = new_graph()
    for prefix, ns in graph.namespaces():
        out.bind(prefix, ns, override=False)
    for triple in graph:
        out.add(triple)
    return out


def _run_owlrl(ontology: Ontology) -> tuple[Graph, list[str], list[str]]:
    """``(closure, errors, unsatisfiable)``."""
    import owlrl

    closure = _copy(ontology.graph)
    owlrl.DeductiveClosure(
        owlrl.OWLRL_Semantics,
        rdfs_closure=False,
        axiomatic_triples=False,
        datatype_axioms=False,
    ).expand(closure)
    errors = sorted({" ".join(str(o).split()) for o in closure.objects(None, _ERR)})
    unsat = sorted(
        str(c)
        for c in closure.subjects(RDFS.subClassOf, OWL.Nothing)
        if isinstance(c, URIRef) and c != OWL.Nothing
    )
    return closure, errors, unsat


def _run_hermit(ontology: Ontology) -> tuple[Graph | None, list[str], list[str]]:
    import owlready2
    from owlready2 import World, sync_reasoner

    with _hermit_lock, tempfile.TemporaryDirectory(prefix="onto-hermit-") as tmp:
        path = Path(tmp) / "ontology.nt"
        ontology.graph.serialize(path, format="nt", encoding="utf-8")
        world = World()
        try:
            onto = world.get_ontology(path.as_uri()).load()
            try:
                with onto:
                    sync_reasoner(world, infer_property_values=True, debug=0)
            except owlready2.OwlReadyInconsistentOntologyError:
                return None, ["HermiT found the ontology inconsistent."], []
            unsat = sorted(
                c.iri
                for c in world.inconsistent_classes()
                if getattr(c, "iri", "") and c.iri != str(OWL.Nothing)
            )
            closure = _copy(ontology.graph)
            for s, p, o in world.as_rdflib_graph():
                if isinstance(s, URIRef) and str(s).startswith("http://anonymous"):
                    continue
                closure.add((s, p, o))
            return closure, [], unsat
        finally:
            try:
                world.close()
            except Exception:  # noqa: BLE001 -- best effort
                pass


# ---------------------------------------------------------------------------
# Picking out what matters
# ---------------------------------------------------------------------------


def _named(term: object) -> bool:
    return isinstance(term, URIRef) and not is_reserved(str(term))


def _most_specific(
    pairs: dict[str, set[str]], ontology: Ontology, closure: Graph
) -> list[tuple[str, str]]:
    """Drop a new superclass already implied by another new or asserted one."""
    out: list[tuple[str, str]] = []
    for sub, sups in pairs.items():
        for sup in sorted(sups):
            redundant = any(
                other != sup
                and (URIRef(other), RDFS.subClassOf, URIRef(sup)) in closure
                and (URIRef(sup), RDFS.subClassOf, URIRef(other)) not in closure
                for other in sups
            )
            if not redundant:
                out.append((sub, sup))
    return out


def _extract(ontology: Ontology, closure: Graph, unsat: set[str]) -> dict:
    asserted = ontology.graph
    elements = ontology.elements

    sup_pairs: dict[str, set[str]] = {}
    equivalences: set[tuple[str, str]] = set()
    for s, o in closure.subject_objects(RDFS.subClassOf):
        if not (_named(s) and _named(o)) or s == o:
            continue
        sub, sup = str(s), str(o)
        if sub not in elements or sup not in elements or sub in unsat:
            continue
        if elements[sub].kind != ElementKind.CLASS:
            continue
        if sup in ontology.ancestors(sub):
            continue
        if (o, RDFS.subClassOf, s) in closure:
            a, b = sorted((sub, sup))
            if (URIRef(a), OWL.equivalentClass, URIRef(b)) not in asserted and (
                URIRef(b),
                OWL.equivalentClass,
                URIRef(a),
            ) not in asserted:
                equivalences.add((a, b))
            continue
        sup_pairs.setdefault(sub, set()).add(sup)
    for s, o in closure.subject_objects(OWL.equivalentClass):
        if (
            _named(s)
            and _named(o)
            and s != o
            and str(s) in elements
            and str(o) in elements
        ):
            a, b = sorted((str(s), str(o)))
            if (URIRef(a), OWL.equivalentClass, URIRef(b)) not in asserted and (
                URIRef(b),
                OWL.equivalentClass,
                URIRef(a),
            ) not in asserted:
                equivalences.add((a, b))

    superprops: list[tuple[str, str]] = []
    for s, o in closure.subject_objects(RDFS.subPropertyOf):
        if (
            _named(s)
            and _named(o)
            and s != o
            and str(s) in elements
            and str(o) in elements
        ):
            if str(o) not in ontology.ancestors(str(s)):
                superprops.append((str(s), str(o)))

    types: dict[str, set[str]] = {}
    for s, o in closure.subject_objects(RDF.type):
        if not (_named(s) and _named(o)):
            continue
        ind, cls = str(s), str(o)
        element = elements.get(ind)
        if (
            element is None
            or element.kind != ElementKind.INDIVIDUAL
            or cls not in elements
        ):
            continue
        if elements[cls].kind != ElementKind.CLASS:
            continue
        implied = set(element.types)
        for t in element.types:
            implied.update(ontology.ancestors(t))
        if cls not in implied:
            types.setdefault(ind, set()).add(cls)

    values: list[tuple[str, str, str]] = []
    for s, p, o in closure:
        if not (_named(s) and _named(p) and _named(o)):
            continue
        prop = elements.get(str(p))
        if prop is None or prop.kind != ElementKind.OBJECT_PROPERTY:
            continue
        if str(s) not in elements or elements[str(s)].kind != ElementKind.INDIVIDUAL:
            continue
        if (s, p, o) not in asserted:
            values.append((str(s), str(p), str(o)))

    return {
        "new_superclasses": _most_specific(sup_pairs, ontology, closure),
        "new_equivalences": sorted(equivalences),
        "new_superproperties": sorted(set(superprops)),
        "new_types": _most_specific(types, ontology, closure),
        "new_property_values": sorted(set(values)),
    }


def reason(ontology: Ontology, backend: str = "auto") -> ReasoningResult:
    """Run *backend* over *ontology* and keep what is worth showing."""
    chosen = resolve_backend(backend)
    started = time.perf_counter()
    if chosen == "hermit":
        closure, errors, unsat = _run_hermit(ontology)
    else:
        closure, errors, unsat = _run_owlrl(ontology)
    seconds = time.perf_counter() - started
    unsat = [u for u in unsat if u in ontology.elements]

    if closure is None or errors:
        return ReasoningResult(
            backend=chosen,
            consistent=False,
            seconds=seconds,
            graph=None,
            errors=errors,
            unsatisfiable=unsat,
        )
    found = _extract(ontology, closure, set(unsat))
    inferred = _copy(ontology.graph)
    for a, b in found["new_superclasses"]:
        inferred.add((URIRef(a), RDFS.subClassOf, URIRef(b)))
    for a, b in found["new_equivalences"]:
        inferred.add((URIRef(a), OWL.equivalentClass, URIRef(b)))
    for a, b in found["new_superproperties"]:
        inferred.add((URIRef(a), RDFS.subPropertyOf, URIRef(b)))
    for a, b in found["new_types"]:
        inferred.add((URIRef(a), RDF.type, URIRef(b)))
    for s, p, o in found["new_property_values"]:
        inferred.add((URIRef(s), URIRef(p), URIRef(o)))
    # Close the hierarchy and propagate types through it, so a query for
    # "every Tool" finds a Blade individual without property paths. HermiT
    # reports direct facts only; OWL RL's closure is already transitive.
    supers: dict[URIRef, set[URIRef]] = {}
    for s_, o in list(closure.subject_objects(RDFS.subClassOf)) + list(
        inferred.subject_objects(RDFS.subClassOf)
    ):
        if (
            _named(s_)
            and _named(o)
            and s_ != o
            and str(s_) in ontology.elements
            and str(o) in ontology.elements
            and str(s_) not in unsat
        ):
            supers.setdefault(s_, set()).add(o)
    closed: dict[URIRef, set[URIRef]] = {}

    def ancestors(cls: URIRef) -> set[URIRef]:
        if cls in closed:
            return closed[cls]
        closed[cls] = set()  # cycle guard
        out: set[URIRef] = set()
        for parent in supers.get(cls, ()):
            out.add(parent)
            out |= ancestors(parent)
        out.discard(cls)
        closed[cls] = out
        return out

    for cls in list(supers):
        for anc in ancestors(cls):
            inferred.add((cls, RDFS.subClassOf, anc))
    typed = [
        (s_, o)
        for s_, o in list(closure.subject_objects(RDF.type))
        + list(inferred.subject_objects(RDF.type))
        if _named(s_) and _named(o) and str(o) in ontology.elements
    ]
    for s_, o in typed:
        inferred.add((s_, RDF.type, o))
        for anc in ancestors(o):
            inferred.add((s_, RDF.type, anc))
    return ReasoningResult(
        backend=chosen,
        consistent=True,
        seconds=seconds,
        graph=inferred,
        unsatisfiable=unsat,
        inferred_triples=len(inferred) - len(ontology.graph),
        **found,
    )


__all__ = [
    "BACKENDS",
    "InconsistentOntologyError",
    "ReasonerUnavailableError",
    "ReasoningResult",
    "availability",
    "hermit_available",
    "reason",
    "resolve_backend",
]
