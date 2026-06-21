from enum import auto

from heliclockter import datetime_utc

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import RoundId, StageItemId
from bracket.utils.types import EnumAutoStr


class RoundLifecycleState(EnumAutoStr):
    PLACEHOLDER = auto()
    RESOLVED = auto()
    LOCKED = auto()


class RoundInsertable(BaseModelORM):
    created: datetime_utc
    stage_item_id: StageItemId
    is_draft: bool
    name: str
    lifecycle_state: RoundLifecycleState | None = None
    is_pinned: bool | None = None


class Round(RoundInsertable):
    id: RoundId


class RoundUpdateBody(BaseModelORM):
    name: str
    is_draft: bool


class RoundCreateBody(BaseModelORM):
    name: str | None = None
    stage_item_id: StageItemId
