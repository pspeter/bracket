"""add_partial_unique_indexes_for_active_stages

Revision ID: b6d3a2c91f08
Revises: 4e5516c97f50
Create Date: 2026-05-31 14:30:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "b6d3a2c91f08"
down_revision: str | None = "4e5516c97f50"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_index(
        "ix_stages_one_active_per_level",
        "stages",
        ["tournament_id", "level_id"],
        unique=True,
        postgresql_where="is_active AND level_id IS NOT NULL",
    )
    op.create_index(
        "ix_stages_one_active_no_level",
        "stages",
        ["tournament_id"],
        unique=True,
        postgresql_where="is_active AND level_id IS NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_stages_one_active_no_level", table_name="stages")
    op.drop_index("ix_stages_one_active_per_level", table_name="stages")
