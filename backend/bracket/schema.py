from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base  # type: ignore[attr-defined]
from sqlalchemy.sql.sqltypes import BigInteger, Boolean, DateTime, Enum, Float, Text

Base = declarative_base()
metadata = Base.metadata
DateTimeTZ = DateTime(timezone=True)

clubs = Table(
    "clubs",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True, autoincrement=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
)

tournaments = Table(
    "tournaments",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("start_time", DateTimeTZ, nullable=False),
    Column("club_id", BigInteger, ForeignKey("clubs.id"), index=True, nullable=False),
    Column("dashboard_public", Boolean, nullable=False),
    Column("logo_path", String, nullable=True),
    Column("dashboard_endpoint", String, nullable=True, index=True, unique=True),
    Column("players_can_be_in_multiple_teams", Boolean, nullable=False, server_default="f"),
    Column("auto_assign_courts", Boolean, nullable=False, server_default="f"),
    Column("duration_minutes", Integer, nullable=False, server_default="15"),
    Column("margin_minutes", Integer, nullable=False, server_default="5"),
    Column(
        "status",
        Enum(
            "OPEN",
            "ARCHIVED",
            name="tournament_status",
        ),
        nullable=False,
        server_default="OPEN",
        index=True,
    ),
    Column("signup_enabled", Boolean, nullable=False, server_default="false"),
    Column("signup_token", String, nullable=True),
    Column("max_team_size", Integer, nullable=False, server_default="4"),
    Column("signup_team_choice_enabled", Boolean, nullable=False, server_default="true"),
    Column("score_tracking_enabled", Boolean, nullable=False, server_default="false"),
    Column("score_tracking_token", String, nullable=True),
    Column("rules", Text, nullable=True),
    Column("referees_enabled", Boolean, nullable=False, server_default="false"),
)

levels = Table(
    "levels",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), nullable=False, index=True),
    Column("name", String, nullable=False),
    Column("position", Integer, nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
)

stages = Table(
    "stages",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), index=True, nullable=False),
    Column("level_id", BigInteger, ForeignKey("levels.id"), nullable=True),
)

stage_items = Table(
    "stage_items",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", Text, nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("stage_id", BigInteger, ForeignKey("stages.id"), index=True, nullable=False),
    Column("team_count", Integer, nullable=False),
    Column("ranking_id", BigInteger, ForeignKey("rankings.id"), nullable=False),
    Column(
        "type",
        Enum(
            "SINGLE_ELIMINATION",
            "SWISS",
            "ROUND_ROBIN",
            name="stage_type",
        ),
        nullable=False,
    ),
    Column("games_per_player", Integer, nullable=True),
)

