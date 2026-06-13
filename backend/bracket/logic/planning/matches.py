from collections import defaultdict
from dataclasses import dataclass
from typing import Any, NamedTuple

from fastapi import HTTPException
from heliclockter import datetime_utc, timedelta
from ortools.sat.python import cp_model
from starlette import status

from bracket.models.db.court import Court
from bracket.models.db.match import (
    Match,
    MatchRescheduleBody,
    MatchState,
    MatchSwapBody,
    MatchWithDetails,
    MatchWithDetailsDefinitive,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import StageWithStageItems
from bracket.sql.courts import get_all_courts_in_tournament
from bracket.sql.matches import (
    sql_reschedule_match_and_determine_duration,
    sql_unschedule_match,
)
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import CourtId, MatchId, StageItemId, StageItemInputId, TournamentId
from bracket.utils.logging import logger
from bracket.utils.types import assert_some


class ScheduleOperation(NamedTuple):
    court_id: CourtId
    start_time: datetime_utc
    position: int
    match: MatchWithDetails | MatchWithDetailsDefinitive


ScheduleMatch = MatchWithDetails | MatchWithDetailsDefinitive
SOLVER_TIME_LIMIT_SECONDS = 5.0
SOLVER_RANDOM_SEED = 77


@dataclass(frozen=True)
class _MatchContext:
    match: ScheduleMatch
    stage_item_id: StageItemId
    input_ids: tuple[StageItemInputId, ...]
    cross_stage_source_ids: tuple[StageItemId, ...]


@dataclass(frozen=True)
class _PinnedMatch:
    context: _MatchContext
    start_minutes: int
    end_minutes: int


def _minute_offset(tournament: Tournament, start_time: datetime_utc) -> int:
    return round((start_time - tournament.start_time).total_seconds() / 60)


def _is_pinned(context: _MatchContext) -> bool:
    return context.match.start_time is not None and context.match.court_id is not None


def _input_ids(match: ScheduleMatch) -> tuple[StageItemInputId, ...]:
    return tuple(
        input_id
        for input_id in (match.stage_item_input1_id, match.stage_item_input2_id)
        if input_id is not None
    )


def _cross_stage_source_ids(match: ScheduleMatch) -> tuple[StageItemId, ...]:
    source_ids = []
    for stage_item_input in (match.stage_item_input1, match.stage_item_input2):
        if stage_item_input is not None and stage_item_input.winner_from_stage_item_id is not None:
            source_ids.append(stage_item_input.winner_from_stage_item_id)
    return tuple(dict.fromkeys(source_ids))


def _get_match_contexts(stages: list[StageWithStageItems]) -> list[_MatchContext]:
    return [
        _MatchContext(
            match=match,
            stage_item_id=stage_item.id,
            input_ids=_input_ids(match),
            cross_stage_source_ids=_cross_stage_source_ids(match),
        )
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
    ]


def _planning_horizon_minutes(
    contexts: list[_MatchContext], tournament: Tournament, movable_contexts: list[_MatchContext]
) -> int:
    movable_minutes = sum(
        context.match.duration_minutes + tournament.margin_minutes for context in movable_contexts
    )
    latest_pinned_end = max(
        (
            max(
                0,
                _minute_offset(tournament, assert_some(context.match.start_time))
                + context.match.duration_minutes
                + tournament.margin_minutes,
            )
            for context in contexts
            if _is_pinned(context)
        ),
        default=0,
    )
    max_duration = max((context.match.duration_minutes for context in contexts), default=0)
    return max(
        1,
        latest_pinned_end + movable_minutes + tournament.margin_minutes + max_duration,
    )


def _pinned_matches_by_court(
    contexts: list[_MatchContext], tournament: Tournament
) -> dict[CourtId, list[_PinnedMatch]]:
    pinned_by_court: dict[CourtId, list[_PinnedMatch]] = defaultdict(list)
    for context in contexts:
        if not _is_pinned(context):
            continue
        start_minutes = _minute_offset(tournament, assert_some(context.match.start_time))
        pinned_by_court[assert_some(context.match.court_id)].append(
            _PinnedMatch(
                context=context,
                start_minutes=start_minutes,
                end_minutes=start_minutes + context.match.duration_minutes,
            )
        )
    return pinned_by_court


def _pinned_matches_by_input(
    contexts: list[_MatchContext], tournament: Tournament
) -> dict[StageItemInputId, list[_PinnedMatch]]:
    pinned_by_input: dict[StageItemInputId, list[_PinnedMatch]] = defaultdict(list)
    for context in contexts:
        if not _is_pinned(context):
            continue
        start_minutes = _minute_offset(tournament, assert_some(context.match.start_time))
        pinned = _PinnedMatch(
            context=context,
            start_minutes=start_minutes,
            end_minutes=start_minutes + context.match.duration_minutes,
        )
        for input_id in context.input_ids:
            pinned_by_input[input_id].append(pinned)
    return pinned_by_input


def _add_movable_match_variables(
    model: Any,
    movable_contexts: list[_MatchContext],
    courts: list[Court],
    tournament: Tournament,
    horizon: int,
) -> tuple[
    dict[MatchId, Any],
    dict[MatchId, Any],
    dict[MatchId, dict[CourtId, Any]],
    dict[CourtId, list[Any]],
    dict[StageItemInputId, list[Any]],
]:
    starts = {}
    ends = {}
    court_choices = {}
    court_intervals: dict[CourtId, list[Any]] = defaultdict(list)
    input_intervals: dict[StageItemInputId, list[Any]] = defaultdict(list)

    # Snap start times to the default match block (duration + break) rather than a fixed
    # 5-minute grid: this packs uniform-duration matches with zero gap waste while keeping
    # the search space discrete so the solve stays fast.
    block_minutes = max(1, tournament.duration_minutes + tournament.margin_minutes)

    for context in movable_contexts:
        match = context.match
        match_id = match.id
        start = model.NewIntVar(0, horizon, f"match_{match_id}_start")
        start_slot = model.NewIntVar(0, horizon // block_minutes + 1, f"match_{match_id}_start_slot")
        model.Add(start == start_slot * block_minutes)
        end = model.NewIntVar(0, horizon + match.duration_minutes, f"match_{match_id}_end")
        model.Add(end == start + match.duration_minutes)
        starts[match_id] = start
        ends[match_id] = end

        choices = {}
        for court in courts:
            chosen = model.NewBoolVar(f"match_{match_id}_on_court_{court.id}")
            choices[court.id] = chosen
            court_end = model.NewIntVar(
                0,
                horizon + match.duration_minutes + tournament.margin_minutes,
                f"match_{match_id}_court_{court.id}_end_with_break",
            )
            court_intervals[court.id].append(
                model.NewOptionalIntervalVar(
                    start,
                    match.duration_minutes + tournament.margin_minutes,
                    court_end,
                    chosen,
                    f"match_{match_id}_court_{court.id}_interval",
                )
            )
        model.AddExactlyOne(choices.values())
        court_choices[match_id] = choices

        for input_id in set(context.input_ids):
            input_end = model.NewIntVar(
                0,
                horizon + match.duration_minutes,
                f"match_{match_id}_input_{input_id}_end",
            )
            input_intervals[input_id].append(
                model.NewIntervalVar(
                    start,
                    match.duration_minutes,
                    input_end,
                    f"match_{match_id}_input_{input_id}_interval",
                )
            )

    return starts, ends, court_choices, court_intervals, input_intervals


def _add_no_overlap_constraints(
    model: Any,
    court_intervals: dict[CourtId, list[Any]],
    input_intervals: dict[StageItemInputId, list[Any]],
) -> None:
    for intervals in court_intervals.values():
        model.AddNoOverlap(intervals)
    for intervals in input_intervals.values():
        model.AddNoOverlap(intervals)


def _add_movable_vs_pinned_court_constraints(
    model: Any,
    movable_contexts: list[_MatchContext],
    starts: dict[MatchId, Any],
    ends: dict[MatchId, Any],
    court_choices: dict[MatchId, dict[CourtId, Any]],
    pinned_by_court: dict[CourtId, list[_PinnedMatch]],
    default_break_minutes: int,
) -> None:
    for context in movable_contexts:
        match_id = context.match.id
        for court_id, pinned_matches in pinned_by_court.items():
            chosen = court_choices[match_id].get(court_id)
            if chosen is None:
                continue
            for pinned in pinned_matches:
                before = model.NewBoolVar(
                    f"match_{match_id}_before_pinned_{pinned.context.match.id}_on_court_{court_id}"
                )
                after = model.NewBoolVar(
                    f"match_{match_id}_after_pinned_{pinned.context.match.id}_on_court_{court_id}"
                )
                model.Add(
                    ends[match_id] + default_break_minutes <= pinned.start_minutes
                ).OnlyEnforceIf([chosen, before])
                model.Add(
                    starts[match_id] >= pinned.end_minutes + default_break_minutes
                ).OnlyEnforceIf([chosen, after])
                model.AddBoolOr([before, after, chosen.Not()])


def _add_movable_vs_pinned_input_constraints(
    model: Any,
    movable_contexts: list[_MatchContext],
    starts: dict[MatchId, Any],
    ends: dict[MatchId, Any],
    pinned_by_input: dict[StageItemInputId, list[_PinnedMatch]],
) -> None:
    for context in movable_contexts:
        match_id = context.match.id
        pinned_match_ids = set()
        for input_id in context.input_ids:
            for pinned in pinned_by_input.get(input_id, []):
                if pinned.context.match.id in pinned_match_ids:
                    continue
                pinned_match_ids.add(pinned.context.match.id)
                before = model.NewBoolVar(
                    f"match_{match_id}_before_pinned_input_{pinned.context.match.id}"
                )
                after = model.NewBoolVar(
                    f"match_{match_id}_after_pinned_input_{pinned.context.match.id}"
                )
                model.Add(ends[match_id] <= pinned.start_minutes).OnlyEnforceIf(before)
                model.Add(starts[match_id] >= pinned.end_minutes).OnlyEnforceIf(after)
                model.AddBoolOr([before, after])


def _precedence_pairs(contexts: list[_MatchContext]) -> list[tuple[_MatchContext, _MatchContext]]:
    contexts_by_match_id = {context.match.id: context for context in contexts}
    contexts_by_stage_item: dict[StageItemId, list[_MatchContext]] = defaultdict(list)
    for context in contexts:
        contexts_by_stage_item[context.stage_item_id].append(context)

    pair_ids = set()
    for successor in contexts:
        for feeder_id in (
            successor.match.stage_item_input1_winner_from_match_id,
            successor.match.stage_item_input2_winner_from_match_id,
        ):
            if feeder_id is not None and feeder_id in contexts_by_match_id:
                pair_ids.add((feeder_id, successor.match.id))

        for source_stage_item_id in successor.cross_stage_source_ids:
            for feeder in contexts_by_stage_item[source_stage_item_id]:
                if feeder.match.id != successor.match.id:
                    pair_ids.add((feeder.match.id, successor.match.id))

    return [
        (contexts_by_match_id[feeder_id], contexts_by_match_id[successor_id])
        for feeder_id, successor_id in sorted(pair_ids)
    ]


def _add_precedence_constraints(
    model: Any,
    contexts: list[_MatchContext],
    tournament: Tournament,
    starts: dict[MatchId, Any],
    ends: dict[MatchId, Any],
    default_break_minutes: int,
) -> None:
    for feeder, successor in _precedence_pairs(contexts):
        feeder_pinned = _is_pinned(feeder)
        successor_pinned = _is_pinned(successor)
        if feeder_pinned and successor_pinned:
            continue

        if feeder_pinned:
            feeder_end = (
                _minute_offset(tournament, assert_some(feeder.match.start_time))
                + feeder.match.duration_minutes
            )
            model.Add(starts[successor.match.id] >= feeder_end + default_break_minutes)
            continue

        if successor_pinned:
            successor_start = _minute_offset(tournament, assert_some(successor.match.start_time))
            model.Add(ends[feeder.match.id] + default_break_minutes <= successor_start)
            continue

        model.Add(starts[successor.match.id] >= ends[feeder.match.id] + default_break_minutes)


def _build_operations_from_solution(
    solver: Any,
    movable_contexts: list[_MatchContext],
    pinned_contexts: list[_MatchContext],
    starts: dict[MatchId, Any],
    court_choices: dict[MatchId, dict[CourtId, Any]],
    tournament: Tournament,
) -> list[ScheduleOperation]:
    scheduled_slots: dict[CourtId, list[tuple[datetime_utc, MatchId, ScheduleOperation | None]]] = (
        defaultdict(list)
    )
    for context in movable_contexts:
        match_id = context.match.id
        court_id = next(
            court_id
            for court_id, chosen in court_choices[match_id].items()
            if solver.Value(chosen) == 1
        )
        start_time = tournament.start_time + timedelta(minutes=solver.Value(starts[match_id]))
        operation_to_schedule = ScheduleOperation(court_id, start_time, 0, context.match)
        scheduled_slots[court_id].append((start_time, match_id, operation_to_schedule))

    for context in pinned_contexts:
        scheduled_slots[assert_some(context.match.court_id)].append(
            (assert_some(context.match.start_time), context.match.id, None)
        )

    operations = []
    for slots in scheduled_slots.values():
        for position, (_, _, operation_for_position) in enumerate(sorted(slots)):
            if operation_for_position is not None:
                operations.append(
                    ScheduleOperation(
                        operation_for_position.court_id,
                        operation_for_position.start_time,
                        position,
                        operation_for_position.match,
                    )
                )

    return sorted(operations, key=lambda operation: (operation.start_time, operation.court_id))


def build_schedule_plan(
    stages: list[StageWithStageItems],
    courts: list[Court],
    tournament: Tournament,
) -> list[ScheduleOperation]:
    """
    Pure function: place every unscheduled match without introducing court, team, or
    dependency conflicts. Already scheduled matches are pinned at their current court/time.
    """
    if not stages or not courts:
        return []

    contexts = _get_match_contexts(stages)
    movable_contexts = [context for context in contexts if not _is_pinned(context)]
    if not movable_contexts:
        return []

    pinned_contexts = [context for context in contexts if _is_pinned(context)]
    horizon = _planning_horizon_minutes(contexts, tournament, movable_contexts)

    model = cp_model.CpModel()
    starts, ends, court_choices, court_intervals, input_intervals = _add_movable_match_variables(
        model,
        movable_contexts,
        courts,
        tournament,
        horizon,
    )
    _add_no_overlap_constraints(model, court_intervals, input_intervals)
    _add_movable_vs_pinned_court_constraints(
        model,
        movable_contexts,
        starts,
        ends,
        court_choices,
        _pinned_matches_by_court(contexts, tournament),
        tournament.margin_minutes,
    )
    _add_movable_vs_pinned_input_constraints(
        model,
        movable_contexts,
        starts,
        ends,
        _pinned_matches_by_input(contexts, tournament),
    )
    _add_precedence_constraints(
        model,
        contexts,
        tournament,
        starts,
        ends,
        tournament.margin_minutes,
    )

    makespan = model.NewIntVar(
        0,
        horizon + max(context.match.duration_minutes for context in contexts),
        "makespan",
    )
    for context in movable_contexts:
        model.Add(makespan >= ends[context.match.id])
    model.Minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    solver.parameters.random_seed = SOLVER_RANDOM_SEED
    solver.parameters.num_search_workers = 1
    status_code = solver.Solve(model)
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Never fail the request: the action must always succeed. Leave the unscheduled
        # matches as-is (placing nothing adds no new conflicts) so the organizer can retry.
        logger.warning(
            "Scheduler found no solution (status %s) for %d unscheduled matches; leaving them "
            "unscheduled",
            solver.StatusName(status_code),
            len(movable_contexts),
        )
        return []

    return _build_operations_from_solution(
        solver,
        movable_contexts,
        pinned_contexts,
        starts,
        court_choices,
        tournament,
    )


async def schedule_all_unscheduled_matches(
    tournament_id: TournamentId, stages: list[StageWithStageItems]
) -> None:
    tournament = await sql_get_tournament(tournament_id)
    courts = await get_all_courts_in_tournament(tournament_id)

    for op in build_schedule_plan(stages, courts, tournament):
        await sql_reschedule_match_and_determine_duration(
            op.court_id,
            op.start_time,
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
    Recompute start_time for scheduled matches, honouring the user-specified
    ordering (match_positions[i].position).

    Each court is processed independently: matches are sorted by transient
    position and existing gaps are preserved unless a match would overlap the
    previous occupied interval plus the tournament's default break.
    """
    if not match_positions:
        return

    court_matches: dict[CourtId, list[MatchPosition]] = defaultdict(list)
    for match_pos in match_positions:
        if match_pos.match.court_id is not None:
            court_matches[match_pos.match.court_id].append(match_pos)

    for court_id, matches in court_matches.items():
        previous_end: datetime_utc | None = None
        for match_pos in sorted(matches, key=lambda mp: mp.position):
            current_time = match_pos.match.start_time or tournament.start_time
            if previous_end is not None:
                earliest_start = previous_end + timedelta(minutes=tournament.margin_minutes)
                current_time = max(current_time, earliest_start)

            await sql_reschedule_match_and_determine_duration(
                court_id,
                current_time,
                match_pos.match,
                tournament,
            )
            previous_end = current_time + timedelta(minutes=match_pos.match.duration_minutes)


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
            # The client thought the match was unscheduled but someone scheduled it
            # in the meantime: reject so the client can refetch and retry.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The schedule changed since this device last refreshed: "
                "the match is no longer unscheduled",
            )

        # Only the destination court changes; other courts keep their packing.
        court_matches = [
            match_pos
            for match_pos in get_scheduled_matches(stages)
            if match_pos.match.court_id == body.new_court_id
        ]
        offset = -0.5
        court_matches.append(
            MatchPosition(
                match=target_match.model_copy(
                    update={"court_id": body.new_court_id, "start_time": None}
                ),
                position=body.new_position + offset,
            )
        )
        await reorder_all_matches(tournament, court_matches)
        return

    assert body.old_position is not None
    assert body.old_court_id is not None
    scheduled_matches_old = get_scheduled_matches(stages)

    target = next(
        (match_pos for match_pos in scheduled_matches_old if match_pos.match.id == match_id), None
    )
    if (
        target is None
        or target.position != body.old_position
        or target.match.court_id != body.old_court_id
    ):
        # Optimistic-concurrency check: the match moved since the client last
        # refreshed (e.g. a co-organizer rescheduled it from another device).
        # 409 lets the client distinguish this from a real error and recover by
        # refetching the schedule.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The schedule changed since this device last refreshed: "
            "the match is no longer at the given court and position",
        )

    offset = (
        -0.5
        if body.new_position < body.old_position or body.new_court_id != body.old_court_id
        else +0.5
    )

    # Only the source and destination courts change; other courts keep their packing.
    affected_court_ids = {body.old_court_id, body.new_court_id}
    scheduled_matches = [
        MatchPosition(
            match=match_pos.match.model_copy(
                update={"court_id": body.new_court_id, "start_time": None}
            ),
            position=body.new_position + offset,
        )
        if match_pos.match.id == match_id
        else match_pos
        for match_pos in scheduled_matches_old
        if match_pos.match.court_id in affected_court_ids
    ]

    await reorder_all_matches(tournament, scheduled_matches)


def validate_match_can_be_unscheduled(match: Match) -> None:
    if match.state is MatchState.NOT_STARTED:
        return

    state_label = "in progress" if match.state is MatchState.IN_PROGRESS else "completed"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Cannot move a {state_label} match back to Unscheduled. "
            "Only not started matches can be unscheduled."
        ),
    )


async def handle_match_swap(tournament: Tournament, body: MatchSwapBody) -> None:
    """
    Trade the schedule slots (court + position) of two matches atomically.

    Matches are identified by id, so the operation is robust against a stale client
    view: "swap A and B" means the same thing regardless of where A and B currently
    sit. An unscheduled match has no slot: swapping it with a scheduled one puts it
    in that match's slot and sends the scheduled match back to the tray.
    """
    if body.match1_id == body.match2_id:
        return

    stages = await get_full_tournament_details(tournament.id)
    scheduled_matches = get_scheduled_matches(stages)
    slots_by_id = {match_pos.match.id: match_pos for match_pos in scheduled_matches}

    slot1 = slots_by_id.get(body.match1_id)
    slot2 = slots_by_id.get(body.match2_id)

    if slot1 is None and slot2 is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of the matches must be scheduled to swap them",
        )

    if slot1 is not None and slot2 is not None:

        def swapped_position(match_pos: MatchPosition) -> MatchPosition:
            other = slot2 if match_pos.match.id == body.match1_id else slot1
            return MatchPosition(
                match=match_pos.match.model_copy(
                    update={
                        "court_id": other.match.court_id,
                        "start_time": other.match.start_time,
                    }
                ),
                position=other.position,
            )

        # Only the two slots' courts change; other courts keep their packing.
        affected_court_ids = {slot1.match.court_id, slot2.match.court_id}
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
        return

    # Mixed swap: the tray match takes over the scheduled match's slot, and the
    # scheduled match is sent back to the tray (only allowed when not started).
    vacated_slot = assert_some(slot1 if slot1 is not None else slot2)
    incoming_match_id = body.match2_id if slot1 is not None else body.match1_id
    incoming_match = next(
        match
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.id == incoming_match_id
    )
    validate_match_can_be_unscheduled(vacated_slot.match)

    court_matches = [
        MatchPosition(
            match=incoming_match.model_copy(
                update={
                    "court_id": vacated_slot.match.court_id,
                    "start_time": vacated_slot.match.start_time,
                }
            ),
            position=vacated_slot.position,
        )
        if match_pos.match.id == vacated_slot.match.id
        else match_pos
        for match_pos in scheduled_matches
        if match_pos.match.court_id == vacated_slot.match.court_id
    ]
    await sql_unschedule_match(vacated_slot.match.id)
    await reorder_all_matches(tournament, court_matches)


async def handle_match_resize_break(
    tournament: Tournament, match_id: MatchId, new_duration_minutes: int
) -> None:
    """
    Resize the break before ``match_id`` (the gap between the previous match's end
    and this match's start on the same court) to ``new_duration_minutes``.

    For the first match on a court the break is the delay between the tournament
    start and that match, so editing it delays the whole court's first match.

    The match and every later match on the court shift by the resulting delta, so
    their relative gaps are preserved; growing the break pushes them back, shrinking
    it pulls them forward. Earlier matches and every other court stay put.
    """
    stages = await get_full_tournament_details(tournament.id)
    matches_per_court = get_scheduled_matches_per_court(stages)

    for court_id, match_positions in matches_per_court.items():
        index = next((i for i, mp in enumerate(match_positions) if mp.match.id == match_id), None)
        if index is None:
            continue

        if index == 0:
            # The break before the first match is the delay between the tournament
            # start and that match; editing it shifts the whole court.
            previous_end = tournament.start_time
        else:
            previous = match_positions[index - 1].match
            previous_end = assert_some(previous.start_time) + timedelta(
                minutes=previous.duration_minutes
            )
        target = match_positions[index].match
        new_start = previous_end + timedelta(minutes=new_duration_minutes)
        delta = new_start - assert_some(target.start_time)
        if delta == timedelta():
            return

        for match_pos in match_positions[index:]:
            shifted_start = assert_some(match_pos.match.start_time) + delta
            await sql_reschedule_match_and_determine_duration(
                CourtId(court_id),
                shifted_start,
                match_pos.match,
                tournament,
            )
        return

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="The match is not currently scheduled on a court",
    )


async def update_start_times_of_matches(tournament_id: TournamentId) -> None:
    stages = await get_full_tournament_details(tournament_id)
    tournament = await sql_get_tournament(tournament_id)
    scheduled_matches = get_scheduled_matches(stages)
    await reorder_all_matches(tournament, scheduled_matches)


def get_scheduled_matches(stages: list[StageWithStageItems]) -> list[MatchPosition]:
    matches_by_court: dict[CourtId, list[MatchWithDetailsDefinitive | MatchWithDetails]] = (
        defaultdict(list)
    )
    for stage in stages:
        for stage_item in stage.stage_items:
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    if match.start_time is not None and match.court_id is not None:
                        matches_by_court[match.court_id].append(match)

    return [
        MatchPosition(match=match, position=float(position))
        for matches in matches_by_court.values()
        for position, match in enumerate(
            sorted(matches, key=lambda match: (assert_some(match.start_time), match.id))
        )
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
