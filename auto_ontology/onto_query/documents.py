# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The text that represents one element, for embedding, keywords and prompts.

The parent path is the important part. A bare label such as "Container" says
little; "Container -> Physical Object -> Object" places it, which is what lets
an embedding tell a kitchen container from a software one.
"""

from __future__ import annotations

from auto_ontology.onto_query.model import Element, ElementKind, Ontology

#: How many items of a long list (children, restrictions...) a document shows.
_LIST_LIMIT = 12
#: Character cap on one document, so a heavily axiomatised class cannot
#: dominate an embedding request or a prompt.
_MAX_CHARS = 2000


def _names(ontology: Ontology, values: list[str], limit: int = _LIST_LIMIT) -> str:
    shown = [ontology.name(v) for v in values[:limit]]
    more = len(values) - limit
    return ", ".join(shown) + (f" (+{more} more)" if more > 0 else "")


def element_document(ontology: Ontology, element: Element) -> str:
    """A readable, embeddable description of *element*."""
    lines = [f"{element.kind.title}: {element.name}"]
    others = [label for label in element.all_labels[1:]]
    if others:
        lines.append("Also called: " + ", ".join(others[:_LIST_LIMIT]))
    if element.description:
        lines.append("Definition: " + element.description)
    if element.kind == ElementKind.CLASS:
        path = ontology.parent_path(element.iri)
        if len(path) > 1:
            lines.append("Is a: " + " -> ".join(path))
        if len(element.parents) > 1:
            lines.append("Parents: " + _names(ontology, element.parents))
        if element.equivalents:
            lines.append("Equivalent to: " + _names(ontology, element.equivalents))
        if element.restrictions:
            lines.append(
                "Restrictions: " + "; ".join(element.restrictions[:_LIST_LIMIT])
            )
        if element.disjoint_with:
            lines.append("Disjoint with: " + _names(ontology, element.disjoint_with))
        if element.children:
            lines.append("Subclasses: " + _names(ontology, element.children))
    elif element.kind.is_property:
        if element.parents:
            lines.append("Subproperty of: " + _names(ontology, element.parents))
        if element.domain:
            lines.append("Domain: " + _names(ontology, element.domain))
        if element.range:
            lines.append("Range: " + _names(ontology, element.range))
        if element.inverse_of:
            lines.append("Inverse of: " + _names(ontology, element.inverse_of))
        if element.characteristics:
            lines.append("Characteristics: " + ", ".join(element.characteristics))
    else:
        if element.types:
            lines.append("Instance of: " + _names(ontology, element.types))
        for prop, value in element.assertions[:_LIST_LIMIT]:
            lines.append(f"{ontology.name(prop)}: {ontology.name(value)}")
    if element.deprecated:
        lines.append("Deprecated.")
    text = "\n".join(lines)
    return text if len(text) <= _MAX_CHARS else text[: _MAX_CHARS - 3] + "..."


def keyword_text(ontology: Ontology, element: Element) -> str:
    """What the keyword index matches: names and definition, parents lightly.

    Children and restrictions are left out: a query for "cheese" should rank
    the class Cheese above every pizza that has a cheese topping.
    """
    parts = [*element.all_labels, element.all_labels[0], element.description]
    parts.extend(ontology.name(p) for p in element.parents)
    return " ".join(p for p in parts if p)
