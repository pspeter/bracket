"""add planner advisory conflict flags

Revision ID: 7c1e9f0d2a4b
Revises: 0d4f19b8c6a2
Create Date: 2026-06-13 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "7c1e9f0d2a4b"
down_revision: str | None = "0d4f19b8c6a2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("precedence_conflict", sa.Boolean(), nullable=True, server_default="f"),
    )
    op.add_column(
        "matches",
        sa.Column("short_break_conflict", sa.Boolean(), nullable=True, server_default="f"),
    )
    op.execute(text("UPDATE matches SET precedence_conflict=false, short_break_conflict=false"))
    op.alter_column("matches", "precedence_conflict", nullable=False)
    op.alter_column("matches", "short_break_conflict", nullable=False)


def downgrade() -> None:
    op.drop_column("matches", "short_break_conflict")
    op.drop_column("matches", "precedence_conflict")
