"""Match set progress pointer on matches

Revision ID: b4e8f2a1c9d7
Revises: 1f6b8c9d2e4a
Create Date: 2026-06-29 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "b4e8f2a1c9d7"
down_revision: str | None = "1f6b8c9d2e4a"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("completed_set_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "matches",
        sa.Column(
            "current_set_in_progress",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_check_constraint(
        "matches_completed_set_count_non_negative",
        "matches",
        "completed_set_count >= 0",
    )

    op.execute(
        """
        UPDATE matches m
        SET
            completed_set_count = stats.completed_count,
            current_set_in_progress = stats.in_progress
        FROM (
            SELECT
                ms.match_id,
                COALESCE(
                    MAX(ms.set_number) FILTER (WHERE ms.state = 'COMPLETED'),
                    0
                ) AS completed_count,
                EXISTS (
                    SELECT 1
                    FROM match_sets ms2
                    WHERE ms2.match_id = ms.match_id
                      AND ms2.state = 'IN_PROGRESS'
                      AND ms2.set_number > COALESCE(
                          MAX(ms.set_number) FILTER (WHERE ms.state = 'COMPLETED'),
                          0
                      )
                ) AS in_progress
            FROM match_sets ms
            GROUP BY ms.match_id
        ) stats
        WHERE m.id = stats.match_id
        """
    )

    op.drop_column("match_sets", "state")
    op.execute("DROP TYPE IF EXISTS match_set_state")


def downgrade() -> None:
    op.execute(
        sa.text(
            "CREATE TYPE match_set_state AS ENUM ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED')"
        )
    )
    op.add_column(
        "match_sets",
        sa.Column(
            "state",
            sa.Enum("NOT_STARTED", "IN_PROGRESS", "COMPLETED", name="match_set_state"),
            nullable=False,
            server_default="NOT_STARTED",
        ),
    )

    op.execute(
        """
        UPDATE match_sets ms
        SET state = CASE
            WHEN ms.set_number <= m.completed_set_count THEN 'COMPLETED'
            WHEN ms.set_number = m.completed_set_count + 1
                 AND m.current_set_in_progress THEN 'IN_PROGRESS'
            ELSE 'NOT_STARTED'
        END::match_set_state
        FROM matches m
        WHERE ms.match_id = m.id
        """
    )

    op.drop_constraint("matches_completed_set_count_non_negative", "matches", type_="check")
    op.drop_column("matches", "current_set_in_progress")
    op.drop_column("matches", "completed_set_count")
