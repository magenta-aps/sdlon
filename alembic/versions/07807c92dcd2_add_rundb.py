# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0

"""Add RunDB

Revision ID: 07807c92dcd2
Revises: 26d00ae9c67f
Create Date: 2024-01-05 15:37:31.521493

"""
from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "07807c92dcd2"
down_revision: Union[str, None] = "26d00ae9c67f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("from_date", sa.DateTime(timezone=True)),
        sa.Column("to_date", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(60)),
    )


def downgrade() -> None:
    op.drop_table("runs")
