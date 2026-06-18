from collections import defaultdict
from dataclasses import dataclass
from typing import Any, NamedTuple

from fastapi import HTTPException
from heliclockter import datetime_utc, timedelta
from ortools.sat.python import cp_model
from starlette import status

from bracket.config import currently_testing
from bracket.models.db.court import Court
from bracket.models.db.match import (
    Match,
    MatchRescheduleBody,
    MatchState,
    MatchSwapBody,
    MatchWithDetails,
    MatchWithDetailsDefinitive,
    SchedulerWeights,
)
from bracket.models.db.stage_item_inputs import StageItemInputEmpty, StageItemInputFinal
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import StageItemWithRounds, StageWithStageItems
from bracket.sql.courts import get_all_courts_in_tournament
from bracket.sql.matches import (
    sql_reschedule_match_and_determine_duration,
    sql_unschedule_match,
)
from bracket.sql.referees import sql_set_match_referee_slot
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import (
    CourtId,
    LevelId,
    MatchId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)
from bracket.utils.logging import logger
from bracket.utils.types import assert_some


class ScheduleOperation(NamedTuple):
    court_id: CourtId
    start_time: datetime_utc
    position: int
    match: MatchWithDetails | MatchWithDetailsDefinitive
    referee_stage_item_input_id: StageItemInputId | None = None


ScheduleMatch = MatchWithDetails | MatchWithDetailsDefinitive
SOLVER_TIME_LIMIT_SECONDS = 5.0
SOLVER_RANDOM_SEED = 77  # Applied only under tests (see currently_testing); prod runs unseeded.
SOLVER_SEARCH_WORKERS = 4

# Objective blend (PRD #73, issue #78). The schedule minimises a single weighted sum.
# Makespan is the headline term; team rest keeps a player from going straight from one
# match into the next; court locality keeps a group on few courts; group sync keeps the
# stage items of a stage finishing each round at a similar time. The weights and the
# comfortable-rest threshold default to the empirically tuned constants on SchedulerWeights
# but are passed in per request, so an organizer can retune the balance for a tournament
# whose default schedule feels off (e.g. on the dev-db seed) without touching code.
DEFAULT_SCHEDULER_WEIGHTS = SchedulerWeights()


@dataclass(frozen=True)
class _MatchContext:
    match: ScheduleMatch
    level_id: LevelId | None
    stage_id: StageId
    stage_item_id: StageItemId
    round_index: int
    input_ids: tuple[StageItemInputId, ...]
    cross_stage_source_ids: tuple[StageItemId, ...]
    # True when the match's stage item has at least one unwired (empty) input slot, e.g. a
    # knockout place filled manually only once the previous stage is fully played.
    stage_item_has_open_slot: bool


@dataclass(frozen=True)
class _PinnedMatch:
    context: _MatchContext
    start_minutes: int
    end_minutes: int


def _minute_offset(tournament: Tournament, start_time: datetime_utc) -> int:
    return round((start_time - tournament.start_time).total_seconds() / 60)


def _is_scheduled(context: _MatchContext) -> bool:
    return context.match.start_time is not None and context.match.court_id is not None


def _pinned_match_ids(contexts: list[_MatchContext], reoptimize: bool) -> frozenset[MatchId]:
    """IDs of matches held fixed at their current court/time during the solve.

    In the default mode every scheduled match is pinned, so "Schedule unscheduled matches"
    only ever places matches that have no slot yet. In re-optimize mode only in-progress and
    completed matches are pinned, so every not-started match — including manually placed ones
    and manually adjusted breaks around them — is free to be re-flowed by the solver.
    """
    pinned = set()
    for context in contexts:
        if not _is_scheduled(context):
            continue
        if reoptimize and context.match.state not in (
            MatchState.IN_PROGRESS,
            MatchState.COMPLETED,
        ):
            continue
        pinned.add(context.match.id)
    return frozenset(pinned)


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


def _has_open_slot(stage_item: StageItemWithRounds) -> bool:
    return any(isinstance(input_, StageItemInputEmpty) for input_ in stage_item.inputs)


