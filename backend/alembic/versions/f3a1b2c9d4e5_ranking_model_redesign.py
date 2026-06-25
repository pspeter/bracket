"""Ranking model redesign: scoring_type, set config, subtype tables

Revision ID: f3a1b2c9d4e5
Revises: e1f4a9c7b2d3
Create Date: 2026-06-25 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "f3a1b2c9d4e5"
down_revision: str | None = "d3b8f1c4e2a9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Add new base columns to rankings (nullable first for data migration)
    op.add_column("rankings", sa.Column("scoring_type", sa.String(), nullable=True))
    op.add_column(
        "rankings", sa.Column("num_sets", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "rankings", sa.Column("max_points", sa.Integer(), nullable=False, server_default="21")
    )
    op.add_column("rankings", sa.Column("last_set_max_points", sa.Integer(), nullable=True))
    op.add_column(
        "rankings",
        sa.Column("two_point_advantage", sa.Boolean(), nullable=False, server_default="true"),
    )

    # 2. Create subtype tables
    op.create_table(
        "ranking_match_points",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "ranking_id",
            sa.BigInteger(),
            sa.ForeignKey("rankings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("win_points", sa.Numeric(), nullable=False),
        sa.Column("draw_points", sa.Numeric(), nullable=False),
        sa.Column("loss_points", sa.Numeric(), nullable=False),
    )
    op.create_table(
        "ranking_set_points",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "ranking_id",
            sa.BigInteger(),
            sa.ForeignKey("rankings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
    )
    op.create_table(
        "ranking_set_points_with_match_bonus",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "ranking_id",
            sa.BigInteger(),
            sa.ForeignKey("rankings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "match_bonus_points",
            sa.Numeric(),
            nullable=False,
            server_default="1.0",
        ),
    )

    # 3. Migrate existing rankings to MATCH_POINTS subtype
    op.execute(
        "INSERT INTO ranking_match_points (ranking_id, win_points, draw_points, loss_points) "
        "SELECT id, win_points, draw_points, loss_points FROM rankings"
    )

    # 4. Set scoring_type for all existing rows
    op.execute("UPDATE rankings SET scoring_type = 'MATCH_POINTS'")

    # 5. Make scoring_type NOT NULL now that all rows have a value
    op.alter_column("rankings", "scoring_type", nullable=False)

    # 6. Create the enum type and cast
    op.execute(
        "CREATE TYPE scoring_type AS ENUM "
        "('MATCH_POINTS', 'SET_POINTS', 'SET_POINTS_WITH_MATCH_BONUS')"
    )
    op.execute("ALTER TABLE rankings ALTER COLUMN scoring_type DROP DEFAULT")
    op.execute(
        "ALTER TABLE rankings ALTER COLUMN scoring_type "
        "TYPE scoring_type USING scoring_type::text::scoring_type"
    )
    op.execute("ALTER TABLE rankings ALTER COLUMN scoring_type SET DEFAULT 'MATCH_POINTS'")

    # 7. Drop the old columns
    op.drop_column("rankings", "win_points")
    op.drop_column("rankings", "draw_points")
    op.drop_column("rankings", "loss_points")
    op.drop_column("rankings", "add_score_points")


def downgrade() -> None:
    # Re-add old columns
    op.add_column("rankings", sa.Column("win_points", sa.Float(), nullable=True))
    op.add_column("rankings", sa.Column("draw_points", sa.Float(), nullable=True))
    op.add_column("rankings", sa.Column("loss_points", sa.Float(), nullable=True))
    op.add_column("rankings", sa.Column("add_score_points", sa.Boolean(), nullable=True))

    # Restore values from subtype table for MATCH_POINTS rankings
    op.execute(
        "UPDATE rankings SET win_points = rmp.win_points, draw_points = rmp.draw_points, "
        "loss_points = rmp.loss_points, add_score_points = false "
        "FROM ranking_match_points rmp WHERE rmp.ranking_id = rankings.id"
    )

    # Set defaults for any that didn't match
    op.execute(
        "UPDATE rankings SET win_points = 1, draw_points = 0.5, loss_points = 0, "
        "add_score_points = false WHERE win_points IS NULL"
    )

    op.alter_column("rankings", "win_points", nullable=False)
    op.alter_column("rankings", "draw_points", nullable=False)
    op.alter_column("rankings", "loss_points", nullable=False)
    op.alter_column("rankings", "add_score_points", nullable=False)

    # Drop new columns and tables
    op.drop_column("rankings", "two_point_advantage")
    op.drop_column("rankings", "last_set_max_points")
    op.drop_column("rankings", "max_points")
    op.drop_column("rankings", "num_sets")
    op.drop_column("rankings", "scoring_type")

    op.drop_table("ranking_set_points_with_match_bonus")
    op.drop_table("ranking_set_points")
    op.drop_table("ranking_match_points")

    op.execute("DROP TYPE scoring_type")
