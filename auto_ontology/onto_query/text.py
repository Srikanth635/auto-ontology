# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small text helpers: readable names from IRIs and keyword tokens."""

from __future__ import annotations

import re

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_TOKEN = re.compile(r"[a-z0-9]+")

#: Words too common in ontology text to help keyword ranking.
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the "
    "this to was which with".split()
)


def local_name(iri: str) -> str:
    """The part of *iri* after its last ``#``, ``/`` or ``:``."""
    for sep in ("#", "/", ":"):
        if sep in iri:
            tail = iri.rsplit(sep, 1)[1]
            if tail:
                return tail
    return iri


def humanize(name: str) -> str:
    """``MargheritaPizza`` / ``has_topping`` -> ``Margherita Pizza`` / ``has topping``."""
    spaced = _CAMEL.sub(" ", name.replace("_", " ").replace("-", " "))
    spaced = re.sub(r"\s+", " ", spaced).strip()
    if name[:1].islower():
        # lowerCamelCase is property style: "hasCapability" -> "has capability",
        # keeping acronyms ("hasURL" -> "has URL").
        spaced = " ".join(
            w if w.isupper() and len(w) > 1 else w.lower() for w in spaced.split()
        )
    return spaced


def tokens(text: str) -> list[str]:
    """Lower-cased keyword tokens of *text*, camelCase split, stopwords removed."""
    return [
        token
        for token in _TOKEN.findall(humanize(text).lower())
        if token not in _STOPWORDS
    ]


def normalize_label(label: str) -> str:
    """A comparison key: ``Margherita-Pizza`` and ``margherita pizza`` match.

    Stopwords are kept here, unlike in :func:`tokens`: ``hasCapability`` and
    ``Capability`` are different names.
    """
    return " ".join(_TOKEN.findall(humanize(label).lower()))