def _referee_candidate_slots_by_level(
    stages: list[StageWithStageItems],
) -> dict[LevelId | None, list[tuple[StageItemInputId, TeamId | None]]]:
    """Candidate referee slots per level: ``(stage_item_input_id, resolved_team_id_or_None)``.

    A referee is just a third match slot, so any stage-item input at the match's level can
    referee. Resolved (Final) slots are deduplicated to one per team (lowest id) so referee load
    balances per team; unresolved (tentative/empty) slots are each offered as a fallback so the
    optimizer can pick "whoever ends up in this position" when no concrete team is free.
    """
    by_level: dict[LevelId | None, list[tuple[StageItemInputId, TeamId | None]]] = defaultdict(list)
    resolved: dict[LevelId | None, dict[TeamId, StageItemInputId]] = defaultdict(dict)
    for stage in stages:
        for stage_item in stage.stage_items:
            for input_ in stage_item.inputs:
                if isinstance(input_, StageItemInputFinal):
                    existing = resolved[stage.level_id].get(input_.team_id)
                    if existing is None or input_.id < existing:
                        resolved[stage.level_id][input_.team_id] = input_.id
                else:
                    by_level[stage.level_id].append((input_.id, None))
    for level_id, team_slots in resolved.items():
        for team_id, slot_id in team_slots.items():
            by_level[level_id].append((slot_id, team_id))
    return by_level


def _get_match_contexts(stages: list[StageWithStageItems]) -> list[_MatchContext]:
    return [
        _MatchContext(
            match=match,
            level_id=stage.level_id,
            stage_id=stage.id,
            stage_item_id=stage_item.id,
            round_index=round_index,
            input_ids=_input_ids(match),
            cross_stage_source_ids=_cross_stage_source_ids(match),
            stage_item_has_open_slot=_has_open_slot(stage_item),
        )
        for stage in stages
        for stage_item in stage.stage_items
        for round_index, round_ in enumerate(stage_item.rounds)
        for match in round_.matches
    ]


def _planning_horizon_minutes(
    contexts: list[_MatchContext],
    tournament: Tournament,
    movable_contexts: list[_MatchContext],
    pinned_ids: frozenset[MatchId],
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
            if context.match.id in pinned_ids
        ),
        default=0,
    )
    max_duration = max((context.match.duration_minutes for context in contexts), default=0)
    return max(
        1,
        latest_pinned_end + movable_minutes + tournament.margin_minutes + max_duration,
    )


def _pinned_matches_by_court(
    contexts: list[_MatchContext], tournament: Tournament, pinned_ids: frozenset[MatchId]
) -> dict[CourtId, list[_PinnedMatch]]:
    pinned_by_court: dict[CourtId, list[_PinnedMatch]] = defaultdict(list)
    for context in contexts:
        if context.match.id not in pinned_ids:
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
    contexts: list[_MatchContext], tournament: Tournament, pinned_ids: frozenset[MatchId]
) -> dict[StageItemInputId, list[_PinnedMatch]]:
    pinned_by_input: dict[StageItemInputId, list[_PinnedMatch]] = defaultdict(list)
    for context in contexts:
        if context.match.id not in pinned_ids:
            continue
        start_minutes = _minute_offset(tournament, assert_some(context.match.start_time))
        pinned = _PinnedMatch(
            context=context,
            start_minutes=start_minutes,
            end_minutes=start_minutes + context.match.duration_minutes,
        )
        # A pinned match occupies all three of its slots for its whole window: the two playing
        # inputs and (if set) its referee slot. Treating the referee slot the same way lets a
        # movable match's referee/playing choice avoid colliding with a pinned occupant.
        referee_slot_id = context.match.referee_stage_item_input_id
        slot_ids = (
            (*context.input_ids, referee_slot_id)
            if referee_slot_id is not None
            else context.input_ids
        )
        for input_id in slot_ids:
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
        start_slot = model.NewIntVar(
            0, horizon // block_minutes + 1, f"match_{match_id}_start_slot"
        )
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


