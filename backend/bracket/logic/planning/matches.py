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
from bracket.sql.referees import sql_set_match_referee, sql_upsert_referee_by_team
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
    referee_team_id: TeamId | None = None


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


def _opponents_are_known(match: ScheduleMatch) -> bool:
    """True only when both opponents are concrete teams.

    Matches in later stages get their opponents from placeholders (e.g. "winner of stage
    item 2 of stage 1"), modelled as ``StageItemInputTentative``. Those resolve to a real
    team only once the prior stage is activated. While a match still has a placeholder (or
    empty) input we don't know who will play it, so the referee optimizer must not assign a
    concrete team as its referee — that team might turn out to be one of the players
    (issue #121). Such matches are left without a referee until their stage activates and
    the optimizer (or the "assign missing referees" action) is run again.
    """
    return isinstance(match.stage_item_input1, StageItemInputFinal) and isinstance(
        match.stage_item_input2, StageItemInputFinal
    )


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


def _get_team_level_ids(stages: list[StageWithStageItems]) -> dict[TeamId, LevelId | None]:
    """Collect team_id → level_id for every team appearing in any stage item input."""
    teams: dict[TeamId, LevelId | None] = {}
    for stage in stages:
        for stage_item in stage.stage_items:
            for input_ in stage_item.inputs:
                if isinstance(input_, StageItemInputFinal):
                    teams[input_.team_id] = input_.team.level_id
    return teams


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


