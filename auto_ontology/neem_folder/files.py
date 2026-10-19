# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Which files in the NEEM folder count, shared by the watcher and the upload API.

Two kinds are accepted: SQLite databases (``.sqlite``, ``.sqlite3``, ``.db``)
and SQLite ``.sql`` dumps (``sqlite3 x.sqlite .dump``). A dump whose stem also
has a database beside it is skipped -- the two are the same NEEM, and loading
both would put every row in twice.

Names starting with a dot are ignored, which is what keeps an upload in
progress (written as ``.<name>.part`` and renamed when complete) out of view.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

DATABASE_SUFFIXES = (".sqlite", ".sqlite3", ".db")
DUMP_SUFFIXES = (".sql",)
ACCEPTED_SUFFIXES = DATABASE_SUFFIXES + DUMP_SUFFIXES

#: The first 16 bytes of every SQLite 3 database file.
SQLITE_MAGIC = b"SQLite format 3\x00"

# Letters, digits, dot, dash, underscore and space; no path separators and no
# leading dot. Anything else is refused rather than rewritten, so the name a
# user sees in the folder is the name they uploaded.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,199}$")


@dataclass(frozen=True)
class NeemFile:
    """One file in the folder, with the fingerprint the watcher compares."""

    name: str
    path: Path
    size: int
    mtime_ns: int

    @property
    def is_dump(self) -> bool:
        """Whether this is a ``.sql`` dump that has to be converted first."""
        return self.path.suffix.lower() in DUMP_SUFFIXES

    @property
    def fingerprint(self) -> tuple[int, int]:
        """Cheap change detection: size and modification time."""
        return (self.size, self.mtime_ns)


def is_valid_name(name: str) -> bool:
    """Whether *name* is acceptable as a NEEM file name in the folder."""
    return bool(_NAME_RE.match(name)) and name.lower().endswith(ACCEPTED_SUFFIXES)


def scan(directory: Path) -> list[NeemFile]:
    """The NEEM files in *directory*, sorted by name."""
    if not directory.is_dir():
        return []
    found: list[NeemFile] = []
    for path in directory.iterdir():
        if not path.is_file() or not is_valid_name(path.name):
            continue
        try:
            stat = path.stat()
        except OSError:
            # Removed between the listing and the stat.
            continue
        found.append(NeemFile(path.name, path, stat.st_size, stat.st_mtime_ns))

    database_stems = {f.path.stem.lower() for f in found if not f.is_dump}
    kept = [
        f for f in found if not (f.is_dump and f.path.stem.lower() in database_stems)
    ]
    return sorted(kept, key=lambda f: f.name)


def sha256(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def looks_like_sqlite(head: bytes) -> bool:
    """Whether *head* (the first bytes of a file) is a SQLite database header."""
    return head.startswith(SQLITE_MAGIC)


def looks_like_sql_dump(head: bytes) -> bool:
    """Whether *head* is plausibly a text SQL dump: UTF-8 and no NUL bytes."""
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A multi-byte character cut off at the end of the sample is fine.
        return exc.start >= len(head) - 3
    return True
