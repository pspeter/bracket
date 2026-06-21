"""Swiss placeholder skeleton: games_per_player, round lifecycle state, match slot columns

Revision ID: c3d5a8f2e1b9
Revises: b8f2a1c4d6e7
Create Date: 2026-06-21 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "c3d5a8f2e1b9"
down_revision: str | None = "b8f2a1c4d6e7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("stage_items", sa.Column("games_per_player", sa.Integer(), nullable=True))

    op.execute("CREATE TYPE round_lifecycle_state AS ENUM ('PLACEHOLDER', 'RESOLVED', 'LOCKED')")
    op.add_column(
        "rounds",
        sa.Column(
            "lifecycle_state",
            sa.Enum("PLACEHOLDER", "RESOLVED", "LOCKED", name="round_lifecycle_state"),
            nullable=True,
        ),
    )
    op.add_column("rounds", sa.Column("is_pinned", sa.Boolean(), nullable=True))

    op.add_column("matches", sa.Column("input1_slot", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("input2_slot", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("referee_slot", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "referee_slot")
    op.drop_column("matches", "input2_slot")
    op.drop_column("matches", "input1_slot")

    op.drop_column("rounds", "is_pinned")
    op.drop_column("rounds", "lifecycle_state")
    op.execute("DROP TYPE round_lifecycle_state")

    op.drop_column("stage_items", "games_per_player")
