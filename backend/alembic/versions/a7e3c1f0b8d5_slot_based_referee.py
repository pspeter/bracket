"""slot-based referee (referee as a third match slot)

Revision ID: a7e3c1f0b8d5
Revises: f2a4c8e1b9d3
Create Date: 2026-06-17 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "a7e3c1f0b8d5"
down_revision: str | None = "f2a4c8e1b9d3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("referee_stage_item_input_id", sa.BigInteger(), nullable=True),
    )
    op.add_column("matches", sa.Column("referee_name", sa.String(), nullable=True))
    op.create_foreign_key(
        "matches_referee_stage_item_input_id_fkey",
        "matches",
        "stage_item_inputs",
        ["referee_stage_item_input_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Free-text referees → referee_name.
    op.execute(
        text(
            """
            UPDATE matches m
            SET referee_name = r.name
            FROM referees r
            WHERE m.referee_id = r.id AND r.name IS NOT NULL
            """
        )
    )

    # Team referees → the team's identity stage_item_input. Prefer the slot in a stage item at
    # the refereed match's level; otherwise any slot the team occupies. Teams with no input slot
    # keep no assignment (their referee_id is simply dropped below).
    op.execute(
        text(
            """
            UPDATE matches m
            SET referee_stage_item_input_id = (
                SELECT sii.id
                FROM referees r
                JOIN stage_item_inputs sii ON sii.team_id = r.team_id
                JOIN stage_items si ON si.id = sii.stage_item_id
                JOIN stages s ON s.id = si.stage_id
                JOIN rounds m_rd ON m_rd.id = m.round_id
                JOIN stage_items m_si ON m_si.id = m_rd.stage_item_id
                JOIN stages m_s ON m_s.id = m_si.stage_id
                WHERE r.id = m.referee_id
                ORDER BY (s.level_id IS NOT DISTINCT FROM m_s.level_id) DESC, sii.id
                LIMIT 1
            )
            WHERE m.referee_id IN (SELECT id FROM referees WHERE team_id IS NOT NULL)
            """
        )
    )

    op.drop_column("matches", "referee_id")
    op.drop_table("referees")

    op.create_check_constraint(
        "matches_at_most_one_referee",
        "matches",
        "referee_stage_item_input_id IS NULL OR referee_name IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint("matches_at_most_one_referee", "matches", type_="check")

    op.create_table(
        "referees",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "tournament_id", sa.BigInteger(), sa.ForeignKey("tournaments.id"), nullable=False
        ),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column(
            "created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(team_id IS NULL) != (name IS NULL)",
            name="referees_exactly_one_of_team_or_name",
        ),
    )
    op.create_index("ix_referees_id", "referees", ["id"])
    op.create_index("ix_referees_tournament_id", "referees", ["tournament_id"])
    op.create_index("ix_referees_team_id", "referees", ["team_id"])

    op.add_column("matches", sa.Column("referee_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "matches_referee_id_fkey",
        "matches",
        "referees",
        ["referee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("matches_referee_stage_item_input_id_fkey", "matches", type_="foreignkey")
    op.drop_column("matches", "referee_stage_item_input_id")
    op.drop_column("matches", "referee_name")
