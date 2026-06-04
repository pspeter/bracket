from collections import defaultdict
from typing import NamedTuple

from heliclockter import datetime_utc, timedelta

from bracket.models.db.court import Court
from bracket.models.db.match import (
    MatchRescheduleBody,
    MatchWithDetails,
    MatchWithDetailsDefinitive,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import StageWithStageItems
from bracket.sql.courts import get_all_courts_in_tournament
from bracket.sql.matches import (
    sql_reschedule_match_and_determine_duration_and_margin,
)
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import CourtId, LevelId, MatchId, TournamentId
from bracket.utils.types import assert_some


class ScheduleOperation(NamedTuple):
    court_id: CourtId
    start_time: datetime_utc
    position: int
    match: MatchWithDetails | MatchWithDetailsDefinitive


def build_schedule_plan(
    stages: list[StageWithStageItems],
    courts: list[Court],
    tournament: Tournament,
) -> list[ScheduleOperation]:
    """
    Pure function: computes the full scheduling plan for all unscheduled matches.

    Stages are grouped by level_id so each level progresses through its stages independently.
    Courts are shared across all levels; matches from different levels are interleaved.
    Stage boundaries are per-level: Level N's Stage K+1 only waits for its own Stage K to
    finish, not for any other level.
    """
    if not stages or not courts:
        return []

    # Group stages by level, preserving DB order (stages are already sorted by id)
    stages_by_level: dict[LevelId | None, list[StageWithStageItems]] = defaultdict(list)
    for stage in stages:
        stages_by_level[stage.level_id].append(stage)

    court_ids = [court.id for court in courts]
    court_next_time: dict[CourtId, datetime_utc] = {c: tournament.start_time for c in court_ids}
    court_next_position: dict[CourtId, int] = {c: 0 for c in court_ids}

    level_stage_start: dict[LevelId | None, datetime_utc] = {
        level_id: tournament.start_time for level_id in stages_by_level
    }
    level_stage_idx: dict[LevelId | None, int] = {level_id: 0 for level_id in stages_by_level}

    operations: list[ScheduleOperation] = []

    while True:
        active_levels = [
            level_id
            for level_id, level_stages in stages_by_level.items()
            if level_stage_idx[level_id] < len(level_stages)
        ]
        if not active_levels:
            break

        # Collect (level_id, stage_item) pairs from all active levels' current stage
        all_stage_items: list[tuple[LevelId | None, object]] = []
        for level_id in active_levels:
            stage = stages_by_level[level_id][level_stage_idx[level_id]]
            for stage_item in sorted(stage.stage_items, key=lambda si: si.name):
                all_stage_items.append((level_id, stage_item))

        # Assign stage_items to courts round-robin, collecting (level_id, match) pairs
        TaggedMatch = tuple[LevelId | None, MatchWithDetails | MatchWithDetailsDefinitive]
        court_matches: dict[CourtId, list[TaggedMatch]] = {c: [] for c in court_ids}
        for i, (level_id, stage_item) in enumerate(all_stage_items):
            court = courts[i % len(courts)]
            for round_ in sorted(stage_item.rounds, key=lambda r: r.id):
                for match in round_.matches:
                    if match.start_time is None and match.position_in_schedule is None:
                        court_matches[court.id].append((level_id, match))

        # Rebalance: move matches from most-loaded to least-loaded court
        while True:
            max_court = max(court_ids, key=lambda c: len(court_matches[c]))
            min_court = min(court_ids, key=lambda c: len(court_matches[c]))
            if len(court_matches[max_court]) - len(court_matches[min_court]) <= 1:
                break
            court_matches[min_court].append(court_matches[max_court].pop())

        # Track max end time per level across all courts for this scheduling round
        level_end_times: dict[LevelId | None, datetime_utc] = {}

        for court_id in court_ids:
            tagged = court_matches[court_id]
            if not tagged:
                continue

            # Matches from earlier-starting levels go first on the court
            tagged.sort(key=lambda x: level_stage_start[x[0]])

            current_time = court_next_time[court_id]
            position = court_next_position[court_id]

            for level_id, match in tagged:
                start_time = max(current_time, level_stage_start[level_id])
                operations.append(ScheduleOperation(court_id, start_time, position, match))
                end_time = start_time + timedelta(
                    minutes=match.duration_minutes + match.margin_minutes
                )
                current_time = end_time
                position += 1

                if level_id not in level_end_times or end_time > level_end_times[level_id]:
                    level_end_times[level_id] = end_time

            court_next_time[court_id] = current_time
            court_next_position[court_id] = position

        # Advance each active level to its next stage
        for level_id in active_levels:
            level_stage_start[level_id] = level_end_times.get(level_id, level_stage_start[level_id])
            level_stage_idx[level_id] += 1

    return operations


async def schedule_all_unscheduled_matches(
    tournament_id: TournamentId, stages: list[StageWithStageItems]
) -> None:
    tournament = await sql_get_tournament(tournament_id)
    courts = await get_all_courts_in_tournament(tournament_id)

    for op in build_schedule_plan(stages, courts, tournament):
        await sql_reschedule_match_and_determine_duration_and_margin(
            op.court_id,
            op.start_time,
            op.position,
            op.match,
            tournament,
        )


class MatchPosition(NamedTuple):
    match: MatchWithDetailsDefinitive | MatchWithDetails
    position: float


async def reorder_all_matches(
    tournament: Tournament,
    match_positions: list[MatchPosition],
) -> None:
    """
    Recompute start_time and position_in_schedule for all scheduled matches,
    honouring the user-specified ordering (match_positions[i].position).

    Each court is processed independently: matches are sorted by position and
    scheduled sequentially with no gaps. Cross-level interleaving is honoured;
    per-level stage-order violations are surfaced as warnings on the frontend.
    """
    if not match_positions:
        return

    court_matches: dict[CourtId, list[MatchPosition]] = defaultdict(list)
    for match_pos in match_positions:
        if match_pos.match.court_id is not None:
            court_matches[match_pos.match.court_id].append(match_pos)

    for court_id, matches in court_matches.items():
        current_time = tournament.start_time
        for position, match_pos in enumerate(sorted(matches, key=lambda mp: mp.position)):
            await sql_reschedule_match_and_determine_duration_and_margin(
                court_id,
                current_time,
                position,
                match_pos.match,
                tournament,
            )
            current_time += timedelta(
                minutes=match_pos.match.duration_minutes + match_pos.match.margin_minutes
            )


async def handle_match_reschedule(
    tournament: Tournament, body: MatchRescheduleBody, match_id: MatchId
) -> None:
    if body.old_court_id is None and body.old_position is not None:
        raise ValueError("old_court_id and old_position must both be set or both omitted")
    if body.old_position is None and body.old_court_id is not None:
        raise ValueError("old_court_id and old_position must both be set or both omitted")

    if (
        body.old_court_id is not None
        and body.old_position is not None
        and body.old_position == body.new_position
        and body.old_court_id == body.new_court_id
    ):
        return

    stages = await get_full_tournament_details(tournament.id)

    if body.old_court_id is None:
        all_matches = [
            MatchPosition(match=match, position=float(assert_some(match.position_in_schedule)))
            for stage in stages
            for stage_item in stage.stage_items
            for round_ in stage_item.rounds
            for match in round_.matches
            if match.start_time is not None and match.id != match_id
        ]
        target_match = next(
            match
            for stage in stages
            for stage_item in stage.stage_items
            for round_ in stage_item.rounds
            for match in round_.matches
            if match.id == match_id
        )
        if target_match.court_id is not None or target_match.start_time is not None:
            raise ValueError("match_id doesn't match unscheduled match state")

        offset = -0.5
        all_matches.append(
            MatchPosition(
                match=target_match.model_copy(update={"court_id": body.new_court_id}),
                position=body.new_position + offset,
            )
        )
        await reorder_all_matches(tournament, all_matches)
        return

    scheduled_matches_old = get_scheduled_matches(stages)

    # For match in prev position: set new position
    scheduled_matches = []
    for match_pos in scheduled_matches_old:
        if match_pos.match.id == match_id:
            if (
                match_pos.position != body.old_position
                or match_pos.match.court_id != body.old_court_id
            ):
                raise ValueError("match_id doesn't match court id or position in schedule")

            offset = (
                -0.5
                if body.new_position < body.old_position or body.new_court_id != body.old_court_id
                else +0.5
            )
            scheduled_matches.append(
                MatchPosition(
                    match=match_pos.match.model_copy(update={"court_id": body.new_court_id}),
                    position=body.new_position + offset,
                )
            )
        else:
            scheduled_matches.append(match_pos)

    await reorder_all_matches(tournament, scheduled_matches)


async def update_start_times_of_matches(tournament_id: TournamentId) -> None:
    stages = await get_full_tournament_details(tournament_id)
    tournament = await sql_get_tournament(tournament_id)
    scheduled_matches = get_scheduled_matches(stages)
    await reorder_all_matches(tournament, scheduled_matches)


def get_scheduled_matches(stages: list[StageWithStageItems]) -> list[MatchPosition]:
    return [
        MatchPosition(match=match, position=float(assert_some(match.position_in_schedule)))
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.start_time is not None
    ]


def get_scheduled_matches_per_court(
    stages: list[StageWithStageItems],
) -> dict[int, list[MatchPosition]]:
    scheduled_matches = get_scheduled_matches(stages)
    matches_per_court = defaultdict(list)

    for match_pos in scheduled_matches:
        if match_pos.match.court_id is not None:
            matches_per_court[match_pos.match.court_id].append(match_pos)

    return {
        court_id: sorted(matches, key=lambda mp: assert_some(mp.match.start_time))
        for court_id, matches in matches_per_court.items()
    }
