"""add draws_allowed to rankings

Revision ID: b6e3f9a2c7d5
Revises: d9f3b1a7c5e2
Create Date: 2026-07-09 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "b6e3f9a2c7d5"
down_revision: str | None = "d9f3b1a7c5e2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "rankings",
        sa.Column(
            "draws_allowed",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("rankings", "draws_allowed")
