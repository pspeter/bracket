from collections import defaultdict
from dataclasses import dataclass

from heliclockter import datetime_utc

from bracket.database import database
from bracket.models.db.match import Match, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.util import StageWithStageItems
from bracket.utils.id_types import CourtId, MatchId, StageItemId


def matches_overlap(match1: Match, match2: Match) -> bool:
    if match1.start_time is None or match2.start_time is None:
        return False

    # Half-open intervals [start, end): back-to-back matches (end1 == start2) do not conflict.
    return match1.start_time < match2.end_time and match2.start_time < match1.end_time


@dataclass
class MatchConflictFlags:
    stage_item_input1_conflict: bool = False
    stage_item_input2_conflict: bool = False
    precedence_conflict: bool = False
    short_break_conflict: bool = False


def _get_all_matches(
    stages: list[StageWithStageItems],
) -> list[MatchWithDetailsDefinitive | MatchWithDetails]:
    return [
        match
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
    ]


def _set_team_overlap_conflicts(
    matches: list[MatchWithDetailsDefinitive | MatchWithDetails],
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    definitive_matches = [
        match for match in matches if isinstance(match, MatchWithDetailsDefinitive)
    ]

    for i, match1 in enumerate(definitive_matches):
        for match2 in definitive_matches[i + 1 :]:
            conflicting_input_ids = []

            if match2.stage_item_input1_id in match1.stage_item_input_ids:
                conflicting_input_ids.append(match2.stage_item_input1_id)
            if match2.stage_item_input2_id in match1.stage_item_input_ids:
                conflicting_input_ids.append(match2.stage_item_input2_id)

            if len(conflicting_input_ids) < 1 or not matches_overlap(match1, match2):
                continue

            for match in (match1, match2):
                flags[match.id].stage_item_input1_conflict = (
                    flags[match.id].stage_item_input1_conflict
                    or match.stage_item_input1_id in conflicting_input_ids
                )
                flags[match.id].stage_item_input2_conflict = (
                    flags[match.id].stage_item_input2_conflict
                    or match.stage_item_input2_id in conflicting_input_ids
                )


def _set_winner_of_precedence_conflicts(
    matches: list[MatchWithDetailsDefinitive | MatchWithDetails],
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    matches_by_id = {match.id: match for match in matches}

    for match in matches:
        if match.start_time is None:
            continue

        feeder_ids = [
            match.stage_item_input1_winner_from_match_id,
            match.stage_item_input2_winner_from_match_id,
        ]
        for feeder_id in feeder_ids:
            if feeder_id is None:
                continue
            feeder = matches_by_id.get(feeder_id)
            if (
                feeder is not None
                and feeder.start_time is not None
                and match.start_time < feeder.end_time
            ):
                flags[match.id].precedence_conflict = True


def _get_stage_item_end_times(
    stages: list[StageWithStageItems],
) -> dict[StageItemId, datetime_utc]:
    stage_item_end_times: dict[StageItemId, datetime_utc] = {}
    for stage in stages:
        for stage_item in stage.stage_items:
            latest_end_time: datetime_utc | None = None
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    if match.start_time is None:
                        continue
                    if latest_end_time is None or match.end_time > latest_end_time:
                        latest_end_time = match.end_time
            if latest_end_time is not None:
                stage_item_end_times[stage_item.id] = latest_end_time
    return stage_item_end_times


def _set_cross_stage_precedence_conflicts(
    stages: list[StageWithStageItems],
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    stage_item_end_times = _get_stage_item_end_times(stages)

    for match in _get_all_matches(stages):
        if match.start_time is None:
            continue

        for stage_item_input in (match.stage_item_input1, match.stage_item_input2):
            if stage_item_input is None or stage_item_input.winner_from_stage_item_id is None:
                continue
            source_end_time = stage_item_end_times.get(stage_item_input.winner_from_stage_item_id)
            if source_end_time is not None and match.start_time < source_end_time:
                flags[match.id].precedence_conflict = True


def _set_short_break_conflicts(
    matches: list[MatchWithDetailsDefinitive | MatchWithDetails],
    default_break_minutes: int,
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    matches_by_court: defaultdict[CourtId, list[MatchWithDetailsDefinitive | MatchWithDetails]] = (
        defaultdict(list)
    )
    for match in matches:
        if match.court_id is not None and match.start_time is not None:
            matches_by_court[match.court_id].append(match)

    for court_matches in matches_by_court.values():
        scheduled = sorted(court_matches, key=lambda match: (match.start_time, match.id))
        for previous, match in zip(scheduled, scheduled[1:], strict=False):
            assert previous.start_time is not None
            assert match.start_time is not None
            break_minutes = (match.start_time - previous.end_time).total_seconds() / 60
            if break_minutes < default_break_minutes:
                flags[match.id].short_break_conflict = True


def get_match_conflict_flags(
    stages: list[StageWithStageItems], default_break_minutes: int
) -> dict[MatchId, MatchConflictFlags]:
    matches = _get_all_matches(stages)
    flags = {match.id: MatchConflictFlags() for match in matches}

    _set_team_overlap_conflicts(matches, flags)
    _set_winner_of_precedence_conflicts(matches, flags)
    _set_cross_stage_precedence_conflicts(stages, flags)
    _set_short_break_conflicts(matches, default_break_minutes, flags)

    return flags


def get_conflicting_matches(
    stages: list[StageWithStageItems],
) -> tuple[
    defaultdict[MatchId, list[bool]],
    set[MatchId],
]:
    flags = get_match_conflict_flags(stages, default_break_minutes=0)
    conflicts_to_set: defaultdict[MatchId, list[bool]] = defaultdict(lambda: [False, False])
    conflicts_to_clear = set()

    for match_id, conflict_flags in flags.items():
        if conflict_flags.stage_item_input1_conflict or conflict_flags.stage_item_input2_conflict:
            conflicts_to_set[match_id] = [
                conflict_flags.stage_item_input1_conflict,
                conflict_flags.stage_item_input2_conflict,
            ]
        else:
            conflicts_to_clear.add(match_id)

    assert set(conflicts_to_set.keys()).intersection(conflicts_to_clear) == set()
    return conflicts_to_set, conflicts_to_clear


async def set_conflicts(match_conflicts: dict[MatchId, MatchConflictFlags]) -> None:
    for match_id, conflict in match_conflicts.items():
        await database.execute(
            """
            UPDATE matches
            SET
                stage_item_input1_conflict = :stage_item_input1_conflict,
                stage_item_input2_conflict = :stage_item_input2_conflict,
                precedence_conflict = :precedence_conflict,
                short_break_conflict = :short_break_conflict
            WHERE id = :match_id
            """,
            values={
                "match_id": match_id,
                "stage_item_input1_conflict": conflict.stage_item_input1_conflict,
                "stage_item_input2_conflict": conflict.stage_item_input2_conflict,
                "precedence_conflict": conflict.precedence_conflict,
                "short_break_conflict": conflict.short_break_conflict,
            },
        )


async def handle_conflicts(
    stages: list[StageWithStageItems], default_break_minutes: int | None = None
) -> None:
    if len(stages) < 1:
        return

    if default_break_minutes is None:
        from bracket.sql.tournaments import sql_get_tournament

        tournament = await sql_get_tournament(stages[0].tournament_id)
        default_break_minutes = tournament.margin_minutes

    await set_conflicts(get_match_conflict_flags(stages, default_break_minutes))