def _add_referee_assignment(
    model: Any,
    movable_contexts: list[_MatchContext],
    pinned_contexts: list[_MatchContext],
    starts: dict[MatchId, Any],
    ends: dict[MatchId, Any],
    input_intervals: dict[StageItemInputId, list[Any]],
    pinned_by_input: dict[StageItemInputId, list[_PinnedMatch]],
    pinned_by_referee_team: dict[TeamId, list[_PinnedMatch]],
    team_level_ids: dict[TeamId, LevelId | None],
    horizon: int,
    reoptimize: bool = False,
) -> tuple[dict[MatchId, dict[TeamId, Any]], list[Any]]:
    """Add referee decision variables, hard constraints, and fairness objective.

    For each movable match without a referee, optionally assigns one team (same level,
    not currently playing). When reoptimize=True, existing referee assignments on movable
    matches are also freed up and reshuffled by the solver. When reoptimize=False, a match
    that already has a referee keeps it, but the no-overlap constraint still applies because
    its start time is re-flowed. Hard constraints prevent a team from refereeing when it is
    playing or already refereeing another overlapping match. The fairness term minimises the
    spread of per-team referee counts across all eligible teams.

    Returns (ref_choices, [spread_var]) where ref_choices[match_id][team_id] is the
    BoolVar indicating whether that team referees that match, and spread_var (if any
    eligible team exists for at least two teams) is the min-max spread to add to the
    objective.
    """
    # Build team_id -> set of stage_item_input_ids (from all contexts, for overlap tracking)
    all_contexts = movable_contexts + pinned_contexts
    team_to_input_ids: dict[TeamId, set[StageItemInputId]] = defaultdict(set)
    for context in all_contexts:
        match = context.match
        for input_, input_id in (
            (match.stage_item_input1, match.stage_item_input1_id),
            (match.stage_item_input2, match.stage_item_input2_id),
        ):
            if isinstance(input_, StageItemInputFinal) and input_id is not None:
                team_to_input_ids[input_.team_id].add(input_id)

    # Build match_id -> set of team_ids that are PLAYING in each movable match
    match_playing_teams: dict[MatchId, set[TeamId]] = {}
    for context in movable_contexts:
        playing: set[TeamId] = set()
        for input_ in (context.match.stage_item_input1, context.match.stage_item_input2):
            if isinstance(input_, StageItemInputFinal):
                playing.add(input_.team_id)
        match_playing_teams[context.match.id] = playing

    # Create referee decision variables for each movable match.
    # In default (non-reoptimize) mode, a match that already has a referee keeps it: the
    # existing assignment is recorded in preserved_ref_team so the no-overlap constraint still
    # applies while the match is re-flowed. In full-optimize (reoptimize=True) mode, existing
    # assignments are cleared and the solver picks a fresh referee for every movable match.
    ref_choices: dict[MatchId, dict[TeamId, Any]] = {}
    match_durations: dict[MatchId, int] = {}
    preserved_ref_team: dict[MatchId, TeamId] = {}
    for context in movable_contexts:
        match = context.match
        if not _opponents_are_known(match):
            # Defer: a placeholder match's players aren't known yet, so don't pick a referee.
            continue
        if match.referee_id is not None and not reoptimize:
            # Non-reoptimize: preserve the existing assignment; still constrain overlaps.
            referee = match.referee
            if referee is not None and referee.team_id is not None:
                preserved_ref_team[match.id] = referee.team_id
                match_durations[match.id] = match.duration_minutes
            continue

        match_level = context.level_id
        playing_teams = match_playing_teams[match.id]
        eligible = {
            team_id
            for team_id, level_id in team_level_ids.items()
            if level_id == match_level and team_id not in playing_teams
        }
        if not eligible:
            continue

        choices: dict[TeamId, Any] = {
            team_id: model.NewBoolVar(f"ref_match_{match.id}_team_{team_id}")
            for team_id in sorted(eligible)  # sorted for determinism
        }
        model.AddExactlyOne(choices.values())
        ref_choices[match.id] = choices
        match_durations[match.id] = match.duration_minutes

    if not ref_choices and not preserved_ref_team:
        return {}, []

    all_eligible_teams: set[TeamId] = set(
        team_id for choices in ref_choices.values() for team_id in choices
    )

    # Per-team interval lists: playing (movable) + referee (optional new, mandatory preserved,
    # movable) + pinned referee
    team_all_intervals: dict[TeamId, list[Any]] = defaultdict(list)

    # Add movable playing intervals for every team that participates in a referee constraint:
    # eligible candidates, teams refereeing a pinned match, and teams whose preserved referee
    # assignment sits on a movable match. Each needs conflict-checking against the others.
    for team_id in (
        all_eligible_teams | set(pinned_by_referee_team.keys()) | set(preserved_ref_team.values())
    ):
        for input_id in team_to_input_ids.get(team_id, set()):
            team_all_intervals[team_id].extend(input_intervals.get(input_id, []))

    # Add optional referee intervals for movable matches
    for match_id, choices in ref_choices.items():
        duration = match_durations[match_id]
        for team_id, var in choices.items():
            ref_end = model.NewIntVar(
                0,
                horizon + duration,
                f"ref_end_match_{match_id}_team_{team_id}",
            )
            team_all_intervals[team_id].append(
                model.NewOptionalIntervalVar(
                    starts[match_id],
                    duration,
                    ref_end,
                    var,
                    f"ref_interval_match_{match_id}_team_{team_id}",
                )
            )

    # Add mandatory referee intervals for preserved assignments on movable matches. The team
    # is fixed, but the start is a variable, so a plain (non-optional) interval at the match's
    # start makes AddNoOverlap forbid the team from playing or refereeing anything else then.
    for match_id, team_id in preserved_ref_team.items():
        duration = match_durations[match_id]
        ref_end = model.NewIntVar(
            0,
            horizon + duration,
            f"preserved_ref_end_match_{match_id}_team_{team_id}",
        )
        team_all_intervals[team_id].append(
            model.NewIntervalVar(
                starts[match_id],
                duration,
                ref_end,
                f"preserved_ref_interval_match_{match_id}_team_{team_id}",
            )
        )

    # Add fixed intervals for pinned referee assignments so AddNoOverlap covers:
    #   - movable playing vs pinned referee (team plays a movable match, referees a pinned one)
    #   - movable referee vs pinned referee (team referees both a movable and a pinned match)
    for team_id, pinned_ref_matches in pinned_by_referee_team.items():
        for pinned in pinned_ref_matches:
            duration = pinned.end_minutes - pinned.start_minutes
            if duration > 0:
                team_all_intervals[team_id].append(
                    model.NewFixedSizeIntervalVar(
                        pinned.start_minutes,
                        duration,
                        f"pinned_ref_match_{pinned.context.match.id}_team_{team_id}",
                    )
                )

    # No-overlap: a team cannot play or referee two overlapping intervals (movable vs movable,
    # movable vs pinned-referee; pinned-playing vs movable-referee is handled separately below)
    for team_id, intervals in team_all_intervals.items():
        if len(intervals) >= 2:
            model.AddNoOverlap(intervals)

    # Explicit constraints for movable referee vs pinned playing intervals
    for match_id, choices in ref_choices.items():
        for team_id, var in choices.items():
            for input_id in team_to_input_ids.get(team_id, set()):
                for pinned in pinned_by_input.get(input_id, []):
                    before = model.NewBoolVar(
                        f"ref_match_{match_id}_team_{team_id}_"
                        f"before_pinned_{pinned.context.match.id}"
                    )
                    after = model.NewBoolVar(
                        f"ref_match_{match_id}_team_{team_id}_"
                        f"after_pinned_{pinned.context.match.id}"
                    )
                    model.Add(ends[match_id] <= pinned.start_minutes).OnlyEnforceIf([var, before])
                    model.Add(starts[match_id] >= pinned.end_minutes).OnlyEnforceIf([var, after])
                    model.AddBoolOr([before, after, var.Not()])

    # Same constraint for preserved (fixed) referees on movable matches: the team is committed
    # unconditionally, so the movable match must sit entirely before or after each pinned match
    # the referee team plays in.
    for match_id, team_id in preserved_ref_team.items():
        for input_id in team_to_input_ids.get(team_id, set()):
            for pinned in pinned_by_input.get(input_id, []):
                before = model.NewBoolVar(
                    f"preserved_ref_match_{match_id}_team_{team_id}_"
                    f"before_pinned_{pinned.context.match.id}"
                )
                after = model.NewBoolVar(
                    f"preserved_ref_match_{match_id}_team_{team_id}_"
                    f"after_pinned_{pinned.context.match.id}"
                )
                model.Add(ends[match_id] <= pinned.start_minutes).OnlyEnforceIf(before)
                model.Add(starts[match_id] >= pinned.end_minutes).OnlyEnforceIf(after)
                model.AddBoolOr([before, after])

    # Fixed referee load from pinned matches (already assigned, can't change)
    fixed_ref_count: dict[TeamId, int] = defaultdict(int)
    for context in pinned_contexts:
        ref = context.match.referee
        if ref is not None and ref.team_id in all_eligible_teams:
            fixed_ref_count[ref.team_id] += 1

    # Total load per team = fixed + variable referee assignments
    max_possible_load = len(movable_contexts) + (max(fixed_ref_count.values(), default=0))
    team_loads: list[Any] = []
    for team_id in sorted(all_eligible_teams):  # sorted for determinism
        fixed = fixed_ref_count.get(team_id, 0)
        var_choices = [
            ref_choices[mid][team_id] for mid in ref_choices if team_id in ref_choices[mid]
        ]
        if var_choices:
            load = model.NewIntVar(fixed, fixed + len(var_choices), f"ref_load_team_{team_id}")
            model.Add(load == fixed + sum(var_choices))
        else:
            load = model.NewIntVar(fixed, fixed, f"ref_load_team_{team_id}")
        team_loads.append(load)

    if len(team_loads) < 2:
        # Single eligible team forced to referee all matches; no spread to balance.
        return ref_choices, []

    max_load = model.NewIntVar(0, max_possible_load, "ref_max_load")
    min_load = model.NewIntVar(0, max_possible_load, "ref_min_load")
    model.AddMaxEquality(max_load, team_loads)
    model.AddMinEquality(min_load, team_loads)
    spread = model.NewIntVar(0, max_possible_load, "ref_spread")
    model.Add(spread == max_load - min_load)
    return ref_choices, [spread]


