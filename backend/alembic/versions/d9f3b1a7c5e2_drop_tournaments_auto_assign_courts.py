"""drop tournaments auto_assign_courts

Revision ID: d9f3b1a7c5e2
Revises: e2b7d1f4a9c6
Create Date: 2026-07-06 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "d9f3b1a7c5e2"
down_revision: str | None = "e2b7d1f4a9c6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_column("tournaments", "auto_assign_courts")


def downgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("auto_assign_courts", sa.Boolean(), server_default="f", nullable=False),
    )
