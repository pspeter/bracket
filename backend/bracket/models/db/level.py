from heliclockter import datetime_utc

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import LevelId, TournamentId


class LevelInsertable(BaseModelORM):
    tournament_id: TournamentId
    name: str
    position: int
    created: datetime_utc


class Level(LevelInsertable):
    id: LevelId


class LevelUpdateBody(BaseModelORM):
    name: str
