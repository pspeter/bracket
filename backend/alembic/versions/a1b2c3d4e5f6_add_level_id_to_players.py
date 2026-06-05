"""add level_id to players

Revision ID: a1b2c3d4e5f6
Revises: f4305c95da09
Create Date: 2026-06-05 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "a1b2c3d4e5f6"
down_revision: str | None = "b6d3a2c91f08"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("level_id", sa.BigInteger(), sa.ForeignKey("levels.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("players", "level_id")
