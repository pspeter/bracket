from decimal import Decimal
from enum import auto
from typing import Annotated, Literal

from heliclockter import datetime_utc
from pydantic import BaseModel, Field

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import LevelId, RankingId, TournamentId
from bracket.utils.types import EnumAutoStr


class ScoringType(EnumAutoStr):
    MATCH_POINTS = auto()
    SET_POINTS = auto()
    SET_POINTS_WITH_MATCH_BONUS = auto()


class RankingMatchPointsData(BaseModel):
    win_points: Decimal
    draw_points: Decimal
    loss_points: Decimal


class RankingSetPointsWithMatchBonusData(BaseModel):
    match_bonus_points: Decimal = Decimal("1.0")


class RankingBase(BaseModel):
    tournament_id: TournamentId
    position: int
    level_id: LevelId | None = None
    scoring_type: ScoringType = ScoringType.MATCH_POINTS
    num_sets: int = 1
    max_points: int = 21
    last_set_max_points: int | None = None
    two_point_advantage: bool = True
    side_switch_every_n_points: int | None = None


# Keep for backwards-compatibility with insert helpers / existing SQL insert code
RankingInsertable = RankingBase


class Ranking(BaseModelORM, RankingBase):
    id: RankingId
    created: datetime_utc
    # Exactly one will be non-None depending on scoring_type
    match_points: RankingMatchPointsData | None = None
    set_points_with_bonus: RankingSetPointsWithMatchBonusData | None = None


# --- Request bodies (discriminated union) ---


class RankingMatchPointsBody(BaseModel):
    scoring_type: Literal["MATCH_POINTS"] = "MATCH_POINTS"
    win_points: Decimal = Decimal("1.0")
    draw_points: Decimal = Decimal("0.5")
    loss_points: Decimal = Decimal("0.0")
    num_sets: int = 1
    max_points: int = 21
    last_set_max_points: int | None = None
    two_point_advantage: bool = True
    position: int | None = None
    side_switch_every_n_points: int | None = None


class RankingSetPointsBody(BaseModel):
    scoring_type: Literal["SET_POINTS"] = "SET_POINTS"
    num_sets: int = 1
    max_points: int = 21
    last_set_max_points: int | None = None
    two_point_advantage: bool = True
    position: int | None = None
    side_switch_every_n_points: int | None = None


class RankingSetPointsWithMatchBonusBody(BaseModel):
    scoring_type: Literal["SET_POINTS_WITH_MATCH_BONUS"] = "SET_POINTS_WITH_MATCH_BONUS"
    match_bonus_points: Decimal = Decimal("1.0")
    num_sets: int = 1
    max_points: int = 21
    last_set_max_points: int | None = None
    two_point_advantage: bool = True
    position: int | None = None
    side_switch_every_n_points: int | None = None


RankingBody = Annotated[
    RankingMatchPointsBody | RankingSetPointsBody | RankingSetPointsWithMatchBonusBody,
    Field(discriminator="scoring_type"),
]

# Create body accepts any scoring type (same union as update)
RankingCreateBody = RankingBody
