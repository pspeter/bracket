from typing import Literal

from heliclockter import datetime_utc

from bracket.logic.planning.template import TemplateConfig
from bracket.models.db.shared import BaseModelORM
from bracket.models.db.stage_item import StageType
from bracket.utils.id_types import StageId, TournamentId


class StageInsertable(BaseModelORM):
    tournament_id: TournamentId
    name: str
    created: datetime_utc
    is_active: bool


class Stage(StageInsertable):
    id: StageId


class StageUpdateBody(BaseModelORM):
    name: str


class StageActivateBody(BaseModelORM):
    direction: Literal["next", "previous"] = "next"


class StageTemplateCreateBody(BaseModelORM):
    groups: int
    total_teams: int
    until_rank: int | Literal["all"]
    include_semi_final: bool = True

    def to_template_config(self) -> TemplateConfig:
        return TemplateConfig(
            groups=self.groups,
            total_teams=self.total_teams,
            until_rank=self.until_rank,
            include_semi_final=self.include_semi_final,
            group_stage_type=StageType.ROUND_ROBIN,
        )
