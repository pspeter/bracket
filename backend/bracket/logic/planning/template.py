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


def _tentative(slot: int, winner_from: str, winner_position: int) -> BlueprintInput:
    return BlueprintInput(slot=slot, winner_from=winner_from, winner_position=winner_position)


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


def _resolve_until_rank(config: TemplateConfig) -> int:
    if config.until_rank != "all":
        return config.until_rank
    if config.groups == 4 or (config.groups == 2 and config.include_semi_final):
        return 8
    # 2 groups, no semi-final: every group position gets a place match
    teams_per_group = config.total_teams // config.groups
    return teams_per_group * 2


def _build_4group_knockout(until_rank: int) -> BlueprintStage:
    items: list[BlueprintStageItem] = [
        BlueprintStageItem(
            name="Semi-final A",
            type=StageType.SINGLE_ELIMINATION,
            team_count=2,
            inputs=[
                _tentative(1, "Group A", 1),
                _tentative(2, "Group C", 1),
            ],
        ),
        BlueprintStageItem(
            name="Semi-final B",
            type=StageType.SINGLE_ELIMINATION,
            team_count=2,
            inputs=[
                _tentative(1, "Group B", 1),
                _tentative(2, "Group D", 1),
            ],
        ),
        BlueprintStageItem(
            name="Final",
            type=StageType.SINGLE_ELIMINATION,
            team_count=2,
            inputs=[
                _tentative(1, "Semi-final A", 1),
                _tentative(2, "Semi-final B", 1),
            ],
        ),
    ]

    if until_rank >= 4:
        items.append(
            BlueprintStageItem(
                name="3rd Place",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "Semi-final A", 2),
                    _tentative(2, "Semi-final B", 2),
                ],
            )
        )

    if until_rank >= 6:
        items += [
            BlueprintStageItem(
                name="5th-8th Semi A",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "Group B", 2),
                    _tentative(2, "Group D", 2),
                ],
            ),
            BlueprintStageItem(
                name="5th-8th Semi B",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "Group A", 2),
                    _tentative(2, "Group C", 2),
                ],
            ),
            BlueprintStageItem(
                name="5th Place",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "5th-8th Semi A", 1),
                    _tentative(2, "5th-8th Semi B", 1),
                ],
            ),
        ]

    if until_rank >= 8:
        items.append(
            BlueprintStageItem(
                name="7th Place",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "5th-8th Semi A", 2),
                    _tentative(2, "5th-8th Semi B", 2),
                ],
            )
        )

    return BlueprintStage(name="Knockout Phase", items=items)


def _build_2group_with_semifinal_knockout(until_rank: int) -> BlueprintStage:
    items: list[BlueprintStageItem] = [
        BlueprintStageItem(
            name="Semi-final A",
            type=StageType.SINGLE_ELIMINATION,
            team_count=2,
            inputs=[
                _tentative(1, "Group A", 1),
                _tentative(2, "Group B", 2),
            ],
        ),
        BlueprintStageItem(
            name="Semi-final B",
            type=StageType.SINGLE_ELIMINATION,
            team_count=2,
            inputs=[
                _tentative(1, "Group B", 1),
                _tentative(2, "Group A", 2),
            ],
        ),
        BlueprintStageItem(
            name="Final",
            type=StageType.SINGLE_ELIMINATION,
            team_count=2,
            inputs=[
                _tentative(1, "Semi-final A", 1),
                _tentative(2, "Semi-final B", 1),
            ],
        ),
    ]

    if until_rank >= 4:
        items.append(
            BlueprintStageItem(
                name="3rd Place",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "Semi-final A", 2),
                    _tentative(2, "Semi-final B", 2),
                ],
            )
        )

    if until_rank >= 6:
        items += [
            BlueprintStageItem(
                name="5th-8th Semi A",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "Group A", 2),
                    _tentative(2, "Group B", 1),
                ],
            ),
            BlueprintStageItem(
                name="5th-8th Semi B",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "Group B", 2),
                    _tentative(2, "Group A", 1),
                ],
            ),
            BlueprintStageItem(
                name="5th Place",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "5th-8th Semi A", 1),
                    _tentative(2, "5th-8th Semi B", 1),
                ],
            ),
        ]

    if until_rank >= 8:
        items.append(
            BlueprintStageItem(
                name="7th Place",
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "5th-8th Semi A", 2),
                    _tentative(2, "5th-8th Semi B", 2),
                ],
            )
        )

    return BlueprintStage(name="Knockout Phase", items=items)


def _build_2group_no_semifinal_knockout(until_rank: int, teams_per_group: int) -> BlueprintStage:
    place_names = ["Final", "3rd Place", "5th Place", "7th Place"]
    items: list[BlueprintStageItem] = []
    for i in range(teams_per_group):
        rank = (i + 1) * 2
        if rank > until_rank:
            break
        name = place_names[i] if i < len(place_names) else f"{rank - 1}th Place"
        items.append(
            BlueprintStageItem(
                name=name,
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    _tentative(1, "Group A", i + 1),
                    _tentative(2, "Group B", i + 1),
                ],
            )
        )
    return BlueprintStage(name="Knockout Phase", items=items)


def build_template_blueprint(config: TemplateConfig) -> Blueprint:
    until_rank = _resolve_until_rank(config)
    group_stage = _build_group_stage(config)

    if config.groups == 4:
        knockout_stage = _build_4group_knockout(until_rank)
    elif config.include_semi_final:
        knockout_stage = _build_2group_with_semifinal_knockout(until_rank)
    else:
        teams_per_group = config.total_teams // config.groups
        knockout_stage = _build_2group_no_semifinal_knockout(until_rank, teams_per_group)

    return Blueprint(stages=[group_stage, knockout_stage])
