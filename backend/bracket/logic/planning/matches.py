from collections import defaultdict
from dataclasses import dataclass
from typing import NamedTuple

from fastapi import HTTPException
from heliclockter import datetime_utc, timedelta
from starlette import status

from bracket.models.db.court import Court
from bracket.models.db.match import (
    MatchRescheduleBody,
    MatchSwapBody,
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


ScheduleMatch = MatchWithDetails | MatchWithDetailsDefinitive
TaggedMatch = tuple[LevelId | None, ScheduleMatch]
StageItemMatches = tuple[LevelId | None, list[ScheduleMatch]]


@dataclass
class _InterleaveState:
    level_id: LevelId | None
    remaining: list[ScheduleMatch]
    picks: int
    size: int
    rot_idx: int


def _assignment_load(stage_items: list[StageItemMatches]) -> int:
    return sum(len(matches) for _, matches in stage_items)


def _split_from_largest_stage_item(
    stage_items: list[StageItemMatches], match_count: int
) -> StageItemMatches:
    source_idx = max(range(len(stage_items)), key=lambda idx: len(stage_items[idx][1]))
    level_id, matches = stage_items[source_idx]
    if len(matches) <= match_count:
        return stage_items.pop(source_idx)

    split_at = len(matches) - match_count
    stage_items[source_idx] = (level_id, matches[:split_at])
    return level_id, matches[split_at:]


def _assign_stage_items_to_courts(
    stage_items: list[StageItemMatches], courts: list[Court]
) -> dict[CourtId, list[StageItemMatches]]:
    """Assign whole stage items to courts, splitting only to reach tight court loads."""
    court_ids = [court.id for court in courts]
    assignments: dict[CourtId, list[StageItemMatches]] = {court_id: [] for court_id in court_ids}
    if not court_ids:
        return assignments

    for stage_item in stage_items:
        court_id = min(court_ids, key=lambda candidate: _assignment_load(assignments[candidate]))
        assignments[court_id].append(stage_item)

    while True:
        max_court = max(court_ids, key=lambda court_id: _assignment_load(assignments[court_id]))
        min_court = min(court_ids, key=lambda court_id: _assignment_load(assignments[court_id]))
        max_load = _assignment_load(assignments[max_court])
        min_load = _assignment_load(assignments[min_court])
        if max_load - min_load <= 1:
            return assignments

        split_count = (max_load - min_load) // 2
        assignments[min_court].append(
            _split_from_largest_stage_item(assignments[max_court], split_count)
        )


def _weighted_interleave(
    stage_items: list[StageItemMatches], tiebreak_offset: int = 0
) -> list[TaggedMatch]:
    """
    Proportional-fair round-robin: at each step, pick the stage item with the smallest
    "progress" (picks_so_far / total_size). Larger SIs are picked more often because
    their target progress grows faster.

    Tiebreak: larger initial size first, then input order (rotated by `tiebreak_offset`
    so different courts can start with different SIs).

    Match order within each stage item is preserved, so round-dependencies are honored.
    """
    n = len(stage_items)
    state = [
        _InterleaveState(
            level_id=level_id,
            remaining=list(matches),
            picks=0,
            size=len(matches),
            rot_idx=(idx + tiebreak_offset) % n if n else 0,
        )
        for idx, (level_id, matches) in enumerate(stage_items)
    ]
    result: list[TaggedMatch] = []
    while any(s.remaining for s in state):
        active = [s for s in state if s.remaining]
        best = min(active, key=lambda s: (s.picks / s.size, -s.size, s.rot_idx))
        result.append((best.level_id, best.remaining.pop(0)))
        best.picks += 1
    return result


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

    Within each court, matches from different stage items are weighted-round-robin'd so
    larger stage items are picked more often, keeping all assigned stage items finishing
    around the same time.
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

        # Collect (level_id, ordered_matches) for each SI in active levels' current stage
        all_sis: list[StageItemMatches] = []
        for level_id in active_levels:
            stage = stages_by_level[level_id][level_stage_idx[level_id]]
            for stage_item in sorted(stage.stage_items, key=lambda si: si.name):
                matches = [
                    match
                    for round_ in sorted(stage_item.rounds, key=lambda r: r.id)
                    for match in round_.matches
                    if match.start_time is None and match.position_in_schedule is None
                ]
                if matches:
                    all_sis.append((level_id, matches))

        court_to_sis = _assign_stage_items_to_courts(all_sis, courts)

        # Track max end time per level across all courts for this scheduling round
        level_end_times: dict[LevelId | None, datetime_utc] = {}

        for court_idx, court_id in enumerate(court_ids):
            sequence = _weighted_interleave(court_to_sis[court_id], tiebreak_offset=court_idx)
            if not sequence:
                continue

            current_time = court_next_time[court_id]
            position = court_next_position[court_id]

            for level_id, match in sequence:
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

        # Only the destination court changes; other courts keep their packing.
        court_matches = [
            match_pos
            for match_pos in get_scheduled_matches(stages)
            if match_pos.match.court_id == body.new_court_id
        ]
        offset = -0.5
        court_matches.append(
            MatchPosition(
                match=target_match.model_copy(update={"court_id": body.new_court_id}),
                position=body.new_position + offset,
            )
        )
        await reorder_all_matches(tournament, court_matches)
        return

    scheduled_matches_old = get_scheduled_matches(stages)

    target = next(
        (match_pos for match_pos in scheduled_matches_old if match_pos.match.id == match_id), None
    )
    if (
        target is None
        or target.position != body.old_position
        or target.match.court_id != body.old_court_id
    ):
        raise ValueError("match_id doesn't match court id or position in schedule")

    offset = (
        -0.5
        if body.new_position < body.old_position or body.new_court_id != body.old_court_id
        else +0.5
    )

    # Only the source and destination courts change; other courts keep their packing.
    affected_court_ids = {body.old_court_id, body.new_court_id}
    scheduled_matches = [
        MatchPosition(
            match=match_pos.match.model_copy(update={"court_id": body.new_court_id}),
            position=body.new_position + offset,
        )
        if match_pos.match.id == match_id
        else match_pos
        for match_pos in scheduled_matches_old
        if match_pos.match.court_id in affected_court_ids
    ]

    await reorder_all_matches(tournament, scheduled_matches)


async def handle_match_swap(tournament: Tournament, body: MatchSwapBody) -> None:
    """
    Swap the schedule slots (court + position) of two scheduled matches atomically.

    Matches are identified by id, so the operation is robust against a stale client
    view: "swap A and B" means the same thing regardless of where A and B currently
    sit in the schedule.
    """
    if body.match1_id == body.match2_id:
        return

    stages = await get_full_tournament_details(tournament.id)
    scheduled_matches = get_scheduled_matches(stages)
    matches_by_id = {match_pos.match.id: match_pos for match_pos in scheduled_matches}

    match1 = matches_by_id.get(body.match1_id)
    match2 = matches_by_id.get(body.match2_id)
    if match1 is None or match2 is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both matches must be scheduled to swap them",
        )

    def swapped_position(match_pos: MatchPosition) -> MatchPosition:
        other = match2 if match_pos.match.id == body.match1_id else match1
        return MatchPosition(
            match=match_pos.match.model_copy(update={"court_id": other.match.court_id}),
            position=other.position,
        )

    # Only the two slots' courts change; other courts keep their packing.
    affected_court_ids = {match1.match.court_id, match2.match.court_id}
    await reorder_all_matches(
        tournament,
        [
            swapped_position(match_pos)
            if match_pos.match.id in (body.match1_id, body.match2_id)
            else match_pos
            for match_pos in scheduled_matches
            if match_pos.match.court_id in affected_court_ids
        ],
    )


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
