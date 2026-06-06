"""add rules to tournaments

Revision ID: b2e4f8a1c3d5
Revises: a1b2c3d4e5f6
Create Date: 2026-06-07 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "b2e4f8a1c3d5"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("tournaments", sa.Column("rules", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tournaments", "rules")
