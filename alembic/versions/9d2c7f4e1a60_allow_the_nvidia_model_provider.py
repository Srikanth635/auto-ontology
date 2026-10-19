# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""allow the nvidia model provider

The provider check constraint was created with its values written out, so a new
``ModelProvider`` member is rejected by the database until the constraint is
recreated. Autogenerate does not compare check constraints, hence by hand.

Revision ID: 9d2c7f4e1a60
Revises: b473a6d702f7
Create Date: 2026-10-19 15:45:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9d2c7f4e1a60"
down_revision: Union[str, Sequence[str], None] = "b473a6d702f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAME = "ck_model_setting_provider_value"
_BEFORE = "'openai', 'anthropic', 'openai_compatible', 'rerank_api', 'none'"
_AFTER = "'openai', 'anthropic', 'openai_compatible', 'nvidia', 'rerank_api', 'none'"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f(_NAME), "model_setting", type_="check")
    op.create_check_constraint(op.f(_NAME), "model_setting", f"provider IN ({_AFTER})")


def downgrade() -> None:
    """Downgrade schema."""
    # A row saved with the nvidia provider would violate the old constraint, so
    # it goes back to "not configured" rather than blocking the downgrade.
    op.execute("DELETE FROM model_setting WHERE provider = 'nvidia'")
    op.drop_constraint(op.f(_NAME), "model_setting", type_="check")
    op.create_check_constraint(op.f(_NAME), "model_setting", f"provider IN ({_BEFORE})")
