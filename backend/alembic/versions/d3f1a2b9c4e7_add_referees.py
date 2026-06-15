"""add referees

Revision ID: d3f1a2b9c4e7
Revises: 7c1e9f0d2a4b
Create Date: 2026-06-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3f1a2b9c4e7"
down_revision: str | None = "7c1e9f0d2a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "referees",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column(
            "created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(team_id IS NULL) != (name IS NULL)",
            name="referees_exactly_one_of_team_or_name",
        ),
    )
    op.create_index(op.f("ix_referees_id"), "referees", ["id"], unique=False)
    op.create_index(op.f("ix_referees_tournament_id"), "referees", ["tournament_id"], unique=False)
    op.create_index(op.f("ix_referees_team_id"), "referees", ["team_id"], unique=False)

    op.add_column(
        "matches",
        sa.Column("referee_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "matches_referee_id_fkey",
        "matches",
        "referees",
        ["referee_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "tournaments",
        sa.Column("referees_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("tournaments", "referees_enabled")

    op.drop_constraint("matches_referee_id_fkey", "matches", type_="foreignkey")
    op.drop_column("matches", "referee_id")

    op.drop_index(op.f("ix_referees_team_id"), table_name="referees")
    op.drop_index(op.f("ix_referees_tournament_id"), table_name="referees")
    op.drop_index(op.f("ix_referees_id"), table_name="referees")
    op.drop_table("referees")
