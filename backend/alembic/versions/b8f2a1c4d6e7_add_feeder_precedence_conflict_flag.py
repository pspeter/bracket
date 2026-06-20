"""add feeder precedence conflict flag

Revision ID: b8f2a1c4d6e7
Revises: a7e3c1f0b8d5
Create Date: 2026-06-20 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "b8f2a1c4d6e7"
down_revision: str | None = "a7e3c1f0b8d5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("feeder_precedence_conflict", sa.Boolean(), nullable=True, server_default="f"),
    )
    op.execute(text("UPDATE matches SET feeder_precedence_conflict=false"))
    op.alter_column("matches", "feeder_precedence_conflict", nullable=False)


def downgrade() -> None:
    op.drop_column("matches", "feeder_precedence_conflict")
