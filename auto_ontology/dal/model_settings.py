# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read and write the per-role model settings.

Rows come back exactly as stored: ``api_key`` is the encrypted token. Decrypting
it is :mod:`auto_ontology.utils.model_config`'s job, and returning it to a
client is nobody's -- the API reports only whether one is stored.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from auto_ontology.dal import schema as s
from auto_ontology.dal.session import store


def list_model_settings() -> list[dict[str, Any]]:
    """Every stored role, one row each."""
    return [
        dict(row)
        for row in store().query_read(
            select(s.model_setting).order_by(s.model_setting.c.role)
        )
    ]


def get_model_setting(role: str) -> dict[str, Any] | None:
    """The stored row for *role*, or ``None`` when it has never been saved."""
    rows = store().query_read(
        select(s.model_setting).where(s.model_setting.c.role == role)
    )
    return dict(rows[0]) if rows else None


def upsert_model_setting(
    *,
    role: str,
    provider: str,
    model: str,
    base_url: str,
    api_key: str | None,
    dimensions: int | None,
    updated_by: str | None,
) -> dict[str, Any]:
    """Create or replace the row for *role*. *api_key* is already encrypted."""
    values = {
        "role": role,
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "dimensions": dimensions,
        "updated_by": updated_by,
    }
    statement = insert(s.model_setting).values(**values)
    rows = store().query_write(
        statement.on_conflict_do_update(
            index_elements=[s.model_setting.c.role],
            set_={
                **{k: statement.excluded[k] for k in values if k != "role"},
                "updated": func.now(),
            },
        ).returning(s.model_setting)
    )
    return dict(rows[0])


def delete_model_setting(role: str) -> bool:
    """Remove *role*'s row, so it falls back to the environment again."""
    rows = store().query_write(
        delete(s.model_setting)
        .where(s.model_setting.c.role == role)
        .returning(s.model_setting.c.role)
    )
    return bool(rows)
