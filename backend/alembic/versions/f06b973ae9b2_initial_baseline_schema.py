"""Initial baseline schema

Revision ID: f06b973ae9b2
Revises:
Create Date: 2023-04-15 00:00:00.000000

These tables predate this Alembic migration chain: they were originally created by
SQLAlchemy's ``metadata.create_all()`` before Alembic was introduced, and no later
migration ever creates them from scratch (they're only ever altered). Without this
migration, ``alembic upgrade head`` fails immediately on a genuinely empty database,
since the very first tracked migration (274385f2a757) assumes they already exist.

The shape below is the state each table must have been in immediately before
274385f2a757 ran, reconstructed from every later migration's add/drop/rename calls
against these tables (renamed/dropped columns are recreated here under their
original pre-rename names so later migrations can still operate on them).
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "f06b973ae9b2"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "clubs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clubs_id"), "clubs", ["id"], unique=False)
    op.create_index(op.f("ix_clubs_name"), "clubs", ["name"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "users_x_clubs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("club_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], name="users_x_clubs_club_id_fkey"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="users_x_clubs_user_id_fkey"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_x_clubs_id"), "users_x_clubs", ["id"], unique=False)

    op.create_table(
        "tournaments",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("club_id", sa.BigInteger(), nullable=False),
        sa.Column("dashboard_public", sa.Boolean(), nullable=False),
        sa.Column("logo_path", sa.String(), nullable=True),
        sa.Column(
            "players_can_be_in_multiple_teams",
            sa.Boolean(),
            server_default="f",
            nullable=False,
        ),
        sa.Column("duration_minutes", sa.Integer(), server_default="15", nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tournaments_id"), "tournaments", ["id"], unique=False)
    op.create_index(op.f("ix_tournaments_name"), "tournaments", ["name"], unique=False)
    op.create_index(op.f("ix_tournaments_club_id"), "tournaments", ["club_id"], unique=False)

    op.create_table(
        "teams",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="t", nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_teams_id"), "teams", ["id"], unique=False)
    op.create_index(op.f("ix_teams_name"), "teams", ["name"], unique=False)
    op.create_index(op.f("ix_teams_tournament_id"), "teams", ["tournament_id"], unique=False)
    op.create_index(op.f("ix_teams_active"), "teams", ["active"], unique=False)

    op.create_table(
        "players",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("elo_score", sa.Float(), nullable=False),
        sa.Column("swiss_score", sa.Float(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("draws", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="t", nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_players_id"), "players", ["id"], unique=False)
    op.create_index("ix_players_name", "players", ["name"], unique=True)
    op.create_index(op.f("ix_players_tournament_id"), "players", ["tournament_id"], unique=False)
    op.create_index(op.f("ix_players_active"), "players", ["active"], unique=False)

    op.create_table(
        "players_x_teams",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name="players_x_teams_player_id_fkey"
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="players_x_teams_team_id_fkey"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_players_x_teams_id"), "players_x_teams", ["id"], unique=False)

    # `stage_id` intentionally has no foreign key yet: the `stages` table it refers to
    # is only created later, by 6458e0bc3e9d, which also adds the FK constraint.
    op.create_table(
        "stage_items",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage_id", sa.BigInteger(), nullable=False),
        sa.Column("team_count", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "SINGLE_ELIMINATION",
                "SWISS",
                "ROUND_ROBIN",
                name="stage_type",
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stage_items_id"), "stage_items", ["id"], unique=False)
    op.create_index(op.f("ix_stage_items_stage_id"), "stage_items", ["stage_id"], unique=False)

    op.create_table(
        "stage_item_inputs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("stage_item_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("team_stage_item_id", sa.BigInteger(), nullable=False),
        sa.Column("team_position_in_group", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"]),
        sa.ForeignKeyConstraint(["stage_item_id"], ["stage_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["team_stage_item_id"], ["stage_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stage_item_inputs_id"), "stage_item_inputs", ["id"], unique=False)
    op.create_index(
        op.f("ix_stage_item_inputs_tournament_id"),
        "stage_item_inputs",
        ["tournament_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stage_item_inputs_stage_item_id"),
        "stage_item_inputs",
        ["stage_item_id"],
        unique=False,
    )

    op.create_table(
        "rounds",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("stage_item_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_draft", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["tournament_id"], ["tournaments.id"], name="rounds_tournament_id_fkey"
        ),
        sa.ForeignKeyConstraint(["stage_item_id"], ["stage_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rounds_id"), "rounds", ["id"], unique=False)

    op.create_table(
        "matches",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("round_id", sa.BigInteger(), nullable=False),
        sa.Column("team1_id", sa.BigInteger(), nullable=False),
        sa.Column("team2_id", sa.BigInteger(), nullable=False),
        sa.Column("team1_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("team2_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("team1_stage_item_id", sa.BigInteger(), nullable=False),
        sa.Column("team2_stage_item_id", sa.BigInteger(), nullable=False),
        sa.Column("team1_position_in_group", sa.Integer(), nullable=False),
        sa.Column("team2_position_in_group", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"]),
        sa.ForeignKeyConstraint(["team1_id"], ["teams.id"], name="matches_team1_id_fkey"),
        sa.ForeignKeyConstraint(["team2_id"], ["teams.id"], name="matches_team2_id_fkey"),
        sa.ForeignKeyConstraint(["team1_stage_item_id"], ["stage_items.id"]),
        sa.ForeignKeyConstraint(["team2_stage_item_id"], ["stage_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_matches_id"), "matches", ["id"], unique=False)


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_table("rounds")
    op.drop_table("stage_item_inputs")
    op.drop_table("stage_items")
    op.drop_table("players_x_teams")
    op.drop_table("players")
    op.drop_table("teams")
    op.drop_table("tournaments")
    op.drop_table("users_x_clubs")
    op.drop_table("users")
    op.drop_table("clubs")
