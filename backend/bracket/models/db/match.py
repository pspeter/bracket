import json
from decimal import Decimal
from enum import auto
from typing import cast

from heliclockter import datetime_utc, timedelta
from pydantic import BaseModel, Field, field_validator

from bracket.models.db.court import Court
from bracket.models.db.referee import Referee
from bracket.models.db.shared import BaseModelORM
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.utils.id_types import (
    CourtId,
    LevelId,
    MatchId,
    RefereeId,
    RoundId,
    StageItemInputId,
    TeamId,
)
from bracket.utils.types import EnumAutoStr, assert_some


class MatchState(EnumAutoStr):
    NOT_STARTED = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()


class MatchBaseInsertable(BaseModelORM):
    created: datetime_utc
    start_time: datetime_utc | None = None
    duration_minutes: int
    custom_duration_minutes: int | None = None
    round_id: RoundId
    stage_item_input1_score: int
    stage_item_input2_score: int
    court_id: CourtId | None = None
    referee_id: RefereeId | None = None
    stage_item_input1_conflict: bool
    stage_item_input2_conflict: bool
    precedence_conflict: bool = False
    short_break_conflict: bool = False
    referee_conflict: bool = False
    state: MatchState = MatchState.NOT_STARTED
    completed_at: datetime_utc | None = None

    @property
    def end_time(self) -> datetime_utc:
        assert self.start_time
        return self.start_time + timedelta(minutes=self.duration_minutes)


class MatchInsertable(MatchBaseInsertable):
    stage_item_input1_id: StageItemInputId | None = None
    stage_item_input2_id: StageItemInputId | None = None
    stage_item_input1_winner_from_match_id: MatchId | None = None
    stage_item_input2_winner_from_match_id: MatchId | None = None


class Match(MatchInsertable):
    id: MatchId
    stage_item_input1: StageItemInput | None = None
    stage_item_input2: StageItemInput | None = None

    def get_winner(self) -> StageItemInput | None:
        if self.state is not MatchState.COMPLETED:
            return None
        if self.stage_item_input1_score > self.stage_item_input2_score:
            return self.stage_item_input1
        if self.stage_item_input1_score < self.stage_item_input2_score:
            return self.stage_item_input2

        return None


class MatchWithDetails(Match):
    """
    MatchWithDetails has zero or one defined stage item inputs, but not both.
    """

    court: Court | None = None
    referee: Referee | None = None
    level_id: LevelId | None = None

    @field_validator("stage_item_input1", "stage_item_input2", "court", "referee", mode="before")
    @staticmethod
    def parse_nested_json(value: str | dict[str, object] | None) -> str | dict[str, object] | None:
        if isinstance(value, str):
            return cast("str | dict[str, object]", json.loads(value))
        return value


def get_match_hash(
    stage_item_input1_id: StageItemInputId | None, stage_item_input2_id: StageItemInputId | None
) -> str:
    return f"{stage_item_input1_id}-{stage_item_input2_id}"


class MatchWithDetailsDefinitive(Match):
    level_id: LevelId | None = None
    stage_item_input1: StageItemInput  # pyrefly: ignore [bad-override]
    stage_item_input2: StageItemInput  # pyrefly: ignore [bad-override]
    court: Court | None = None
    referee: Referee | None = None

    @property
    def stage_item_inputs(self) -> list[StageItemInput]:
        return [self.stage_item_input1, self.stage_item_input2]

    @property
    def stage_item_input_ids(self) -> list[StageItemInputId]:
        return [assert_some(self.stage_item_input1_id), assert_some(self.stage_item_input2_id)]

    def get_input_ids_hashes(self) -> list[str]:
        return [
            get_match_hash(self.stage_item_input1_id, self.stage_item_input2_id),
            get_match_hash(self.stage_item_input2_id, self.stage_item_input1_id),
        ]


class MatchBody(BaseModelORM):
    round_id: RoundId
    stage_item_input1_score: int = 0
    stage_item_input2_score: int = 0
    court_id: CourtId | None = None
    referee_team_id: TeamId | None = None
    referee_name: str | None = None
    custom_duration_minutes: int | None = None
    state: MatchState = MatchState.NOT_STARTED
    completed_at: datetime_utc | None = None


class MatchScoreTrackingBody(BaseModelORM):
    stage_item_input1_score: int = 0
    stage_item_input2_score: int = 0
    state: MatchState = MatchState.NOT_STARTED


class MatchCreateBodyFrontend(BaseModelORM):
    round_id: RoundId
    court_id: CourtId | None = None
    stage_item_input1_id: StageItemInputId | None = None
    stage_item_input2_id: StageItemInputId | None = None
    stage_item_input1_winner_from_match_id: MatchId | None = None
    stage_item_input2_winner_from_match_id: MatchId | None = None


class MatchCreateBody(MatchCreateBodyFrontend):
    duration_minutes: int
    custom_duration_minutes: int | None = None


class MatchRescheduleBody(BaseModelORM):
    old_court_id: CourtId | None = None
    old_position: int | None = None
    new_court_id: CourtId
    new_position: int


class MatchSwapBody(BaseModelORM):
    match1_id: MatchId
    match2_id: MatchId


class SchedulerWeights(BaseModelORM):
    """Objective weights for the auto-scheduler's weighted-sum CP-SAT objective.

    Defaults are the empirically tuned constants from PRD #73. Every term is measured in
    minutes (court locality in court-count, scaled up so it can matter against the
    minute-sized terms), so the ratios between these weights are what set the priorities:
    makespan and team rest lead, locality and group sync only bend a schedule that is
    otherwise free. ``comfortable_rest_minutes`` is the gap below which a team's consecutive
    matches are penalised; longer gaps are free.
    """

    makespan: int = Field(default=150, ge=0)
    team_rest: int = Field(default=13, ge=0)
    group_sync: int = Field(default=8, ge=0)
    court_locality: int = Field(default=4, ge=0)
    comfortable_rest_minutes: int = Field(default=30, ge=0)


class MatchResizeBreakBody(BaseModelORM):
    # The break sits before this match on its court: the gap between the previous
    # match's end (or the tournament start, for the first match) and this match's
    # start. Resizing it shifts this match and every later match on the court by
    # the delta.
    new_duration_minutes: int = Field(ge=0)


class MatchFilter(BaseModel):
    elo_diff_threshold: int
    only_recommended: bool
    limit: int
    iterations: int


class SuggestedMatch(BaseModel):
    stage_item_input1: StageItemInput
    stage_item_input2: StageItemInput
    elo_diff: Decimal
    swiss_diff: Decimal
    is_recommended: bool
    times_played_sum: int
    player_behind_schedule_count: int

    @property
    def stage_item_input_ids(self) -> list[int]:
        return [self.stage_item_input1.id, self.stage_item_input2.id]