def _open_slot_precedence_ids(contexts: list[_MatchContext]) -> set[tuple[MatchId, MatchId]]:
    """Pair each open-slot stage item's matches with its whole immediately-preceding stage.

    A stage item with an unwired input slot has no explicit feeder to follow, but it still
    cannot be played before the stage that fills that slot is over. Lacking a specific
    source, we conservatively make every match of such a stage item wait for every match of
    the immediately-preceding stage in the same level. Cross-level scheduling is unaffected,
    and fully-wired stage items keep their tighter, feeder-specific dependencies.
    """
    contexts_by_stage: dict[StageId, list[_MatchContext]] = defaultdict(list)
    stages_by_level: dict[LevelId | None, set[StageId]] = defaultdict(set)
    for context in contexts:
        contexts_by_stage[context.stage_id].append(context)
        stages_by_level[context.level_id].add(context.stage_id)

    ordered_stages_by_level = {
        level_id: sorted(stage_ids) for level_id, stage_ids in stages_by_level.items()
    }

    pair_ids = set()
    for successor in contexts:
        if not successor.stage_item_has_open_slot:
            continue
        ordered_stages = ordered_stages_by_level[successor.level_id]
        position = ordered_stages.index(successor.stage_id)
        if position == 0:
            continue  # first stage in the level — nothing precedes it
        preceding_stage_id = ordered_stages[position - 1]
        for feeder in contexts_by_stage[preceding_stage_id]:
            pair_ids.add((feeder.match.id, successor.match.id))
    return pair_ids


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

    pair_ids |= _open_slot_precedence_ids(contexts)

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
    pinned_ids: frozenset[MatchId],
) -> None:
    for feeder, successor in _precedence_pairs(contexts):
        feeder_pinned = feeder.match.id in pinned_ids
        successor_pinned = successor.match.id in pinned_ids
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


def _add_team_rest_penalty(
    model: Any,
    movable_contexts: list[_MatchContext],
    starts: dict[MatchId, Any],
    ends: dict[MatchId, Any],
    horizon: int,
    comfortable_rest_minutes: int,
) -> list[Any]:
    """Penalise how far each team's consecutive matches fall short of a comfortable rest.

    For every pair of a team's movable matches the gap between them (later start minus
    earlier end) is known to be non-negative because they already cannot overlap. The
    shortfall ``max(0, comfortable_rest_minutes - gap)`` is summed and minimised, so the
    solver spreads a team's matches whenever doing so is cheap on the headline terms.
    """
    matches_by_input: dict[StageItemInputId, list[MatchId]] = defaultdict(list)
    for context in movable_contexts:
        for input_id in set(context.input_ids):
            matches_by_input[input_id].append(context.match.id)

    shortfalls = []
    for match_ids in matches_by_input.values():
        for index, first_id in enumerate(match_ids):
            for second_id in match_ids[index + 1 :]:
                gap = model.NewIntVar(-horizon, horizon, f"rest_gap_{first_id}_{second_id}")
                model.AddMaxEquality(
                    gap,
                    [starts[second_id] - ends[first_id], starts[first_id] - ends[second_id]],
                )
                shortfall = model.NewIntVar(
                    0, comfortable_rest_minutes, f"rest_shortfall_{first_id}_{second_id}"
                )
                model.Add(shortfall >= comfortable_rest_minutes - gap)
                shortfalls.append(shortfall)
    return shortfalls


def _add_court_locality_penalty(
    model: Any,
    movable_contexts: list[_MatchContext],
    court_choices: dict[MatchId, dict[CourtId, Any]],
) -> list[Any]:
    """Penalise the number of distinct courts each stage item (group/bracket) spreads over.

    For every (stage item, court) pair a boolean is forced on when any of the item's
    matches is placed on that court, and the sum of those booleans is minimised. A group
    that fits on one court without hurting the headline terms therefore stays put.
    """
    matches_by_item: dict[StageItemId, list[MatchId]] = defaultdict(list)
    for context in movable_contexts:
        matches_by_item[context.stage_item_id].append(context.match.id)

    used_court_vars = []
    for stage_item_id, match_ids in matches_by_item.items():
        courts_in_item = {
            court_id for match_id in match_ids for court_id in court_choices[match_id]
        }
        for court_id in courts_in_item:
            used = model.NewBoolVar(f"item_{stage_item_id}_uses_court_{court_id}")
            for match_id in match_ids:
                model.Add(used >= court_choices[match_id][court_id])
            used_court_vars.append(used)
    return used_court_vars


