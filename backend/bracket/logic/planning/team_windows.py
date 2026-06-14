from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from heliclockter import datetime_utc

from bracket.models.db.match import MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.models.db.util import StageWithStageItems
from bracket.utils.id_types import StageItemInputId, TeamId

MatchWithDetailsAny = MatchWithDetailsDefinitive | MatchWithDetails


@dataclass(frozen=True)
class PlayingWindow:
    stage_item_input_id: StageItemInputId
    start_time: datetime_utc
    end_time: datetime_utc


TeamPlayingWindows = dict[TeamId, list[tuple[MatchWithDetailsAny, PlayingWindow]]]


def get_team_playing_windows(stages: list[StageWithStageItems]) -> TeamPlayingWindows:
    team_ids_by_input_id = _get_team_ids_by_input_id(stages)
    windows_by_team_id: defaultdict[TeamId, list[tuple[MatchWithDetailsAny, PlayingWindow]]] = (
        defaultdict(list)
    )

    for stage in stages:
        for stage_item in stage.stage_items:
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    if match.start_time is None:
                        continue
                    for stage_item_input_id, stage_item_input in _get_match_inputs(match):
                        if stage_item_input_id is None:
                            continue
                        team_id = _get_team_id(
                            stage_item_input_id,
                            stage_item_input,
                            team_ids_by_input_id,
                        )
                        if team_id is None:
                            continue
                        windows_by_team_id[team_id].append(
                            (
                                match,
                                PlayingWindow(
                                    stage_item_input_id=stage_item_input_id,
                                    start_time=match.start_time,
                                    end_time=match.end_time,
                                ),
                            )
                        )

    return dict(windows_by_team_id)


def _get_team_ids_by_input_id(
    stages: list[StageWithStageItems],
) -> dict[StageItemInputId, TeamId]:
    team_ids_by_input_id: dict[StageItemInputId, TeamId] = {}
    for stage in stages:
        for stage_item in stage.stage_items:
            for stage_item_input in stage_item.inputs:
                _set_team_id(team_ids_by_input_id, stage_item_input)
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    _set_team_id(team_ids_by_input_id, match.stage_item_input1)
                    _set_team_id(team_ids_by_input_id, match.stage_item_input2)
    return team_ids_by_input_id


def _set_team_id(
    team_ids_by_input_id: dict[StageItemInputId, TeamId],
    stage_item_input: StageItemInput | None,
) -> None:
    if stage_item_input is None or stage_item_input.team_id is None:
        return
    team_ids_by_input_id[stage_item_input.id] = stage_item_input.team_id


def _get_match_inputs(
    match: MatchWithDetailsAny,
) -> tuple[
    tuple[StageItemInputId | None, StageItemInput | None],
    tuple[StageItemInputId | None, StageItemInput | None],
]:
    return (
        (match.stage_item_input1_id, match.stage_item_input1),
        (match.stage_item_input2_id, match.stage_item_input2),
    )


def _get_team_id(
    stage_item_input_id: StageItemInputId,
    stage_item_input: StageItemInput | None,
    team_ids_by_input_id: dict[StageItemInputId, TeamId],
) -> TeamId | None:
    if stage_item_input is not None and stage_item_input.team_id is not None:
        return stage_item_input.team_id
    return team_ids_by_input_id.get(stage_item_input_id)
