"""Add set_difference and point_difference to stage_item_inputs

Revision ID: b9d3e7f1a2c4
Revises: a7c2e9f1b3d8
Create Date: 2026-06-26 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "b9d3e7f1a2c4"
down_revision: str | None = "a7c2e9f1b3d8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "stage_item_inputs",
        sa.Column("set_difference", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "stage_item_inputs",
        sa.Column("point_difference", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("stage_item_inputs", "point_difference")
    op.drop_column("stage_item_inputs", "set_difference")
