# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Background jobs run once at startup, then only when triggered."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from auto_ontology.ingestion_service import ingest, router
from auto_ontology.ingestion_service.scheduler import JobRunner


class _Counting(JobRunner):
    name = "counting"

    def __init__(self) -> None:
        super().__init__()
        self.passes = 0

    async def _run_once(self) -> None:
        self.passes += 1


def test_a_job_runs_once_at_start_and_then_only_on_trigger() -> None:
    async def scenario() -> list[int]:
        job = _Counting()
        job.start()
        await job.wait_first_pass()
        await asyncio.sleep(0.05)
        seen = [job.passes]
        job.trigger()
        for _ in range(100):
            if job.passes == 2:
                break
            await asyncio.sleep(0.01)
        seen.append(job.passes)
        await asyncio.sleep(0.05)
        seen.append(job.passes)
        await job.stop()
        return seen

    assert asyncio.run(scenario()) == [1, 2, 2]


def test_start_or_trigger_never_runs_twice() -> None:
    calls: list[str] = []

    class _Job:
        def __init__(self, started: bool) -> None:
            self._started = started

        def start(self) -> bool:
            calls.append("start")
            return not self._started

        def trigger(self) -> None:
            calls.append("trigger")

    router._start_or_trigger(_Job(started=False))
    assert calls == ["start"]
    calls.clear()
    router._start_or_trigger(_Job(started=True))
    assert calls == ["start", "trigger"]


def test_on_done_runs_after_a_successful_ingest(monkeypatch: Any) -> None:
    class _Connector:
        database_name = "pagila"

    done = threading.Event()
    monkeypatch.setattr(ingest, "invalidate_connectors_cache", lambda: None)
    monkeypatch.setattr(ingest, "get_connectors", lambda: [_Connector()])
    monkeypatch.setattr(ingest, "run_ingest", lambda connector: None)
    monkeypatch.setattr(ingest, "replay_rules", lambda label: None)

    ingest.trigger_ingest({"database": "pagila"}, on_done=done.set)
    assert done.wait(5)


def test_on_done_is_skipped_when_the_ingest_fails(monkeypatch: Any) -> None:
    class _Connector:
        database_name = "pagila"

    finished = threading.Event()
    called = threading.Event()

    def _fail(connector: Any) -> None:
        finished.set()
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest, "invalidate_connectors_cache", lambda: None)
    monkeypatch.setattr(ingest, "get_connectors", lambda: [_Connector()])
    monkeypatch.setattr(ingest, "run_ingest", _fail)

    ingest.trigger_ingest({"database": "pagila"}, on_done=called.set)
    assert finished.wait(5)
    assert not called.wait(0.2)
