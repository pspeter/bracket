"""add round_order_conflict flag to matches

Revision ID: a2c4e6f8b1d3
Revises: e1f4a9c7b2d3
Create Date: 2026-06-23 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "a2c4e6f8b1d3"
down_revision: str | None = "e1f4a9c7b2d3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("round_order_conflict", sa.Boolean(), nullable=True, server_default="f"),
    )
    op.execute(text("UPDATE matches SET round_order_conflict=false"))
    op.alter_column("matches", "round_order_conflict", nullable=False)


def downgrade() -> None:
    op.drop_column("matches", "round_order_conflict")
