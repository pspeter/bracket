"""add play_all_sets to rankings

Revision ID: e4f7a2c9d1b3
Revises: b6e3f9a2c7d5
Create Date: 2026-07-09 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "e4f7a2c9d1b3"
down_revision: str | None = "b6e3f9a2c7d5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Behaviour-preserving: every existing ranking keeps playing out all sets.
    op.add_column(
        "rankings",
        sa.Column("play_all_sets", sa.Boolean(), server_default="true", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("rankings", "play_all_sets")
