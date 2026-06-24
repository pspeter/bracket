from __future__ import annotations

import json
from typing import Any

from pydantic import field_validator, model_validator

from bracket.models.db.match import Match, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.round import Round
from bracket.models.db.stage import Stage
from bracket.models.db.stage_item import StageItem, StageType
from bracket.models.db.stage_item_inputs import StageItemInput


class RoundWithMatches(Round):
    matches: list[MatchWithDetailsDefinitive | MatchWithDetails]

    @field_validator("matches", mode="before")
    @staticmethod
    def handle_matches(values: list[Match]) -> list[Match]:
        if values == [None]:
            return []
        return values

    @field_validator("matches", mode="after")
    @staticmethod
    def sort_matches_by_id(
        values: list[MatchWithDetailsDefinitive | MatchWithDetails],
    ) -> list[MatchWithDetailsDefinitive | MatchWithDetails]:
        # Guarantee a stable, deterministic match order (by id, i.e. creation order) regardless of
        # how the database happened to aggregate them. The SQL already orders these, but this keeps
        # the contract from silently regressing if that query is ever changed.
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

    @field_validator("rounds", "inputs", mode="before")
    @staticmethod
    def handle_empty_list_elements(values: list[Any] | None) -> list[Any]:
        if values is None:
            return []
        return [value for value in values if value is not None]

    @field_validator("rounds", mode="after")
    @staticmethod
    def sort_rounds_by_id(values: list[RoundWithMatches]) -> list[RoundWithMatches]:
        # Guarantee a stable, deterministic round order (by id, i.e. round 1, 2, 3 …) regardless of
        # how the database aggregated them. The SQL already orders these, but this keeps the
        # contract from silently regressing if that query is ever changed, and ensures round-1
        # logic (e.g. Swiss resolution) always sees the real round 1 first.
        return sorted(values, key=lambda round_: round_.id)


class StageWithStageItems(Stage):
    stage_items: list[StageItemWithRounds]

    @field_validator("stage_items", mode="before")
    @staticmethod
    def handle_stage_items(values: list[StageItemWithRounds]) -> list[StageItemWithRounds]:
        if isinstance(values, str):
            values_json = json.loads(values)
            if values_json == [None]:
                return []
            return values_json

        return values
