"""drop conflict columns from matches

Revision ID: d3b8f1c4e2a9
Revises: c2e4f9a1b7d3
Create Date: 2026-06-24 00:00:00.000000

Conflict detection now lives entirely client-side (see the client conflict engine), so
the persisted advisory flags are no longer read or written by the backend. Drop them.

"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str | None = "d3b8f1c4e2a9"
down_revision: str | None = "c2e4f9a1b7d3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_column("matches", "round_order_conflict")
    op.drop_column("matches", "referee_conflict")
    op.drop_column("matches", "short_break_conflict")
    op.drop_column("matches", "feeder_precedence_conflict")
    op.drop_column("matches", "precedence_conflict")
    op.drop_column("matches", "stage_item_input2_conflict")
    op.drop_column("matches", "stage_item_input1_conflict")


def downgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("stage_item_input1_conflict", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("stage_item_input2_conflict", sa.Boolean(), nullable=True),
    )
    op.execute(
        text(
            "UPDATE matches SET stage_item_input1_conflict=false, stage_item_input2_conflict=false"
        )
    )
    op.alter_column("matches", "stage_item_input1_conflict", nullable=False)
    op.alter_column("matches", "stage_item_input2_conflict", nullable=False)
    op.add_column(
        "matches",
        sa.Column(
            "precedence_conflict",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "feeder_precedence_conflict",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "short_break_conflict",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "referee_conflict",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "round_order_conflict",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
