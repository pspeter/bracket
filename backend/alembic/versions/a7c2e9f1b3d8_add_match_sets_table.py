"""Add match_sets table; derive match state from sets

Revision ID: a7c2e9f1b3d8
Revises: f3a1b2c9d4e5
Create Date: 2026-06-25 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "a7c2e9f1b3d8"
down_revision: str | None = "f3a1b2c9d4e5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Create the match_sets table
    op.create_table(
        "match_sets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "match_id",
            sa.BigInteger(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("stage_item_input1_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_item_input2_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "state",
            sa.Enum("NOT_STARTED", "IN_PROGRESS", "COMPLETED", name="match_set_state"),
            nullable=False,
            server_default="NOT_STARTED",
        ),
        sa.UniqueConstraint("match_id", "set_number"),
    )
    op.create_index(op.f("ix_match_sets_id"), "match_sets", ["id"], unique=False)

    # 2. Backfill one set per existing match copying its current score and state.
    op.execute(
        """
        INSERT INTO match_sets (
            match_id, set_number, stage_item_input1_score, stage_item_input2_score, state
        )
        SELECT
            id,
            1,
            stage_item_input1_score,
            stage_item_input2_score,
            state::text::match_set_state
        FROM matches
        """
    )

    # 3. Drop the flat score / state columns from matches (state is now derived).
    op.drop_index("ix_matches_state", table_name="matches")
    op.drop_column("matches", "stage_item_input1_score")
    op.drop_column("matches", "stage_item_input2_score")
    op.drop_column("matches", "state")
    op.execute("DROP TYPE IF EXISTS match_state")


def downgrade() -> None:
    op.execute(
        sa.text("CREATE TYPE match_state AS ENUM ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED')")
    )
    op.add_column(
        "matches",
        sa.Column("stage_item_input1_score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "matches",
        sa.Column("stage_item_input2_score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "matches",
        sa.Column(
            "state",
            sa.Enum("NOT_STARTED", "IN_PROGRESS", "COMPLETED", name="match_state"),
            nullable=False,
            server_default="NOT_STARTED",
        ),
    )

    # Restore flat columns from set_number = 1 where present.
    op.execute(
        """
        UPDATE matches m
        SET stage_item_input1_score = ms.stage_item_input1_score,
            stage_item_input2_score = ms.stage_item_input2_score,
            state = ms.state::text::match_state
        FROM match_sets ms
        WHERE ms.match_id = m.id AND ms.set_number = 1
        """
    )
    op.create_index("ix_matches_state", "matches", ["state"])
    op.drop_index(op.f("ix_match_sets_id"), table_name="match_sets")
    op.drop_table("match_sets")
    op.execute("DROP TYPE IF EXISTS match_set_state")
