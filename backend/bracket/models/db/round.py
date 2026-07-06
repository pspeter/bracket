from enum import auto

from heliclockter import datetime_utc

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import MatchId, RoundId, StageItemId
from bracket.utils.types import EnumAutoStr


class RoundLifecycleState(EnumAutoStr):
    ACTIVE = auto()
    PLACEHOLDER = auto()
    RESOLVED = auto()
    LOCKED = auto()


class RoundInsertable(BaseModelORM):
    created: datetime_utc
    stage_item_id: StageItemId
    name: str
    lifecycle_state: RoundLifecycleState = RoundLifecycleState.ACTIVE
    is_pinned: bool | None = None


class Round(RoundInsertable):
    id: RoundId


class RoundUpdateBody(BaseModelORM):
    name: str
    lifecycle_state: RoundLifecycleState


class SwapMatchInputsBody(BaseModelORM):
    match1_id: MatchId
    match2_id: MatchId
