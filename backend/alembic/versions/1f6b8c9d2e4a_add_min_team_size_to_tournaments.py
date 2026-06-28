"""add min_team_size to tournaments

Revision ID: 1f6b8c9d2e4a
Revises: c5f8a1d2e4b7
Create Date: 2026-06-28 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "1f6b8c9d2e4a"
down_revision: str | None = "c5f8a1d2e4b7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("min_team_size", sa.Integer(), nullable=True, server_default="0"),
    )
    op.execute(text("UPDATE tournaments SET min_team_size=0 WHERE min_team_size IS NULL"))
    op.alter_column("tournaments", "min_team_size", nullable=False)


def downgrade() -> None:
    op.drop_column("tournaments", "min_team_size")