def _add_group_sync_penalty(
    model: Any,
    movable_contexts: list[_MatchContext],
    ends: dict[MatchId, Any],
    horizon: int,
) -> list[Any]:
    """Penalise divergence in round progress across the stage items of a stage.

    Round progress is keyed by (stage, round index): for each round index present in at
    least two of a stage's items, the spread between the earliest- and latest-finishing
    item at that round is minimised. Keying on the round index (rather than assuming equal
    round counts) keeps the term well-defined when stage items have different numbers of
    rounds — items simply stop contributing once their rounds run out.
    """
    ends_by_stage_round_item: dict[tuple[StageId, int], dict[StageItemId, list[Any]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for context in movable_contexts:
        key = (context.stage_id, context.round_index)
        ends_by_stage_round_item[key][context.stage_item_id].append(ends[context.match.id])

    spreads = []
    for (stage_id, round_index), ends_by_item in ends_by_stage_round_item.items():
        if len(ends_by_item) < 2:
            continue
        item_round_ends = []
        for stage_item_id, match_ends in ends_by_item.items():
            round_end = model.NewIntVar(
                0, horizon, f"round_end_stage_{stage_id}_round_{round_index}_item_{stage_item_id}"
            )
            model.AddMaxEquality(round_end, match_ends)
            item_round_ends.append(round_end)

        latest = model.NewIntVar(0, horizon, f"round_latest_stage_{stage_id}_round_{round_index}")
        earliest = model.NewIntVar(
            0, horizon, f"round_earliest_stage_{stage_id}_round_{round_index}"
        )
        model.AddMaxEquality(latest, item_round_ends)
        model.AddMinEquality(earliest, item_round_ends)
        spread = model.NewIntVar(0, horizon, f"round_spread_stage_{stage_id}_round_{round_index}")
        model.Add(spread == latest - earliest)
        spreads.append(spread)
    return spreads


def _add_referee_slot_occupancy(
    model: Any,
    slot_id: StageItemInputId,
    match_id: MatchId,
    duration: int,
    enforce: Any | None,
    starts: dict[MatchId, Any],
    ends: dict[MatchId, Any],
    horizon: int,
    input_intervals: dict[StageItemInputId, list[Any]],
    pinned_by_input: dict[StageItemInputId, list[_PinnedMatch]],
) -> None:
    """Mark a slot occupied for a match's window as its referee.

    The interval joins the slot's own no-overlap list (shared with its playing intervals); since
    pinned matches contribute fixed intervals that are not in that list, the slot is also
    constrained against pinned occupants explicitly. ``enforce=None`` is an unconditional
    occupancy (a preserved assignment); otherwise the occupancy holds only when ``enforce`` is set.
    """
    ref_end = model.NewIntVar(0, horizon + duration, f"ref_end_m{match_id}_s{slot_id}")
    name = f"ref_iv_m{match_id}_s{slot_id}"
    if enforce is None:
        input_intervals[slot_id].append(
            model.NewIntervalVar(starts[match_id], duration, ref_end, name)
        )
    else:
        input_intervals[slot_id].append(
            model.NewOptionalIntervalVar(starts[match_id], duration, ref_end, enforce, name)
        )

    for pinned in pinned_by_input.get(slot_id, []):
        before = model.NewBoolVar(f"ref_m{match_id}_s{slot_id}_before_{pinned.context.match.id}")
        after = model.NewBoolVar(f"ref_m{match_id}_s{slot_id}_after_{pinned.context.match.id}")
        before_guard = [before] if enforce is None else [enforce, before]
        after_guard = [after] if enforce is None else [enforce, after]
        model.Add(ends[match_id] <= pinned.start_minutes).OnlyEnforceIf(before_guard)
        model.Add(starts[match_id] >= pinned.end_minutes).OnlyEnforceIf(after_guard)
        model.AddBoolOr([before, after] if enforce is None else [before, after, enforce.Not()])


def _referee_fairness_spread(
    model: Any, resolved_choice_vars: dict[StageItemInputId, list[Any]], max_possible: int
) -> list[Any]:
    """Min-max spread of per-resolved-slot referee load (one slot per team, so per team)."""
    if len(resolved_choice_vars) < 2:
        return []
    loads: list[Any] = []
    for slot_id in sorted(resolved_choice_vars):  # sorted for determinism
        choice_vars = resolved_choice_vars[slot_id]
        load = model.NewIntVar(0, len(choice_vars), f"ref_load_s{slot_id}")
        model.Add(load == sum(choice_vars))
        loads.append(load)
    max_load = model.NewIntVar(0, max_possible, "ref_max_load")
    min_load = model.NewIntVar(0, max_possible, "ref_min_load")
    model.AddMaxEquality(max_load, loads)
    model.AddMinEquality(min_load, loads)
    spread = model.NewIntVar(0, max_possible, "ref_spread")
    model.Add(spread == max_load - min_load)
    return [spread]


def _add_referee_assignment(
    model: Any,
    movable_contexts: list[_MatchContext],
    starts: dict[MatchId, Any],
    ends: dict[MatchId, Any],
    input_intervals: dict[StageItemInputId, list[Any]],
    pinned_by_input: dict[StageItemInputId, list[_PinnedMatch]],
    candidate_slots_by_level: dict[LevelId | None, list[tuple[StageItemInputId, TeamId | None]]],
    horizon: int,
    reoptimize: bool = False,
) -> tuple[dict[MatchId, dict[StageItemInputId, Any]], list[Any], list[Any]]:
    """Assign each movable match a referee slot, treating it as a third match slot.

    The chosen referee occupies a ``stage_item_input`` for the match's duration via the very same
    per-input ``AddNoOverlap`` used for the two playing slots, so a slot cannot play and referee
    (nor referee twice) at overlapping times — no referee-specific overlap bookkeeping.

    Resolved (team) slots are preferred via ``unresolved_vars`` (penalised in the objective);
    unresolved (tentative/empty) slots are a fallback. Under ``reoptimize`` existing assignments
    are reshuffled; otherwise a match keeps its referee (its slot interval is still added so the
    no-overlap holds as the match re-flows).

    Returns ``(ref_choices, fairness_spreads, unresolved_vars)`` where
    ``ref_choices[match_id][slot_id]`` is the BoolVar for "that slot referees that match".
    """
    ref_choices: dict[MatchId, dict[StageItemInputId, Any]] = {}
    resolved_choice_vars: dict[StageItemInputId, list[Any]] = defaultdict(list)
    unresolved_vars: list[Any] = []

    for context in movable_contexts:
        match = context.match
        match_id = match.id
        duration = match.duration_minutes
        own = set(context.input_ids)

        keep_existing = (
            match.referee_stage_item_input_id is not None or match.referee_name is not None
        ) and not reoptimize
        if keep_existing:
            # Preserve the assignment; a slot-based referee still occupies its slot (a free-text
            # referee occupies none) so the no-overlap stays valid as the match re-flows.
            slot_id = match.referee_stage_item_input_id
            if slot_id is not None:
                _add_referee_slot_occupancy(
                    model,
                    slot_id,
                    match_id,
                    duration,
                    None,
                    starts,
                    ends,
                    horizon,
                    input_intervals,
                    pinned_by_input,
                )
            continue

        candidates = [
            (slot_id, team_id)
            for slot_id, team_id in candidate_slots_by_level.get(context.level_id, [])
            if slot_id not in own
        ]
        if not candidates:
            continue

        choices: dict[StageItemInputId, Any] = {}
        for slot_id, team_id in sorted(candidates, key=lambda candidate: candidate[0]):
            var = model.NewBoolVar(f"ref_m{match_id}_s{slot_id}")
            choices[slot_id] = var
            _add_referee_slot_occupancy(
                model,
                slot_id,
                match_id,
                duration,
                var,
                starts,
                ends,
                horizon,
                input_intervals,
                pinned_by_input,
            )
            if team_id is not None:
                resolved_choice_vars[slot_id].append(var)
            else:
                unresolved_vars.append(var)
        model.AddExactlyOne(choices.values())
        ref_choices[match_id] = choices

    spreads = _referee_fairness_spread(model, resolved_choice_vars, len(movable_contexts))
    return ref_choices, spreads, unresolved_vars


def _build_operations_from_solution(
    solver: Any,
    movable_contexts: list[_MatchContext],
    pinned_contexts: list[_MatchContext],
    starts: dict[MatchId, Any],
    court_choices: dict[MatchId, dict[CourtId, Any]],
    ref_choices: dict[MatchId, dict[StageItemInputId, Any]],
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
        referee_slot_id: StageItemInputId | None = None
        if match_id in ref_choices:
            referee_slot_id = next(
                (
                    slot_id
                    for slot_id, var in ref_choices[match_id].items()
                    if solver.Value(var) == 1
                ),
                None,
            )
        operation_to_schedule = ScheduleOperation(
            court_id, start_time, 0, context.match, referee_slot_id
        )
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
                        operation_for_position.referee_stage_item_input_id,
                    )
                )

    return sorted(operations, key=lambda operation: (operation.start_time, operation.court_id))


def build_schedule_plan(
    stages: list[StageWithStageItems],
    courts: list[Court],
    tournament: Tournament,
    reoptimize: bool = False,
    weights: SchedulerWeights = DEFAULT_SCHEDULER_WEIGHTS,
) -> list[ScheduleOperation]:
    """
    Pure function: place movable matches without introducing court, team, or dependency
    conflicts. With ``reoptimize`` false every scheduled match is pinned and only matches
    without a slot are placed; with ``reoptimize`` true only in-progress and completed
    matches are pinned, so every not-started match is re-flowed around them. ``weights``
    tunes the objective blend (makespan, team rest, court locality, group sync).
    """
    if not stages or not courts:
        return []

    contexts = _get_match_contexts(stages)
    pinned_ids = _pinned_match_ids(contexts, reoptimize)
    movable_contexts = [context for context in contexts if context.match.id not in pinned_ids]
    if not movable_contexts:
        return []

    pinned_contexts = [context for context in contexts if context.match.id in pinned_ids]
    horizon = _planning_horizon_minutes(contexts, tournament, movable_contexts, pinned_ids)

    model = cp_model.CpModel()
    starts, ends, court_choices, court_intervals, input_intervals = _add_movable_match_variables(
        model,
        movable_contexts,
        courts,
        tournament,
        horizon,
    )
    pinned_by_input = _pinned_matches_by_input(contexts, tournament, pinned_ids)

    # Referee assignment treats the referee as a third match slot: it appends the chosen
    # referee's interval to that stage_item_input's interval list, so it must run before the
    # per-input no-overlap below — which then covers playing and refereeing uniformly.
    ref_choices: dict[MatchId, dict[StageItemInputId, Any]] = {}
    ref_spreads: list[Any] = []
    unresolved_referee_vars: list[Any] = []
    if tournament.referees_enabled:
        ref_choices, ref_spreads, unresolved_referee_vars = _add_referee_assignment(
            model,
            movable_contexts,
            starts,
            ends,
            input_intervals,
            pinned_by_input,
            _referee_candidate_slots_by_level(stages),
            horizon,
            reoptimize,
        )

    _add_no_overlap_constraints(model, court_intervals, input_intervals)
    _add_movable_vs_pinned_court_constraints(
        model,
        movable_contexts,
        starts,
        ends,
        court_choices,
        _pinned_matches_by_court(contexts, tournament, pinned_ids),
        tournament.margin_minutes,
    )
    _add_movable_vs_pinned_input_constraints(
        model,
        movable_contexts,
        starts,
        ends,
        pinned_by_input,
    )
    _add_precedence_constraints(
        model,
        contexts,
        tournament,
        starts,
        ends,
        tournament.margin_minutes,
        pinned_ids,
    )

    makespan = model.NewIntVar(
        0,
        horizon + max(context.match.duration_minutes for context in contexts),
        "makespan",
    )
    for context in movable_contexts:
        model.Add(makespan >= ends[context.match.id])

    objective = weights.makespan * makespan
    rest_shortfalls = _add_team_rest_penalty(
        model, movable_contexts, starts, ends, horizon, weights.comfortable_rest_minutes
    )
    if rest_shortfalls:
        objective += weights.team_rest * sum(rest_shortfalls)
    used_court_vars = _add_court_locality_penalty(model, movable_contexts, court_choices)
    if used_court_vars:
        objective += weights.court_locality * sum(used_court_vars)
    sync_spreads = _add_group_sync_penalty(model, movable_contexts, ends, horizon)
    if sync_spreads:
        objective += weights.group_sync * sum(sync_spreads)

    if ref_spreads and weights.referee_fairness > 0:
        objective += weights.referee_fairness * sum(ref_spreads)
    if unresolved_referee_vars:
        # Prefer a concrete (resolved) referee over an unresolved slot ("winner of ...") whenever
        # one is free: this penalty per unresolved pick dominates the per-pick fairness swing, so
        # balancing never trades a real referee for a placeholder.
        objective += (weights.referee_fairness + 1) * sum(unresolved_referee_vars)

    model.Minimize(objective)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    if currently_testing():
        # Pin the seed only under tests, for reproducible runs. In production a fixed seed
        # would bake the same pseudo-random tie-breaking into every tournament's schedule.
        solver.parameters.random_seed = SOLVER_RANDOM_SEED
    # Use CP-SAT's parallel portfolio search. With a single worker the solver explores far
    # too little within the few-second wall limit on realistic fixtures and returns a poor
    # feasible solution (matches crammed onto one court, others left idle); the makespan
    # objective never gets a chance to matter. Multiple workers find a near-optimal layout
    # in the same wall time. (Auto/0 segfaults with this ortools build, so pin a count.)
    solver.parameters.num_search_workers = SOLVER_SEARCH_WORKERS
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
        ref_choices,
        tournament,
    )


