"""add_levels_table_and_level_id_fks

Revision ID: 4e5516c97f50
Revises: a9f4c8d2b1e7
Create Date: 2026-05-31 01:37:38.957505

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = '4e5516c97f50'
down_revision: str | None = 'a9f4c8d2b1e7'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "levels",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_levels_id"), "levels", ["id"], unique=False)
    op.create_index(op.f("ix_levels_tournament_id"), "levels", ["tournament_id"], unique=False)

    op.add_column("stages", sa.Column("level_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("stages_level_id_fkey", "stages", "levels", ["level_id"], ["id"])

    op.add_column("teams", sa.Column("level_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("teams_level_id_fkey", "teams", "levels", ["level_id"], ["id"])

    op.add_column("rankings", sa.Column("level_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("rankings_level_id_fkey", "rankings", "levels", ["level_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("rankings_level_id_fkey", "rankings", type_="foreignkey")
    op.drop_column("rankings", "level_id")

    op.drop_constraint("teams_level_id_fkey", "teams", type_="foreignkey")
    op.drop_column("teams", "level_id")

    op.drop_constraint("stages_level_id_fkey", "stages", type_="foreignkey")
    op.drop_column("stages", "level_id")

    op.drop_index(op.f("ix_levels_tournament_id"), table_name="levels")
    op.drop_index(op.f("ix_levels_id"), table_name="levels")
    op.drop_table("levels")
