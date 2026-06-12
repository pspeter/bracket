"""drop match schedule position and margin

Revision ID: 0d4f19b8c6a2
Revises: b2e4f8a1c3d5
Create Date: 2026-06-12 21:34:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "0d4f19b8c6a2"
down_revision: str | None = "b2e4f8a1c3d5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_column("matches", "position_in_schedule")
    op.drop_column("matches", "custom_margin_minutes")
    op.drop_column("matches", "margin_minutes")


def downgrade() -> None:
    op.add_column("matches", sa.Column("margin_minutes", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("custom_margin_minutes", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("position_in_schedule", sa.Integer(), nullable=True))