async def _apply_schedule_plan(
    tournament_id: TournamentId,
    stages: list[StageWithStageItems],
    *,
    reoptimize: bool,
    weights: SchedulerWeights,
) -> None:
    tournament = await sql_get_tournament(tournament_id)
    courts = await get_all_courts_in_tournament(tournament_id)

    for op in build_schedule_plan(
        stages, courts, tournament, reoptimize=reoptimize, weights=weights
    ):
        await sql_reschedule_match_and_determine_duration(
            op.court_id,
            op.start_time,
            op.match,
            tournament,
        )
        if op.referee_stage_item_input_id is not None:
            await sql_set_match_referee_slot(op.match.id, op.referee_stage_item_input_id)


def build_referee_assignment_plan(
    stages: list[StageWithStageItems],
    tournament: Tournament,
    weights: SchedulerWeights = DEFAULT_SCHEDULER_WEIGHTS,
) -> dict[MatchId, StageItemInputId]:
    """Assign referees to already-scheduled matches that have none, without moving any match.

    Returns a mapping of match_id → referee stage_item_input_id for each match that received a
    new referee. Matches that already have a referee (slot or free-text name), unscheduled
    matches, and matches with no eligible candidate are left untouched. Never fails — returns
    what it can.
    """
    if not tournament.referees_enabled:
        return {}

    contexts = _get_match_contexts(stages)
    candidate_slots_by_level = _referee_candidate_slots_by_level(stages)

    # Only scheduled matches (fixed court + start_time) participate.
    scheduled_contexts = [c for c in contexts if _is_scheduled(c)]
    if not scheduled_contexts:
        return {}

    # Treat all three slots the same: a stage_item_input is "busy" in a window when it plays (one
    # of the two playing slots) or referees an existing assignment. A candidate referee slot must
    # be free for the match's window, whether it resolves to a team or is still a placeholder.
    slot_busy: dict[StageItemInputId, list[tuple[int, int]]] = defaultdict(list)
    for context in scheduled_contexts:
        start_min = _minute_offset(tournament, assert_some(context.match.start_time))
        end_min = start_min + context.match.duration_minutes
        for input_id in context.input_ids:
            slot_busy[input_id].append((start_min, end_min))
        referee_slot_id = context.match.referee_stage_item_input_id
        if referee_slot_id is not None:
            slot_busy[referee_slot_id].append((start_min, end_min))

    def _has_referee(context: _MatchContext) -> bool:
        return (
            context.match.referee_stage_item_input_id is not None
            or context.match.referee_name is not None
        )

    def _overlaps(start: int, end: int, busy: list[tuple[int, int]]) -> bool:
        return any(start < b_end and b_start < end for b_start, b_end in busy)

    needs_ref = [c for c in scheduled_contexts if not _has_referee(c)]
    if not needs_ref:
        return {}

    model = cp_model.CpModel()
    ref_choices: dict[MatchId, dict[StageItemInputId, Any]] = {}
    match_windows: dict[MatchId, tuple[int, int]] = {}
    resolved_choice_vars: dict[StageItemInputId, list[Any]] = defaultdict(list)
    unresolved_vars: list[Any] = []

    for context in needs_ref:
        match = context.match
        start_min = _minute_offset(tournament, assert_some(match.start_time))
        end_min = start_min + match.duration_minutes
        match_windows[match.id] = (start_min, end_min)
        own = set(context.input_ids)

        choices: dict[StageItemInputId, Any] = {}
        for slot_id, team_id in sorted(
            candidate_slots_by_level.get(context.level_id, []), key=lambda candidate: candidate[0]
        ):
            if slot_id in own or _overlaps(start_min, end_min, slot_busy.get(slot_id, [])):
                continue
            var = model.NewBoolVar(f"ref_m{match.id}_s{slot_id}")
            choices[slot_id] = var
            if team_id is not None:
                resolved_choice_vars[slot_id].append(var)
            else:
                unresolved_vars.append(var)

        if choices:
            model.AddAtMostOne(choices.values())
            ref_choices[match.id] = choices

    if not ref_choices:
        return {}

    # A slot cannot referee two overlapping newly-assigned matches.
    sorted_match_ids = sorted(ref_choices.keys())
    for i, mid1 in enumerate(sorted_match_ids):
        for mid2 in sorted_match_ids[i + 1 :]:
            s1, e1 = match_windows[mid1]
            s2, e2 = match_windows[mid2]
            if s1 < e2 and s2 < e1:
                for slot_id in set(ref_choices[mid1]) & set(ref_choices[mid2]):
                    model.AddBoolOr(
                        [ref_choices[mid1][slot_id].Not(), ref_choices[mid2][slot_id].Not()]
                    )

    # Count existing resolved-referee assignments toward the fairness balance.
    fixed_load: dict[StageItemInputId, int] = defaultdict(int)
    for context in scheduled_contexts:
        existing_slot_id = context.match.referee_stage_item_input_id
        if existing_slot_id is not None and existing_slot_id in resolved_choice_vars:
            fixed_load[existing_slot_id] += 1

    # Objective, in order of dominance:
    #   1. coverage         — assign as many matches as possible
    #   2. prefer resolved  — only fall back to an unresolved slot when no team is free
    #   3. fairness         — balance referee load across resolved slots (i.e. per team)
    all_choice_vars = [var for choices in ref_choices.values() for var in choices.values()]
    fairness_max = weights.referee_fairness * len(needs_ref)
    unresolved_weight = fairness_max + 1
    coverage_weight = unresolved_weight + fairness_max + 1

    objective = -coverage_weight * sum(all_choice_vars) + unresolved_weight * sum(unresolved_vars)

    if len(resolved_choice_vars) >= 2 and weights.referee_fairness > 0:
        max_possible = len(needs_ref) + max(fixed_load.values(), default=0)
        loads: list[Any] = []
        for slot_id in sorted(resolved_choice_vars):
            choice_vars = resolved_choice_vars[slot_id]
            fixed = fixed_load.get(slot_id, 0)
            load = model.NewIntVar(fixed, fixed + len(choice_vars), f"ref_load_s{slot_id}")
            model.Add(load == fixed + sum(choice_vars))
            loads.append(load)
        max_load = model.NewIntVar(0, max_possible, "ref_max_load")
        min_load = model.NewIntVar(0, max_possible, "ref_min_load")
        model.AddMaxEquality(max_load, loads)
        model.AddMinEquality(min_load, loads)
        spread = model.NewIntVar(0, max_possible, "ref_spread")
        model.Add(spread == max_load - min_load)
        objective += weights.referee_fairness * spread

    model.Minimize(objective)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    if currently_testing():
        # Single worker + fixed seed makes the referee solver fully deterministic in tests
        # (multi-worker portfolio search is non-deterministic even with a pinned seed).
        solver.parameters.random_seed = SOLVER_RANDOM_SEED
        solver.parameters.num_search_workers = 1
    else:
        solver.parameters.num_search_workers = SOLVER_SEARCH_WORKERS
    status_code = solver.Solve(model)
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.warning(
            "Referee-only assignment found no solution (status %s); leaving matches unassigned",
            solver.StatusName(status_code),
        )
        return {}

    result: dict[MatchId, StageItemInputId] = {}
    for match_id, choices in ref_choices.items():
        for slot_id, var in choices.items():
            if solver.Value(var) == 1:
                result[match_id] = slot_id
                break
    return result


async def assign_missing_referees_only(
    tournament: Tournament,
    stages: list[StageWithStageItems],
    weights: SchedulerWeights = DEFAULT_SCHEDULER_WEIGHTS,
) -> None:
    """Persist referee assignments for scheduled matches that have none."""
    for match_id, slot_id in build_referee_assignment_plan(stages, tournament, weights).items():
        await sql_set_match_referee_slot(match_id, slot_id)


async def schedule_all_unscheduled_matches(
    tournament_id: TournamentId,
    stages: list[StageWithStageItems],
    weights: SchedulerWeights = DEFAULT_SCHEDULER_WEIGHTS,
) -> None:
    await _apply_schedule_plan(tournament_id, stages, reoptimize=False, weights=weights)


async def reoptimize_all_matches(
    tournament_id: TournamentId,
    stages: list[StageWithStageItems],
    weights: SchedulerWeights = DEFAULT_SCHEDULER_WEIGHTS,
) -> None:
    """Re-flow every not-started match, keeping in-progress and completed matches fixed."""
    await _apply_schedule_plan(tournament_id, stages, reoptimize=True, weights=weights)


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
