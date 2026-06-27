"""drop stages.is_active

Removes the stage activation feature: stages no longer have an "active" flag. Placeholder inputs
now auto-resolve as soon as their source stage item completes.

Revision ID: c5f8a1d2e4b7
Revises: b9d3e7f1a2c4
Create Date: 2026-06-26 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "c5f8a1d2e4b7"
down_revision: str | None = "b9d3e7f1a2c4"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_index("ix_stages_one_active_per_level", table_name="stages")
    op.drop_index("ix_stages_one_active_no_level", table_name="stages")
    op.drop_column("stages", "is_active")


def downgrade() -> None:
    op.add_column(
        "stages",
        sa.Column(
            "is_active",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.create_index(
        "ix_stages_one_active_per_level",
        "stages",
        ["tournament_id", "level_id"],
        unique=True,
        postgresql_where=text("is_active AND level_id IS NOT NULL"),
    )
    op.create_index(
        "ix_stages_one_active_no_level",
        "stages",
        ["tournament_id"],
        unique=True,
        postgresql_where=text("is_active AND level_id IS NULL"),
    )
