"""add name to rankings

Revision ID: e8c1a4d7f3b2
Revises: b9d3e7f1a2c4
Create Date: 2026-06-26 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "e8c1a4d7f3b2"
down_revision: str | None = "b9d3e7f1a2c4"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "rankings",
        sa.Column("name", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("rankings", "name")
