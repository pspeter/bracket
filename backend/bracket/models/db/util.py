from __future__ import annotations

from typing import Any

from pydantic import field_validator, model_validator

from bracket.models.db.match import MatchState, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.round import Round, RoundLifecycleState
from bracket.models.db.stage import Stage
from bracket.models.db.stage_item import StageItem, StageType
from bracket.models.db.stage_item_inputs import StageItemInput


class RoundWithMatches(Round):
    matches: list[MatchWithDetailsDefinitive | MatchWithDetails]

    @field_validator("matches", mode="after")
    @staticmethod
    def sort_matches_by_id(
        values: list[MatchWithDetailsDefinitive | MatchWithDetails],
    ) -> list[MatchWithDetailsDefinitive | MatchWithDetails]:
        # Domain invariant: matches are always in id order (i.e. creation order), regardless of
        # what order the caller assembled them in. This is the single owner of that guarantee from
        # the model's point of view -- the SQL's `ORDER BY m.id` is an optimization/no-op given
        # this validator, not the source of truth.
        return sorted(values, key=lambda match: match.id)


def is_round_complete(round_: RoundWithMatches) -> bool:
    """Whether every match in a resolved round has concluded.

    A match counts as concluded either by being COMPLETED, or -- only once its round has been
    resolved -- by never having been assigned a pairing at all. The latter happens when a
    standings-resolved round (e.g. Mexicano, see issue #261) is resolved against fewer active
    inputs than its pre-built skeleton has playing slots for (a mid-tournament deactivation
    shrinking the active field): the surplus match is explicitly cleared to [None, None] rather
    than left holding a stale assignment, and must not block the round -- or the whole stage
    item -- from ever being considered finished. A PLACEHOLDER round's matches are also unset,
    but must NOT count as complete: gating on ``lifecycle_state == RESOLVED`` is what tells the
    two cases apart.
    """
    if not round_.matches:
        return False
    return all(
        match.state is MatchState.COMPLETED
        or (
            round_.lifecycle_state == RoundLifecycleState.RESOLVED
            and match.stage_item_input1_id is None
            and match.stage_item_input2_id is None
        )
        for match in round_.matches
    )


class StageItemWithRounds(StageItem):
    rounds: list[RoundWithMatches]
    inputs: list[StageItemInput]
    type_name: str

    @model_validator(mode="before")
    @classmethod
    def fill_type_name(cls, values: Any) -> Any:
        match values["type"]:
            case str() as type_:
                values["type_name"] = type_.lower().capitalize().replace("_", " ")
            case StageType() as type_:
                values["type_name"] = str(type_.value).lower().capitalize().replace("_", " ")

        return values

    @field_validator("rounds", mode="after")
    @staticmethod
    def sort_rounds_by_id(values: list[RoundWithMatches]) -> list[RoundWithMatches]:
        # Domain invariant: rounds are always in id order (i.e. round 1, 2, 3 ...), regardless of
        # what order the caller assembled them in. This is the single owner of that guarantee from
        # the model's point of view -- the SQL's `ORDER BY r.id` is an optimization/no-op given
        # this validator -- and it ensures round-1 logic (e.g. Swiss resolution) always sees the
        # real round 1 first.
        return sorted(values, key=lambda round_: round_.id)


class StageWithStageItems(Stage):
    stage_items: list[StageItemWithRounds]
