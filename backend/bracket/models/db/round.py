from enum import auto

from heliclockter import datetime_utc
from pydantic import computed_field

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import MatchId, RoundId, StageItemId
from bracket.utils.types import EnumAutoStr


class RoundLifecycleState(EnumAutoStr):
    DRAFT = auto()
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_draft(self) -> bool:
        return self.lifecycle_state == RoundLifecycleState.DRAFT


class Round(RoundInsertable):
    id: RoundId


class RoundUpdateBody(BaseModelORM):
    name: str
    lifecycle_state: RoundLifecycleState


class RoundCreateBody(BaseModelORM):
    name: str | None = None
    stage_item_id: StageItemId


class SwapMatchInputsBody(BaseModelORM):
    match1_id: MatchId
    match2_id: MatchId
