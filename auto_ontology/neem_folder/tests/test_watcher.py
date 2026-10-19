# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The NEEM folder watcher, one poll at a time."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from auto_ontology.neem_folder import merge
from auto_ontology.neem_folder.tests.neem_fixtures import (
    make_neem,
    neem_db,  # noqa: F401 -- fixture
)
from auto_ontology.neem_folder.watcher import NeemFolderWatcher

pytestmark = pytest.mark.usefixtures("neem_db")


class _Recorder:
    def __init__(self) -> None:
        self.ingests = 0
        self.changes = 0

    def ingest(self) -> None:
        self.ingests += 1

    def changed(self) -> None:
        self.changes += 1


def _watcher(directory: Path, recorder: _Recorder) -> NeemFolderWatcher:
    return NeemFolderWatcher(
        directory, ingest=recorder.ingest, on_changed=recorder.changed, poll_seconds=1
    )


def _states(watcher: NeemFolderWatcher) -> dict[str, str]:
    return {f["name"]: f["state"] for f in watcher.status()["files"]}


def test_a_new_file_is_loaded_once_it_has_stopped_changing(tmp_path: Path) -> None:
    recorder = _Recorder()
    watcher = _watcher(tmp_path, recorder)
    make_neem(tmp_path / "a.sqlite")

    assert watcher.poll_once() is False  # first sighting: not yet stable
    assert _states(watcher) == {"a.sqlite": "waiting"}
    assert watcher.poll_once() is True
    assert _states(watcher) == {"a.sqlite": "loaded"}
    assert (recorder.ingests, recorder.changes) == (1, 1)
    assert watcher.poll_once() is False  # nothing new: no second ingest
    assert recorder.ingests == 1


def test_a_deleted_file_is_removed_from_the_database(tmp_path: Path) -> None:
    recorder = _Recorder()
    watcher = _watcher(tmp_path, recorder)
    make_neem(tmp_path / "a.sqlite")
    make_neem(tmp_path / "b.sqlite")
    watcher.poll_once()
    watcher.poll_once()

    (tmp_path / "b.sqlite").unlink()
    assert watcher.poll_once() is True
    assert set(merge.loaded_sources()) == {"a.sqlite"}
    assert _states(watcher) == {"a.sqlite": "loaded"}


def test_a_touched_file_with_the_same_content_is_not_reloaded(tmp_path: Path) -> None:
    recorder = _Recorder()
    watcher = _watcher(tmp_path, recorder)
    path = tmp_path / "a.sqlite"
    make_neem(path)
    watcher.poll_once()
    watcher.poll_once()
    loaded_at = merge.loaded_sources()["a.sqlite"].loaded_at

    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    watcher.poll_once()
    assert watcher.poll_once() is False
    assert merge.loaded_sources()["a.sqlite"].loaded_at == loaded_at
    assert recorder.ingests == 1


def test_a_failed_file_is_reported_and_not_retried_until_it_changes(
    tmp_path: Path,
) -> None:
    recorder = _Recorder()
    watcher = _watcher(tmp_path, recorder)
    path = tmp_path / "junk.sqlite"
    path.write_bytes(b"not sqlite" * 50)
    watcher.poll_once()
    watcher.poll_once()

    status = {f["name"]: f for f in watcher.status()["files"]}
    assert status["junk.sqlite"]["state"] == "failed"
    assert "SQLite" in status["junk.sqlite"]["error"]
    assert recorder.ingests == 0

    path.unlink()
    make_neem(path)
    watcher.poll_once()
    assert watcher.poll_once() is True
    assert _states(watcher) == {"junk.sqlite": "loaded"}
