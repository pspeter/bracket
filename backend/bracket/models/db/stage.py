from typing import Literal

from heliclockter import datetime_utc

from bracket.logic.planning.template import TemplateConfig
from bracket.models.db.shared import BaseModelORM
from bracket.models.db.stage_item import StageType
from bracket.utils.id_types import LevelId, StageId, TournamentId


class StageInsertable(BaseModelORM):
    tournament_id: TournamentId
    name: str
    created: datetime_utc
    is_active: bool
    level_id: LevelId | None = None


class Stage(StageInsertable):
    id: StageId


class StageCreateBody(BaseModelORM):
    level_id: LevelId | None = None


class StageUpdateBody(BaseModelORM):
    name: str


class StageActivateBody(BaseModelORM):
    direction: Literal["next", "previous"] = "next"
    level_id: LevelId | None = None


class StageTemplateCreateBody(BaseModelORM):
    groups: int
    total_teams: int
    until_rank: int | Literal["all"]
    include_semi_final: bool = True
    level_id: LevelId | None = None

    def to_template_config(self) -> TemplateConfig:
        return TemplateConfig(
            groups=self.groups,
            total_teams=self.total_teams,
            until_rank=self.until_rank,
            include_semi_final=self.include_semi_final,
            group_stage_type=StageType.ROUND_ROBIN,
        )
