"""add match state and score tracking

Revision ID: a9f4c8d2b1e7
Revises: f4305c95da09
Create Date: 2026-04-19 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9f4c8d2b1e7"
down_revision: str | None = "f4305c95da09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


match_state = sa.Enum("NOT_STARTED", "IN_PROGRESS", "COMPLETED", name="match_state")


def upgrade() -> None:
    match_state.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "matches",
        sa.Column("state", match_state, nullable=False, server_default="NOT_STARTED"),
    )
    op.add_column("matches", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_matches_state"), "matches", ["state"], unique=False)

    op.add_column(
        "tournaments",
        sa.Column("score_tracking_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("tournaments", sa.Column("score_tracking_token", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("tournaments", "score_tracking_token")
    op.drop_column("tournaments", "score_tracking_enabled")

    op.drop_index(op.f("ix_matches_state"), table_name="matches")
    op.drop_column("matches", "completed_at")
    op.drop_column("matches", "state")
    match_state.drop(op.get_bind(), checkfirst=True)
