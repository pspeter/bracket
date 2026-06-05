from __future__ import annotations

import json
from decimal import Decimal

from heliclockter import datetime_utc
from pydantic import Field, field_validator

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import LevelId, PlayerId, TeamId, TournamentId


class PlayerInsertable(BaseModelORM):
    active: bool
    name: str
    created: datetime_utc
    tournament_id: TournamentId
    elo_score: Decimal = Decimal("0.0")
    swiss_score: Decimal = Decimal("0.0")
    wins: int = 0
    draws: int = 0
    losses: int = 0
    level_id: LevelId | None = None


class Player(PlayerInsertable):
    id: PlayerId

    def __hash__(self) -> int:
        return self.id


class PlayerTeam(BaseModelORM):
    id: TeamId
    name: str
    level_id: LevelId | None = None


class PlayerWithTeams(Player):
    teams: list[PlayerTeam] = []

    @field_validator("teams", mode="before")
    @staticmethod
    def handle_teams(values: list[PlayerTeam] | str) -> list[PlayerTeam]:
        if isinstance(values, str):
            values_json: list[PlayerTeam] = json.loads(values)
            if values_json == [None]:
                return []
            return values_json
        return values


class PlayerBody(BaseModelORM):
    name: str = Field(..., min_length=1, max_length=30)
    active: bool


class PlayerMultiBody(BaseModelORM):
    names: str = Field(..., min_length=1)
    active: bool


class PlayerToInsert(PlayerBody):
    created: datetime_utc
    tournament_id: TournamentId
    elo_score: Decimal = Decimal("1200.0")
    swiss_score: Decimal
    wins: int = 0
    draws: int = 0
    losses: int = 0
    level_id: LevelId | None = None
