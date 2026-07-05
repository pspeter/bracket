from __future__ import annotations

from typing import Any

from pydantic import field_validator, model_validator

from bracket.models.db.match import MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.round import Round
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
