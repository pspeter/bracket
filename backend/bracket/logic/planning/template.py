from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from bracket.models.db.stage_item import StageType


@dataclass(frozen=True)
class BlueprintInput:
    slot: int
    winner_from: str | None
    winner_position: int | None


@dataclass
class BlueprintStageItem:
    name: str
    type: StageType
    team_count: int
    inputs: list[BlueprintInput]


@dataclass
class BlueprintStage:
    name: str
    items: list[BlueprintStageItem] = field(default_factory=list)


@dataclass
class Blueprint:
    stages: list[BlueprintStage]


@dataclass
class TemplateConfig:
    groups: Literal[2, 4]
    total_teams: int
    until_rank: int | Literal["all"]
    include_semi_final: bool
    group_stage_type: StageType


def _group_names(groups: int) -> list[str]:
    return [f"Group {chr(ord('A') + i)}" for i in range(groups)]


def _empty_inputs(team_count: int) -> list[BlueprintInput]:
    return [BlueprintInput(slot=i + 1, winner_from=None, winner_position=None) for i in range(team_count)]


def _t(slot: int, winner_from: str, winner_position: int) -> BlueprintInput:
    return BlueprintInput(slot=slot, winner_from=winner_from, winner_position=winner_position)


def _max_rank(config: TemplateConfig) -> int:
    if config.groups == 4:
        return 8
    # Both 2-group variants: each group position pair yields one place match
    return (config.total_teams // config.groups) * 2


def _validate(config: TemplateConfig) -> None:
    if config.total_teams < 4:
        raise ValueError("total_teams must be at least 4")
    if config.total_teams % config.groups != 0:
        raise ValueError("total_teams must be divisible by groups")
    teams_per_group = config.total_teams // config.groups
    min_per_group = 3 if (config.groups == 2 and config.include_semi_final) else 2
    if teams_per_group < min_per_group:
        raise ValueError(f"teams per group must be at least {min_per_group}")
    if config.until_rank != "all":
        if config.until_rank < 2:
            raise ValueError("until_rank must be at least 2")
        if config.until_rank % 2 != 0:
            raise ValueError("until_rank must be even")
        if config.until_rank > _max_rank(config):
            raise ValueError(
                f"until_rank {config.until_rank} exceeds maximum {_max_rank(config)} for this config"
            )


def _resolve_until_rank(config: TemplateConfig) -> int:
    return _max_rank(config) if config.until_rank == "all" else config.until_rank


def _build_group_stage(config: TemplateConfig) -> BlueprintStage:
    teams_per_group = config.total_teams // config.groups
    return BlueprintStage(
        name="Group Phase",
        items=[
            BlueprintStageItem(
                name=name,
                type=config.group_stage_type,
                team_count=teams_per_group,
                inputs=_empty_inputs(teams_per_group),
            )
            for name in _group_names(config.groups)
        ],
    )


def _item(name: str, inputs: list[BlueprintInput]) -> BlueprintStageItem:
    return BlueprintStageItem(
        name=name,
        type=StageType.SINGLE_ELIMINATION,
        team_count=2,
        inputs=inputs,
    )


def _build_4group_stages(until_rank: int) -> tuple[BlueprintStage, BlueprintStage]:
    semis_items = [
        _item("Semi-final A", [_t(1, "Group A", 1), _t(2, "Group C", 1)]),
        _item("Semi-final B", [_t(1, "Group B", 1), _t(2, "Group D", 1)]),
    ]
    finals_items = [
        _item("Final", [_t(1, "Semi-final A", 1), _t(2, "Semi-final B", 1)]),
    ]

    if until_rank >= 4:
        finals_items.append(
            _item("3rd Place", [_t(1, "Semi-final A", 2), _t(2, "Semi-final B", 2)])
        )

    if until_rank >= 6:
        semis_items += [
            _item("5th-8th Semi A", [_t(1, "Group B", 2), _t(2, "Group D", 2)]),
            _item("5th-8th Semi B", [_t(1, "Group A", 2), _t(2, "Group C", 2)]),
        ]
        finals_items.append(
            _item("5th Place", [_t(1, "5th-8th Semi A", 1), _t(2, "5th-8th Semi B", 1)])
        )

    if until_rank >= 8:
        finals_items.append(
            _item("7th Place", [_t(1, "5th-8th Semi A", 2), _t(2, "5th-8th Semi B", 2)])
        )

    return BlueprintStage(name="Semi-finals", items=semis_items), BlueprintStage(name="Finals", items=finals_items)


def _build_2group_sf_stages(until_rank: int, teams_per_group: int) -> tuple[BlueprintStage, BlueprintStage]:
    # Semi-finals stage: only the two main cross-seeded semis, always
    semis_items = [
        _item("Semi-final A", [_t(1, "Group A", 1), _t(2, "Group B", 2)]),
        _item("Semi-final B", [_t(1, "Group B", 1), _t(2, "Group A", 2)]),
    ]
    finals_items = [
        _item("Final", [_t(1, "Semi-final A", 1), _t(2, "Semi-final B", 1)]),
    ]

    if until_rank >= 4:
        finals_items.append(
            _item("3rd Place", [_t(1, "Semi-final A", 2), _t(2, "Semi-final B", 2)])
        )

    # Ranks 5+ use direct group position matches (positions 3, 4, …)
    # The main semi-finals already consume positions 1 and 2 from each group.
    place_names = ["5th Place", "7th Place", "9th Place", "11th Place"]
    for i, position in enumerate(range(3, teams_per_group + 1)):
        rank = 4 + (position - 2) * 2
        if rank > until_rank:
            break
        name = place_names[i] if i < len(place_names) else f"{rank - 1}th Place"
        finals_items.append(_item(name, [_t(1, "Group A", position), _t(2, "Group B", position)]))

    return BlueprintStage(name="Semi-finals", items=semis_items), BlueprintStage(name="Finals", items=finals_items)


def _build_2group_nosf_finals(until_rank: int, teams_per_group: int) -> BlueprintStage:
    place_names = ["Final", "3rd Place", "5th Place", "7th Place"]
    items = []
    for i in range(teams_per_group):
        rank = (i + 1) * 2
        if rank > until_rank:
            break
        name = place_names[i] if i < len(place_names) else f"{rank - 1}th Place"
        items.append(_item(name, [_t(1, "Group A", i + 1), _t(2, "Group B", i + 1)]))
    return BlueprintStage(name="Finals", items=items)


def build_template_blueprint(config: TemplateConfig) -> Blueprint:
    _validate(config)
    until_rank = _resolve_until_rank(config)
    group_stage = _build_group_stage(config)

    if config.groups == 4 or config.include_semi_final:
        if config.groups == 4:
            semis_stage, finals_stage = _build_4group_stages(until_rank)
        else:
            semis_stage, finals_stage = _build_2group_sf_stages(until_rank, config.total_teams // config.groups)
        return Blueprint(stages=[group_stage, semis_stage, finals_stage])

    teams_per_group = config.total_teams // config.groups
    finals_stage = _build_2group_nosf_finals(until_rank, teams_per_group)
    return Blueprint(stages=[group_stage, finals_stage])