stage_item_inputs = Table(
    "stage_item_inputs",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("slot", Integer, nullable=False),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), index=True, nullable=False),
    Column(
        "stage_item_id",
        BigInteger,
        ForeignKey("stage_items.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    ),
    Column("team_id", BigInteger, ForeignKey("teams.id"), nullable=True),
    Column("winner_from_stage_item_id", BigInteger, ForeignKey("stage_items.id"), nullable=True),
    Column("winner_position", Integer, nullable=True),
    Column("points", Float, nullable=False, server_default="0"),
    Column("wins", Integer, nullable=False, server_default="0"),
    Column("draws", Integer, nullable=False, server_default="0"),
    Column("losses", Integer, nullable=False, server_default="0"),
    Column("set_difference", Integer, nullable=False, server_default="0"),
    Column("point_difference", Integer, nullable=False, server_default="0"),
    UniqueConstraint("stage_item_id", "team_id"),
    UniqueConstraint("stage_item_id", "winner_from_stage_item_id", "winner_position"),
)

rounds = Table(
    "rounds",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", Text, nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("stage_item_id", BigInteger, ForeignKey("stage_items.id"), nullable=False),
    Column(
        "lifecycle_state",
        Enum("ACTIVE", "PLACEHOLDER", "RESOLVED", "LOCKED", name="round_lifecycle_state"),
        nullable=False,
        server_default="ACTIVE",
    ),
    Column("is_pinned", Boolean, nullable=True),
)


matches = Table(
    "matches",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("start_time", DateTimeTZ, nullable=True),
    Column("duration_minutes", Integer, nullable=True),
    Column("custom_duration_minutes", Integer, nullable=True),
    Column("round_id", BigInteger, ForeignKey("rounds.id"), nullable=False),
    Column("stage_item_input1_id", BigInteger, ForeignKey("stage_item_inputs.id"), nullable=True),
    Column("stage_item_input2_id", BigInteger, ForeignKey("stage_item_inputs.id"), nullable=True),
    Column(
        "stage_item_input1_winner_from_match_id",
        BigInteger,
        ForeignKey("matches.id"),
        nullable=True,
    ),
    Column(
        "stage_item_input2_winner_from_match_id",
        BigInteger,
        ForeignKey("matches.id"),
        nullable=True,
    ),
    Column("court_id", BigInteger, ForeignKey("courts.id"), nullable=True),
    # The referee is a third match slot: a reference to a stage_item_input that resolves to a
    # team via the same machinery as the two playing slots. ``referee_name`` is a parallel,
    # free-text external referee. At most one of the two is set.
    Column(
        "referee_stage_item_input_id",
        BigInteger,
        ForeignKey("stage_item_inputs.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("referee_name", String, nullable=True),
    Column("completed_at", DateTimeTZ, nullable=True),
    Column("input1_slot", Integer, nullable=True),
    Column("input2_slot", Integer, nullable=True),
    Column("referee_slot", Integer, nullable=True),
    CheckConstraint(
        "referee_stage_item_input_id IS NULL OR referee_name IS NULL",
        name="matches_at_most_one_referee",
    ),
)

match_sets = Table(
    "match_sets",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column(
        "match_id",
        BigInteger,
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("set_number", Integer, nullable=False),
    Column("stage_item_input1_score", Integer, nullable=False, server_default="0"),
    Column("stage_item_input2_score", Integer, nullable=False, server_default="0"),
    Column(
        "state",
        Enum(
            "NOT_STARTED",
            "IN_PROGRESS",
            "COMPLETED",
            name="match_set_state",
        ),
        nullable=False,
        server_default="NOT_STARTED",
    ),
    UniqueConstraint("match_id", "set_number"),
)

teams = Table(
    "teams",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), index=True, nullable=False),
    Column("active", Boolean, nullable=False, index=True, server_default="t"),
    Column("elo_score", Float, nullable=False, server_default="0"),
    Column("swiss_score", Float, nullable=False, server_default="0"),
    Column("wins", Integer, nullable=False, server_default="0"),
    Column("draws", Integer, nullable=False, server_default="0"),
    Column("losses", Integer, nullable=False, server_default="0"),
    Column("logo_path", String, nullable=True),
    Column("level_id", BigInteger, ForeignKey("levels.id"), nullable=True),
)

players = Table(
    "players",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), index=True, nullable=False),
    Column("elo_score", Float, nullable=False),
    Column("swiss_score", Float, nullable=False),
    Column("wins", Integer, nullable=False),
    Column("draws", Integer, nullable=False),
    Column("losses", Integer, nullable=False),
    Column("active", Boolean, nullable=False, index=True, server_default="t"),
    Column("level_id", BigInteger, ForeignKey("levels.id"), nullable=True),
)

users = Table(
    "users",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("email", String, nullable=False, index=True, unique=True),
    Column("name", String, nullable=False),
    Column("password_hash", String, nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column(
        "account_type",
        Enum(
            "REGULAR",
            "DEMO",
            name="account_type",
        ),
        nullable=False,
    ),
)

users_x_clubs = Table(
    "users_x_clubs",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("club_id", BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column(
        "relation",
        Enum(
            "OWNER",
            "COLLABORATOR",
            name="user_x_club_relation",
        ),
        nullable=False,
        default="OWNER",
    ),
)

players_x_teams = Table(
    "players_x_teams",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("player_id", BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("team_id", BigInteger, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
)

courts = Table(
    "courts",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", Text, nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), nullable=False, index=True),
)

rankings = Table(
    "rankings",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), nullable=False, index=True),
    Column("position", Integer, nullable=False),
    Column(
        "scoring_type",
        Enum("MATCH_POINTS", "SET_POINTS", "SET_POINTS_WITH_MATCH_BONUS", name="scoring_type"),
        nullable=False,
        server_default="MATCH_POINTS",
    ),
    Column("num_sets", Integer, nullable=False, server_default="1"),
    Column("max_points", Integer, nullable=False, server_default="21"),
    Column("last_set_max_points", Integer, nullable=True),
    Column("two_point_advantage", Boolean, nullable=False, server_default="true"),
    Column("level_id", BigInteger, ForeignKey("levels.id"), nullable=True),
    Column("side_switch_every_n_points", Integer, nullable=True),
)

ranking_match_points = Table(
    "ranking_match_points",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column(
        "ranking_id",
        BigInteger,
        ForeignKey("rankings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    Column("win_points", Numeric, nullable=False),
    Column("draw_points", Numeric, nullable=False),
    Column("loss_points", Numeric, nullable=False),
)

ranking_set_points = Table(
    "ranking_set_points",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column(
        "ranking_id",
        BigInteger,
        ForeignKey("rankings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
)

ranking_set_points_with_match_bonus = Table(
    "ranking_set_points_with_match_bonus",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column(
        "ranking_id",
        BigInteger,
        ForeignKey("rankings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    Column("match_bonus_points", Numeric, nullable=False, server_default="1.0"),
)
