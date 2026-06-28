from enum import auto

from heliclockter import datetime_utc
from pydantic import Field, model_validator

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import ClubId, LevelId, TournamentId
from bracket.utils.pydantic import EmptyStrToNone
from bracket.utils.types import EnumAutoStr


class TournamentStatus(EnumAutoStr):
    OPEN = auto()
    ARCHIVED = auto()


class TournamentInsertable(BaseModelORM):
    club_id: ClubId
    name: str
    created: datetime_utc
    start_time: datetime_utc
    duration_minutes: int = Field(..., ge=1)
    margin_minutes: int = Field(..., ge=0)
    dashboard_public: bool
    dashboard_endpoint: str | None = None
    logo_path: str | None = None
    players_can_be_in_multiple_teams: bool
    auto_assign_courts: bool
    status: TournamentStatus = TournamentStatus.OPEN
    signup_enabled: bool = False
    signup_token: str | None = None
    max_team_size: int = Field(4, ge=1)
    min_team_size: int = Field(0, ge=0)
    signup_team_choice_enabled: bool = True
    score_tracking_enabled: bool = False
    score_tracking_token: str | None = None
    rules: str | None = None
    referees_enabled: bool = False

    @model_validator(mode="after")
    def validate_team_size_bounds(self) -> "TournamentInsertable":
        if self.min_team_size > self.max_team_size:
            raise ValueError("min_team_size must be less than or equal to max_team_size")
        return self


class Tournament(TournamentInsertable):
    id: TournamentId


class LevelResponse(BaseModelORM):
    id: LevelId
    name: str
    position: int


class TournamentWithLevels(Tournament):
    levels: list[LevelResponse] = []


class TournamentUpdateBody(BaseModelORM):
    start_time: datetime_utc
    name: str
    dashboard_public: bool
    dashboard_endpoint: EmptyStrToNone | str = None
    players_can_be_in_multiple_teams: bool
    auto_assign_courts: bool
    duration_minutes: int = Field(..., ge=1)
    margin_minutes: int = Field(..., ge=0)
    # Required on PUT: omitted keys must not fall back to insert defaults (e.g. max_team_size=4).
    signup_enabled: bool
    max_team_size: int = Field(..., ge=1)
    min_team_size: int = Field(..., ge=0)
    signup_team_choice_enabled: bool
    score_tracking_enabled: bool = False
    referees_enabled: bool = False
    rules: str | None = Field(None, max_length=50_000)

    @model_validator(mode="before")
    @classmethod
    def reject_levels(cls, data: dict) -> dict:  # type: ignore[type-arg]
        if isinstance(data, dict) and "levels" in data:
            raise ValueError("Levels cannot be changed after tournament creation")
        return data

    @model_validator(mode="after")
    def validate_team_size_bounds(self) -> "TournamentUpdateBody":
        if self.min_team_size > self.max_team_size:
            raise ValueError("min_team_size must be less than or equal to max_team_size")
        return self


class TournamentChangeStatusBody(BaseModelORM):
    status: TournamentStatus


class TournamentBody(TournamentUpdateBody):
    club_id: ClubId
    min_team_size: int = Field(0, ge=0)
    levels: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_levels(cls, data: dict) -> dict:  # type: ignore[type-arg]
        return data
