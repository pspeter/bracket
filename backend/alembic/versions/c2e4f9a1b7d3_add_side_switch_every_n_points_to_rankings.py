"""add side_switch_every_n_points to rankings

Revision ID: c2e4f9a1b7d3
Revises: 0d4f19b8c6a2
Create Date: 2026-06-23 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "c2e4f9a1b7d3"
down_revision: str | None = "a2c4e6f8b1d3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "rankings",
        sa.Column("side_switch_every_n_points", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rankings", "side_switch_every_n_points")
