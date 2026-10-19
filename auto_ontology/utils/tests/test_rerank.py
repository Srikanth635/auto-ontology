# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`auto_ontology.utils.rerank.rerank_hits`.

The two built-in endpoints speak different ranking schemas -- inference-api's
``/rerank`` and NIM's ``/reranking`` -- so both are pinned here: a request in
the wrong shape is rejected by the server and every bridge-table owner falls
back to the first Term without anyone noticing.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from auto_ontology.utils import rerank
from auto_ontology.utils.rerank import rerank_hits

Server = Callable[..., list[httpx.Request]]

_HITS = [
    {"id": "a", "text": "apples"},
    {"id": "b", "text": "bananas"},
    {"id": "c", "text": "cherries"},
]


@pytest.fixture
def server(
    monkeypatch: pytest.MonkeyPatch,
) -> Server:
    """Answer the next POST with *body*; returns the requests seen."""

    def _install(body: dict[str, Any], status: int = 200) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def _post(url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request(
                "POST", url, json=kwargs["json"], headers=kwargs["headers"]
            )
            seen.append(request)
            assert kwargs["timeout"] == rerank._TIMEOUT_S
            return httpx.Response(status, json=body, request=request)

        monkeypatch.setattr(rerank.httpx, "post", _post)
        return seen

    return _install


def test_the_rerank_api_schema(server: Server) -> None:
    seen = server(
        {
            "results": [
                {"index": 2, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.1},
            ]
        }
    )

    ranked = rerank_hits(
        "fruit",
        _HITS,
        rerank_invoke_url="https://inference.example/v1/rerank",
        model_name="m",
        api_key="sk-x",
    )

    [request] = seen
    assert str(request.url) == "https://inference.example/v1/rerank"
    assert request.headers["authorization"] == "Bearer sk-x"
    assert json.loads(request.content) == {
        "model": "m",
        "query": "fruit",
        "documents": ["apples", "bananas", "cherries"],
        "top_n": 3,
    }
    # b was not returned, so it ranks last rather than disappearing.
    assert [(h["id"], h["_rerank_score"]) for h in ranked] == [
        ("c", 0.9),
        ("a", 0.1),
        ("b", float("-inf")),
    ]


def test_a_base_url_gets_the_rerank_path(server: Server) -> None:
    seen = server({"results": []})
    rerank_hits(
        "q", _HITS, rerank_invoke_url="http://localhost:8015/v1/", model_name="m"
    )
    assert str(seen[0].url) == "http://localhost:8015/v1/rerank"


def test_reranking_is_off_until_configured(monkeypatch) -> None:
    from auto_ontology.dal.schema import ModelProvider, ModelRole
    from auto_ontology.utils import rerank
    from auto_ontology.utils.model_config import ResolvedModel

    monkeypatch.setattr(
        rerank,
        "get_model",
        lambda role: ResolvedModel(ModelRole.RERANK, ModelProvider.NONE, ""),
    )
    assert rerank.get_rerank_kwargs() is None


def test_an_endpoint_error_reaches_the_caller(server: Server) -> None:
    server({"error": "nope"}, status=500)
    with pytest.raises(httpx.HTTPStatusError):
        rerank_hits("q", _HITS, rerank_invoke_url="http://x/rerank", model_name="m")


def test_no_hits_makes_no_request(server: Server) -> None:
    seen = server({})
    assert (
        rerank_hits("q", [], rerank_invoke_url="http://x/rerank", model_name="m") == []
    )
    assert seen == []


def test_the_nim_schema(server: Server) -> None:
    seen = server(
        {"rankings": [{"index": 1, "logit": 4.5}, {"index": 0, "logit": -1.0}]}
    )

    ranked = rerank_hits(
        "fruit",
        _HITS[:2],
        rerank_invoke_url=(
            "https://ai.api.nvidia.com/v1/retrieval/nvidia/m-rerank/reranking"
        ),
        model_name="nvidia/m-rerank",
        api_key="nvapi-x",
    )

    [request] = seen
    assert str(request.url).endswith("/nvidia/m-rerank/reranking")
    assert request.headers["authorization"] == "Bearer nvapi-x"
    assert json.loads(request.content) == {
        "model": "nvidia/m-rerank",
        "query": {"text": "fruit"},
        "passages": [{"text": "apples"}, {"text": "bananas"}],
        "truncate": "END",
    }
    assert [h["id"] for h in ranked] == ["b", "a"]
