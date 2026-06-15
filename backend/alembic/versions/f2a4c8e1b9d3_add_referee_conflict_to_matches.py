"""add referee_conflict to matches

Revision ID: f2a4c8e1b9d3
Revises: d3f1a2b9c4e7
Create Date: 2026-06-15 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "f2a4c8e1b9d3"
down_revision: str | None = "d3f1a2b9c4e7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("referee_conflict", sa.Boolean(), nullable=True, server_default="f"),
    )
    op.execute(text("UPDATE matches SET referee_conflict=false"))
    op.alter_column("matches", "referee_conflict", nullable=False)


def downgrade() -> None:
    op.drop_column("matches", "referee_conflict")