def _build_operations_from_solution(
    solver: Any,
    movable_contexts: list[_MatchContext],
    pinned_contexts: list[_MatchContext],
    starts: dict[MatchId, Any],
    court_choices: dict[MatchId, dict[CourtId, Any]],
    ref_choices: dict[MatchId, dict[TeamId, Any]],
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
        referee_team_id: TeamId | None = None
        if match_id in ref_choices:
            referee_team_id = next(
                (
                    team_id
                    for team_id, var in ref_choices[match_id].items()
                    if solver.Value(var) == 1
                ),
                None,
            )
        operation_to_schedule = ScheduleOperation(
            court_id, start_time, 0, context.match, referee_team_id
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
                        operation_for_position.referee_team_id,
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
    pinned_by_input = _pinned_matches_by_input(contexts, tournament, pinned_ids)
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

    ref_choices: dict[MatchId, dict[TeamId, Any]] = {}
    if tournament.referees_enabled:
        team_level_ids = _get_team_level_ids(stages)
        pinned_by_referee_team: dict[TeamId, list[_PinnedMatch]] = defaultdict(list)
        for context in pinned_contexts:
            ref = context.match.referee
            if ref is None or ref.team_id is None:
                continue
            start_minutes = _minute_offset(tournament, assert_some(context.match.start_time))
            pinned_by_referee_team[ref.team_id].append(
                _PinnedMatch(
                    context=context,
                    start_minutes=start_minutes,
                    end_minutes=start_minutes + context.match.duration_minutes,
                )
            )
        ref_choices, ref_spreads = _add_referee_assignment(
            model,
            movable_contexts,
            pinned_contexts,
            starts,
            ends,
            input_intervals,
            pinned_by_input,
            pinned_by_referee_team,
            team_level_ids,
            horizon,
            reoptimize,
        )
        if ref_spreads and weights.referee_fairness > 0:
            objective += weights.referee_fairness * sum(ref_spreads)

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
        if op.referee_team_id is not None:
            referee = await sql_upsert_referee_by_team(tournament_id, op.referee_team_id)
            await sql_set_match_referee(op.match.id, referee.id)


def build_referee_assignment_plan(
    stages: list[StageWithStageItems],
    tournament: Tournament,
    weights: SchedulerWeights = DEFAULT_SCHEDULER_WEIGHTS,
) -> dict[MatchId, TeamId]:
    """Assign referees to already-scheduled matches that have none, without moving any match.

    Returns a mapping of match_id → team_id for each match that received a new referee.
    Matches that already have a referee, unscheduled matches, and matches with no eligible
    candidate are left untouched. Never fails — returns what it can.
    """
    if not tournament.referees_enabled:
        return {}

    contexts = _get_match_contexts(stages)
    team_level_ids = _get_team_level_ids(stages)

    # Only scheduled matches (fixed court + start_time) participate.
    scheduled_contexts = [c for c in contexts if _is_scheduled(c)]
    if not scheduled_contexts:
        return {}

    # Build per-team playing intervals (minute offsets) over all scheduled matches.
    team_playing_intervals: dict[TeamId, list[tuple[int, int]]] = defaultdict(list)
    for context in scheduled_contexts:
        start_min = _minute_offset(tournament, assert_some(context.match.start_time))
        end_min = start_min + context.match.duration_minutes
        for input_ in (context.match.stage_item_input1, context.match.stage_item_input2):
            if isinstance(input_, StageItemInputFinal):
                team_playing_intervals[input_.team_id].append((start_min, end_min))

    needs_ref = [c for c in scheduled_contexts if c.match.referee_id is None]
    has_ref = [c for c in scheduled_contexts if c.match.referee_id is not None]

    if not needs_ref:
        return {}

    # Build per-team refereeing intervals from already-assigned matches so we can
    # exclude teams that are already committed as referee at an overlapping time.
    team_refereeing_intervals: dict[TeamId, list[tuple[int, int]]] = defaultdict(list)
    for context in has_ref:
        ref = context.match.referee
        if ref is not None and ref.team_id is not None:
            start_min = _minute_offset(tournament, assert_some(context.match.start_time))
            end_min = start_min + context.match.duration_minutes
            team_refereeing_intervals[ref.team_id].append((start_min, end_min))

    model = cp_model.CpModel()

    ref_choices: dict[MatchId, dict[TeamId, Any]] = {}
    match_windows: dict[MatchId, tuple[int, int]] = {}

    for context in needs_ref:
        match = context.match
        if not _opponents_are_known(match):
            # Defer: a placeholder match's players aren't known yet, so don't pick a referee.
            continue
        start_min = _minute_offset(tournament, assert_some(match.start_time))
        end_min = start_min + match.duration_minutes
        match_windows[match.id] = (start_min, end_min)

        playing_teams: set[TeamId] = set()
        for input_ in (match.stage_item_input1, match.stage_item_input2):
            if isinstance(input_, StageItemInputFinal):
                playing_teams.add(input_.team_id)

        # Eligible: same level, not playing in this match, not playing or refereeing at overlap.
        eligible: set[TeamId] = set()
        for team_id, level_id in team_level_ids.items():
            if level_id != context.level_id or team_id in playing_teams:
                continue
            if any(
                start_min < p_end and p_start < end_min
                for p_start, p_end in team_playing_intervals.get(team_id, [])
            ):
                continue
            if any(
                start_min < r_end and r_start < end_min
                for r_start, r_end in team_refereeing_intervals.get(team_id, [])
            ):
                continue
            eligible.add(team_id)

        if not eligible:
            continue

        choices: dict[TeamId, Any] = {
            team_id: model.NewBoolVar(f"ref_match_{match.id}_team_{team_id}")
            for team_id in sorted(eligible)
        }
        model.AddAtMostOne(choices.values())
        ref_choices[match.id] = choices

    if not ref_choices:
        return {}

    all_eligible_teams: set[TeamId] = set(
        team_id for choices in ref_choices.values() for team_id in choices
    )

    # A team cannot referee two overlapping matches.
    sorted_match_ids = sorted(ref_choices.keys())
    for i, mid1 in enumerate(sorted_match_ids):
        for mid2 in sorted_match_ids[i + 1 :]:
            s1, e1 = match_windows[mid1]
            s2, e2 = match_windows[mid2]
            if s1 < e2 and s2 < e1:
                for team_id in set(ref_choices[mid1]) & set(ref_choices[mid2]):
                    model.AddBoolOr(
                        [ref_choices[mid1][team_id].Not(), ref_choices[mid2][team_id].Not()]
                    )

    # Count existing assignments toward the fairness objective.
    fixed_ref_count: dict[TeamId, int] = defaultdict(int)
    for context in has_ref:
        ref = context.match.referee
        if ref is not None and ref.team_id is not None and ref.team_id in all_eligible_teams:
            fixed_ref_count[ref.team_id] += 1

    max_possible_load = len(needs_ref) + (max(fixed_ref_count.values(), default=0))
    team_loads: list[Any] = []
    for team_id in sorted(all_eligible_teams):
        fixed = fixed_ref_count.get(team_id, 0)
        var_choices = [
            ref_choices[mid][team_id] for mid in ref_choices if team_id in ref_choices[mid]
        ]
        if var_choices:
            load = model.NewIntVar(fixed, fixed + len(var_choices), f"ref_load_team_{team_id}")
            model.Add(load == fixed + sum(var_choices))
        else:
            load = model.NewIntVar(fixed, fixed, f"ref_load_team_{team_id}")
        team_loads.append(load)

    # Primary objective: maximize coverage (fill as many matches as possible).
    # Secondary objective: minimize fairness spread.
    # Coverage weight must dominate fairness so the solver never skips an
    # assignable match to improve the spread. A safe bound: assigning one extra
    # match saves (max_load_spread * referee_fairness + 1) units vs. the worst
    # possible change in spread that the same assignment could cause.
    coverage_weight = weights.referee_fairness + 1
    all_choice_vars = [var for choices in ref_choices.values() for var in choices.values()]
    # total_assigned is the sum of all AtMostOne choice vars (0/1 per match)
    total_assigned_expr = sum(all_choice_vars)

    if len(team_loads) >= 2:
        max_load = model.NewIntVar(0, max_possible_load, "ref_max_load")
        min_load = model.NewIntVar(0, max_possible_load, "ref_min_load")
        model.AddMaxEquality(max_load, team_loads)
        model.AddMinEquality(min_load, team_loads)
        spread = model.NewIntVar(0, max_possible_load, "ref_spread")
        model.Add(spread == max_load - min_load)
        model.Minimize(
            -coverage_weight * total_assigned_expr
            + (weights.referee_fairness * spread if weights.referee_fairness > 0 else 0)
        )
    else:
        model.Minimize(-coverage_weight * total_assigned_expr)

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

    result: dict[MatchId, TeamId] = {}
    for match_id, choices in ref_choices.items():
        for team_id, var in choices.items():
            if solver.Value(var) == 1:
                result[match_id] = team_id
                break
    return result


async def assign_missing_referees_only(
    tournament: Tournament,
    stages: list[StageWithStageItems],
    weights: SchedulerWeights = DEFAULT_SCHEDULER_WEIGHTS,
) -> None:
    """Persist referee assignments for scheduled matches that have none."""
    for match_id, team_id in build_referee_assignment_plan(stages, tournament, weights).items():
        referee = await sql_upsert_referee_by_team(tournament.id, team_id)
        await sql_set_match_referee(match_id, referee.id)


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
