"""Add set_difference and point_difference to stage_item_inputs

Revision ID: a1b2c3d4e5f6
Revises: f3a1b2c9d4e5
Create Date: 2026-06-26 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "a1b2c3d4e5f6"
down_revision: str | None = "f3a1b2c9d4e5"
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
