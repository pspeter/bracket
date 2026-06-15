from collections import defaultdict
from datetime import timedelta

import pytest
from heliclockter import datetime_utc

from bracket.logic.planning import matches as planning_matches
from bracket.logic.planning.matches import (
    MatchPosition,
    ScheduleOperation,
    build_referee_assignment_plan,
    build_schedule_plan,
    reorder_all_matches,
)
from bracket.models.db.court import Court
from bracket.models.db.match import (
    MatchState,
    MatchWithDetails,
    MatchWithDetailsDefinitive,
    SchedulerWeights,
)
from bracket.models.db.referee import Referee
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInput,
    StageItemInputEmpty,
    StageItemInputFinal,
    StageItemInputTentative,
)
from bracket.models.db.team import Team
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_TOURNAMENT
from bracket.utils.id_types import (
    CourtId,
    LevelId,
    MatchId,
    RefereeId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)

T0 = DUMMY_MOCK_TIME
DURATION = DUMMY_TOURNAMENT.duration_minutes  # 10
MARGIN = DUMMY_TOURNAMENT.margin_minutes  # 5
SLOT = DURATION + MARGIN  # 15 minutes per match
SqlCall = tuple[CourtId, datetime_utc, MatchId]


def _match(id_: int) -> MatchWithDetails:
    return MatchWithDetails(
        id=MatchId(id_),
        created=T0,
        duration_minutes=DURATION,
        round_id=RoundId(id_),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )


def _stage(
    stage_id: int,
    matches_per_item: list[list[MatchWithDetails]],
    level_id: LevelId | None = None,
    inputs_per_item: list[list[StageItemInput]] | None = None,
) -> StageWithStageItems:
    return _stage_with_rounds(
        stage_id,
        [[matches] for matches in matches_per_item],
        level_id=level_id,
        inputs_per_item=inputs_per_item,
    )


def _stage_with_rounds(
    stage_id: int,
    rounds_per_item: list[list[list[MatchWithDetails]]],
    level_id: LevelId | None = None,
    inputs_per_item: list[list[StageItemInput]] | None = None,
) -> StageWithStageItems:
    stage_items = []
    for item_idx, rounds in enumerate(rounds_per_item):
        item_id = stage_id * 100 + item_idx
        rounds_with_matches = []
        for round_idx, matches in enumerate(rounds):
            round_matches: list[MatchWithDetails | MatchWithDetailsDefinitive] = list(matches)
            rounds_with_matches.append(
                RoundWithMatches(
                    id=RoundId(item_id * 100 + round_idx),
                    matches=round_matches,
                    stage_item_id=StageItemId(item_id),
                    created=T0,
                    is_draft=False,
                    name="",
                )
            )
        stage_items.append(
            StageItemWithRounds(
                id=StageItemId(item_id),
                stage_id=StageId(stage_id),
                rounds=rounds_with_matches,
                inputs=inputs_per_item[item_idx] if inputs_per_item is not None else [],
                type_name="Single Elimination",
                team_count=2,
                ranking_id=None,
                created=T0,
                name=f"Group {item_idx}",
                type=StageType.SINGLE_ELIMINATION,
            )
        )
    return StageWithStageItems(
        id=StageId(stage_id),
        tournament_id=TournamentId(-1),
        name="",
        created=T0,
        is_active=False,
        level_id=level_id,
        stage_items=stage_items,
    )


def _court(id_: int) -> Court:
    return Court(id=CourtId(id_), name=f"Court {id_}", created=T0, tournament_id=TournamentId(-1))


def _tournament() -> Tournament:
    return Tournament(**DUMMY_TOURNAMENT.model_dump(), id=TournamentId(-1))


def _end_time(op: ScheduleOperation) -> datetime_utc:
    return op.start_time + timedelta(minutes=op.match.duration_minutes)


def _assert_match_ids_scheduled(
    ops: list[ScheduleOperation], matches: list[MatchWithDetails]
) -> None:
    assert {op.match.id for op in ops} == {match.id for match in matches}


def _assert_starts_on_whole_minute(ops: list[ScheduleOperation]) -> None:
    for op in ops:
        offset = op.start_time - T0
        assert offset.total_seconds() >= 0
        assert offset.total_seconds() % 60 == 0


def _assert_default_break_between_court_matches(ops: list[ScheduleOperation]) -> None:
    ops_by_court: dict[CourtId, list[ScheduleOperation]] = defaultdict(list)
    for op in ops:
        ops_by_court[op.court_id].append(op)

    for court_ops in ops_by_court.values():
        scheduled = sorted(court_ops, key=lambda op: (op.start_time, op.match.id))
        for previous, op in zip(scheduled, scheduled[1:], strict=False):
            assert op.start_time >= _end_time(previous) + timedelta(minutes=MARGIN)


def _assert_no_input_overlap(ops: list[ScheduleOperation]) -> None:
    for index, first in enumerate(ops):
        first_input_ids = {first.match.stage_item_input1_id, first.match.stage_item_input2_id}
        first_input_ids.discard(None)
        if not first_input_ids:
            continue
        for second in ops[index + 1 :]:
            second_input_ids = {
                second.match.stage_item_input1_id,
                second.match.stage_item_input2_id,
            }
            second_input_ids.discard(None)
            if not first_input_ids.intersection(second_input_ids):
                continue
            assert first.start_time >= _end_time(second) or second.start_time >= _end_time(first)


# ── Tracer bullet ────────────────────────────────────────────────────────────


def test_single_level_single_stage_one_court() -> None:
    """Two matches on one court are scheduled sequentially."""
    m1, m2 = _match(1), _match(2)
    stages = [_stage(1, [[m1, m2]])]
    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    assert len(ops) == 2
    assert all(op.court_id == CourtId(1) for op in ops)
    assert ops[0].start_time == T0
    assert ops[1].start_time == T0 + timedelta(minutes=SLOT)
    assert ops[0].position == 0
    assert ops[1].position == 1


def test_schedule_avoids_team_overlap_across_courts() -> None:
    """Matches sharing a stage-item input never overlap, even when another court is free."""
    m1 = _match(1).model_copy(update={"stage_item_input1_id": 1, "stage_item_input2_id": 2})
    m2 = _match(2).model_copy(update={"stage_item_input1_id": 3, "stage_item_input2_id": 4})
    m3 = _match(3).model_copy(update={"stage_item_input1_id": 1, "stage_item_input2_id": 5})
    stages = [_stage(1, [[m1, m2, m3]])]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, [m1, m2, m3])
    _assert_no_input_overlap(ops)
    _assert_default_break_between_court_matches(ops)


# ── Cross-stage-item interleaving on one court ───────────────────────────────


def test_one_court_two_equal_sis_are_scheduled_with_default_breaks() -> None:
    """1 court, 2 stage items × 2 matches → all matches are placed on playable times."""
    a1, a2 = _match(1), _match(2)
    b1, b2 = _match(3), _match(4)
    stages = [_stage(1, [[a1, a2], [b1, b2]])]

    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    _assert_match_ids_scheduled(ops, [a1, a2, b1, b2])
    assert all(op.court_id == CourtId(1) for op in ops)
    _assert_starts_on_whole_minute(ops)
    _assert_default_break_between_court_matches(ops)


def test_two_courts_two_levels_minimizes_makespan_without_court_conflicts() -> None:
    """Matches from multiple levels share courts while keeping the shortest possible finish."""
    level_a = LevelId(1)
    level_b = LevelId(2)
    a1 = [_match(10), _match(11)]
    a2 = [_match(12), _match(13)]
    b1 = [_match(20), _match(21)]
    b2 = [_match(22), _match(23)]
    stages = [
        _stage(1, [a1, a2], level_id=level_a),
        _stage(2, [b1, b2], level_id=level_b),
    ]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, a1 + a2 + b1 + b2)
    _assert_default_break_between_court_matches(ops)
    assert max(_end_time(op) for op in ops) == T0 + timedelta(minutes=DURATION + 3 * SLOT)


def test_two_courts_two_equal_sis_finish_in_three_match_slots() -> None:
    """2 courts, 6 independent matches → the makespan objective uses both courts."""
    a_matches = [_match(10), _match(11), _match(12)]
    b_matches = [_match(20), _match(21), _match(22)]
    stages = [_stage(1, [a_matches, b_matches])]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, a_matches + b_matches)
    _assert_default_break_between_court_matches(ops)
    assert max(_end_time(op) for op in ops) == T0 + timedelta(minutes=DURATION + 2 * SLOT)


def test_one_court_schedules_all_matches_at_shortest_possible_finish() -> None:
    """With 1 court, 6 independent matches occupy 6 separated slots."""
    a_matches = [_match(10 + i) for i in range(4)]
    b_matches = [_match(20 + i) for i in range(2)]
    stages = [_stage(1, [a_matches, b_matches])]

    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    _assert_match_ids_scheduled(ops, a_matches + b_matches)
    _assert_default_break_between_court_matches(ops)
    assert max(_end_time(op) for op in ops) == T0 + timedelta(minutes=DURATION + 5 * SLOT)


def test_two_courts_imbalanced_sis_still_minimize_makespan() -> None:
    """2 courts, 12 independent matches finish in 6 slots regardless of group sizes."""
    large = [_match(10 + i) for i in range(8)]
    small_a = [_match(20 + i) for i in range(2)]
    small_b = [_match(30 + i) for i in range(2)]
    stages = [_stage(1, [large, small_a, small_b])]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, large + small_a + small_b)
    _assert_default_break_between_court_matches(ops)
    assert max(_end_time(op) for op in ops) == T0 + timedelta(minutes=DURATION + 5 * SLOT)


def test_two_courts_multi_level_imbalanced_sis_still_minimize_makespan() -> None:
    """The makespan objective schedules multiple levels together on shared courts."""
    level_a = LevelId(1)
    level_b = LevelId(2)
    large = [_match(10 + i) for i in range(8)]
    small_a = [_match(20 + i) for i in range(2)]
    small_b = [_match(30 + i) for i in range(2)]
    stages = [
        _stage(1, [large], level_id=level_a),
        _stage(2, [small_a, small_b], level_id=level_b),
    ]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, large + small_a + small_b)
    _assert_default_break_between_court_matches(ops)
    assert max(_end_time(op) for op in ops) == T0 + timedelta(minutes=DURATION + 5 * SLOT)


def test_winner_of_match_starts_after_feeders_plus_default_break() -> None:
    """Elimination successors wait for both winner-of feeder matches."""
    semi1 = _match(10)
    semi2 = _match(11)
    final = _match(12).model_copy(
        update={
            "stage_item_input1_winner_from_match_id": semi1.id,
            "stage_item_input2_winner_from_match_id": semi2.id,
        }
    )
    stages = [_stage_with_rounds(1, [[[semi1, semi2], [final]]])]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    by_id = {op.match.id: op for op in ops}
    final_start = by_id[final.id].start_time
    assert final_start >= _end_time(by_id[semi1.id]) + timedelta(minutes=MARGIN)
    assert final_start >= _end_time(by_id[semi2.id]) + timedelta(minutes=MARGIN)


# ── Single-level stage boundaries ────────────────────────────────────────────


def test_cross_stage_input_waits_for_source_stage_item_plus_default_break() -> None:
    """A match consuming a previous stage-item result waits for that source to finish."""
    source1, source2 = _match(1), _match(2)
    source_stage_item_id = StageItemId(100)
    target_input = StageItemInputTentative(
        id=StageItemInputId(1000),
        slot=1,
        tournament_id=TournamentId(-1),
        stage_item_id=StageItemId(200),
        winner_from_stage_item_id=source_stage_item_id,
        winner_position=1,
    )
    target = _match(3).model_copy(
        update={"stage_item_input1_id": target_input.id, "stage_item_input1": target_input}
    )
    independent = _match(4)
    stages = [
        _stage(1, [[source1, source2]]),
        _stage(2, [[target, independent]]),
    ]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    source_end = max(_end_time(op) for op in ops if op.match.id in {source1.id, source2.id})
    target_start = next(op.start_time for op in ops if op.match.id == target.id)
    assert target_start >= source_end + timedelta(minutes=MARGIN)


def _empty_input(input_id: int, stage_item_id: int) -> StageItemInputEmpty:
    return StageItemInputEmpty(
        id=StageItemInputId(input_id),
        slot=1,
        tournament_id=TournamentId(-1),
        stage_item_id=StageItemId(stage_item_id),
    )


def test_open_slot_stage_item_waits_for_full_preceding_stage() -> None:
    """A later-stage item with an unwired (empty) input waits for its whole preceding stage.

    Mirrors the best-runner-up case: a knockout spot is filled manually only once the
    group stage is fully played, so the input is left empty and the scheduler cannot
    place the knockout match before every group match has finished — even though there
    is no explicit feeder link to follow.
    """
    level = LevelId(1)
    group = [_match(1), _match(2), _match(3)]
    final = _match(4)
    final_item_id = 200
    final_stage = _stage_with_rounds(
        2,
        [[[final]]],
        level_id=level,
        inputs_per_item=[[_empty_input(500, final_item_id)]],
    )
    stages = [_stage(1, [group], level_id=level), final_stage]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    by_id = {op.match.id: op for op in ops}
    group_end = max(_end_time(by_id[m.id]) for m in group)
    assert by_id[final.id].start_time >= group_end + timedelta(minutes=MARGIN)


def test_fully_wired_later_stage_item_is_not_forced_after_whole_preceding_stage() -> None:
    """A fully-wired later-stage item keeps its tight feeder dependency and may start early.

    Group A is a single match; group B is four matches in the same first stage. The
    knockout only consumes group A's winner, so it can slot in alongside group B and the
    whole tournament finishes in three slots. If the conservative fallback wrongly forced
    the knockout to wait for the entire preceding stage (group A + group B), it could not
    start until group B finished, costing an extra slot. Asserting on the makespan pins
    down that the tight dependency is preserved.
    """
    level = LevelId(1)
    group_a = _match(1)
    group_b = [_match(2), _match(3), _match(4), _match(5)]
    source_item_id = StageItemId(100)  # group A is the first stage's first stage item
    wired_input = StageItemInputTentative(
        id=StageItemInputId(600),
        slot=1,
        tournament_id=TournamentId(-1),
        stage_item_id=StageItemId(200),
        winner_from_stage_item_id=source_item_id,
        winner_position=1,
    )
    knockout = _match(6).model_copy(
        update={"stage_item_input1_id": wired_input.id, "stage_item_input1": wired_input}
    )
    first_stage = _stage(1, [[group_a], group_b], level_id=level)
    second_stage = _stage_with_rounds(
        2, [[[knockout]]], level_id=level, inputs_per_item=[[wired_input]]
    )
    stages = [first_stage, second_stage]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, [group_a, *group_b, knockout])
    # Six matches on two courts with only group A blocking the knockout fit in three slots.
    assert max(_end_time(op) for op in ops) == T0 + timedelta(minutes=DURATION + 2 * SLOT)


def test_single_level_no_idle_court_gap_between_stages() -> None:
    """With 1 court, stage 2 starts immediately after stage 1 ends (no idle gap)."""
    m1, m2 = _match(1), _match(2)
    stages = [_stage(1, [[m1]]), _stage(2, [[m2]])]
    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    assert ops[0].start_time == T0
    assert ops[1].start_time == T0 + timedelta(minutes=SLOT)


# ── Multi-level independent stage boundaries ──────────────────────────────────


def test_two_levels_single_stage_all_matches_scheduled() -> None:
    """Matches from two different levels both get scheduled."""
    level_a = LevelId(1)
    level_b = LevelId(2)
    m1, m2 = _match(1), _match(2)
    stages = [
        _stage(1, [[m1]], level_id=level_a),
        _stage(2, [[m2]], level_id=level_b),
    ]
    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    assert len(ops) == 2
    scheduled_ids = {op.match.id for op in ops}
    assert m1.id in scheduled_ids
    assert m2.id in scheduled_ids


def test_independent_later_stage_can_start_before_unrelated_level_finishes() -> None:
    """Only explicit feeder dependencies block a match; unrelated levels do not."""
    level_a = LevelId(1)
    level_b = LevelId(2)
    a_s1 = _match(1)
    a_s2 = _match(2)
    b_s1 = [_match(10 + i) for i in range(4)]

    stages = [
        _stage(1, [[a_s1]], level_id=level_a),
        _stage(2, [[a_s2]], level_id=level_a),
        _stage(3, [b_s1], level_id=level_b),
    ]
    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, [a_s1, a_s2, *b_s1])
    a_s2_start = next(op.start_time for op in ops if op.match.id == a_s2.id)
    b_s1_end = max(_end_time(op) for op in ops if op.match.id in {m.id for m in b_s1})
    assert a_s2_start < b_s1_end


def test_optimizer_uses_shared_courts_without_idle_gaps_in_simple_case() -> None:
    """With 6 independent matches and 2 courts, the minimized schedule has 3 slots."""
    level_a = LevelId(1)
    level_b = LevelId(2)
    a_s1 = _match(1)
    a_s2 = _match(2)
    b_matches = [_match(10 + i) for i in range(4)]

    stages = [
        _stage(1, [[a_s1]], level_id=level_a),
        _stage(2, [[a_s2]], level_id=level_a),
        _stage(3, [b_matches], level_id=level_b),
    ]
    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, [a_s1, a_s2, *b_matches])
    _assert_default_break_between_court_matches(ops)
    assert max(_end_time(op) for op in ops) == T0 + timedelta(minutes=DURATION + 2 * SLOT)


# ── Objective blend: team rest ───────────────────────────────────────────────


def _team_input(match: MatchWithDetails, team_id: int) -> MatchWithDetails:
    return match.model_copy(
        update={"stage_item_input1_id": StageItemInputId(team_id), "stage_item_input2_id": None}
    )


def test_team_rest_spaces_back_to_back_matches_when_it_is_free() -> None:
    """A team's two matches get a gap when spacing them costs no makespan.

    One court, three matches: a team plays the first and the last, with an
    unrelated match available to slot between them. Every ordering finishes in
    the same three slots, so the rest objective should pull the team's matches
    apart rather than leave them back-to-back.
    """
    m1 = _team_input(_match(1), team_id=1)
    m2 = _match(2).model_copy(
        update={"stage_item_input1_id": StageItemInputId(2), "stage_item_input2_id": None}
    )
    m3 = _team_input(_match(3), team_id=1)
    stages = [_stage(1, [[m1, m2, m3]])]

    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    _assert_match_ids_scheduled(ops, [m1, m2, m3])
    by_id = {op.match.id: op for op in ops}
    earlier, later = sorted((by_id[m1.id], by_id[m3.id]), key=lambda op: op.start_time)
    # At least one match sits between the team's two matches (a full slot of rest).
    assert later.start_time - _end_time(earlier) >= timedelta(minutes=SLOT)


# ── Objective blend: court locality ──────────────────────────────────────────


def _courts_used_by(ops: list[ScheduleOperation], matches: list[MatchWithDetails]) -> set[CourtId]:
    match_ids = {match.id for match in matches}
    return {op.court_id for op in ops if op.match.id in match_ids}


def test_each_group_stays_on_one_court_when_makespan_allows() -> None:
    """With two courts and two groups of two matches, each group stays on a single court.

    Both groups fit in two slots either way, so confining each group to one court costs
    no makespan; the locality objective should prefer that over the naive spread that
    scatters a group across both courts.
    """
    group_a = [_match(10), _match(11)]
    group_b = [_match(20), _match(21)]
    stages = [_stage(1, [group_a, group_b])]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, group_a + group_b)
    _assert_default_break_between_court_matches(ops)
    assert len(_courts_used_by(ops, group_a)) == 1
    assert len(_courts_used_by(ops, group_b)) == 1


# ── Configurable objective weights ───────────────────────────────────────────


def test_court_locality_weight_concentrates_a_group_on_one_court() -> None:
    """Cranking court locality (and zeroing makespan) keeps a stage item's matches on one
    court, even though spreading them across both courts would finish sooner.

    A single stage item of two non-conflicting matches parallelises across both courts under
    the makespan-dominant default; raising the locality weight flips that to one court.
    """
    group = [_match(1), _match(2)]
    stages = [_stage(1, [group])]
    courts = [_court(1), _court(2)]

    default_ops = build_schedule_plan(stages, courts, _tournament())
    assert len(_courts_used_by(default_ops, group)) == 2

    weights = SchedulerWeights(makespan=0, court_locality=1000)
    local_ops = build_schedule_plan(stages, courts, _tournament(), weights=weights)
    assert len(_courts_used_by(local_ops, group)) == 1


def test_higher_comfortable_rest_spaces_a_team_further() -> None:
    """Raising the comfortable-rest threshold (and the rest weight) pulls a team's two
    consecutive matches further apart than the makespan-dominant default does.

    Both matches share a team and sit on one court, so the default packs them a single break
    apart; a rest-dominant blend with a larger comfortable-rest target stretches the gap.
    """
    m1 = _team_input(_match(1), team_id=1)
    m2 = _team_input(_match(2), team_id=1)
    stages = [_stage(1, [[m1, m2]])]
    courts = [_court(1)]

    def _team_gap(ops: list[ScheduleOperation]) -> timedelta:
        by_id = {op.match.id: op for op in ops}
        earlier, later = sorted((by_id[m1.id], by_id[m2.id]), key=lambda op: op.start_time)
        return later.start_time - _end_time(earlier)

    default_gap = _team_gap(build_schedule_plan(stages, courts, _tournament()))
    weights = SchedulerWeights(makespan=1, team_rest=1000, comfortable_rest_minutes=60)
    rested_gap = _team_gap(build_schedule_plan(stages, courts, _tournament(), weights=weights))

    assert rested_gap > default_gap


# ── Objective blend: group sync ──────────────────────────────────────────────


def test_groups_in_a_stage_progress_round_for_round_when_free() -> None:
    """Two groups in one stage keep the same round finishing at the same time.

    Each group has two single-match rounds; with two courts every layout finishes in
    two slots, so keeping the groups in lockstep (round 1 of both, then round 2 of both)
    costs no makespan. The group-sync objective should pick that over letting one group
    race a round ahead.
    """
    a1, a2 = _match(10), _match(11)
    b1, b2 = _match(20), _match(21)
    stages = [_stage_with_rounds(1, [[[a1], [a2]], [[b1], [b2]]])]

    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    _assert_match_ids_scheduled(ops, [a1, a2, b1, b2])
    by_id = {op.match.id: op for op in ops}
    # Each round's matches across the two groups finish at the same time (zero spread).
    assert _end_time(by_id[a1.id]) == _end_time(by_id[b1.id])
    assert _end_time(by_id[a2.id]) == _end_time(by_id[b2.id])


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_no_courts_returns_empty() -> None:
    stages = [_stage(1, [[_match(1)]])]
    assert build_schedule_plan(stages, [], _tournament()) == []


def test_no_stages_returns_empty() -> None:
    assert build_schedule_plan([], [_court(1)], _tournament()) == []


def test_already_scheduled_matches_are_skipped() -> None:
    """Matches with start_time set are not rescheduled."""
    scheduled = MatchWithDetails(
        id=MatchId(99),
        created=T0,
        duration_minutes=DURATION,
        round_id=RoundId(99),
        start_time=T0,
        court_id=CourtId(1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    unscheduled = _match(1)
    stages = [_stage(1, [[scheduled, unscheduled]])]
    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    assert len(ops) == 1
    assert ops[0].match.id == unscheduled.id


def test_new_matches_respect_pinned_court_slot_and_default_break() -> None:
    """Pinned matches keep their slot; unscheduled matches are placed around them."""
    scheduled = _match(99).model_copy(update={"start_time": T0, "court_id": CourtId(1)})
    unscheduled = _match(1)
    stages = [_stage(1, [[scheduled, unscheduled]])]

    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    assert len(ops) == 1
    assert ops[0].match.id == unscheduled.id
    assert ops[0].court_id == scheduled.court_id
    assert ops[0].start_time >= scheduled.end_time + timedelta(minutes=MARGIN)


def test_conflicting_pinned_matches_stay_pinned_while_new_match_avoids_them() -> None:
    """Relax-around-pins drops pinned-vs-pinned conflicts but avoids adding new ones."""
    pinned1 = _match(1).model_copy(update={"start_time": T0, "court_id": CourtId(1)})
    pinned2 = _match(2).model_copy(update={"start_time": T0, "court_id": CourtId(1)})
    unscheduled = _match(3)
    stages = [_stage(1, [[pinned1, pinned2, unscheduled]])]

    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    assert len(ops) == 1
    assert ops[0].match.id == unscheduled.id
    assert ops[0].start_time >= pinned1.end_time + timedelta(minutes=MARGIN)
    assert ops[0].start_time >= pinned2.end_time + timedelta(minutes=MARGIN)


# ── Re-optimize everything (reoptimize=True) ─────────────────────────────────


def test_reoptimize_reflows_not_started_but_not_in_progress() -> None:
    """Reoptimize re-flows a scheduled not-started match but leaves an in-progress one pinned."""
    in_progress = _match(1).model_copy(
        update={"start_time": T0, "court_id": CourtId(1), "state": MatchState.IN_PROGRESS}
    )
    not_started = _match(2).model_copy(
        update={"start_time": T0 + timedelta(minutes=SLOT), "court_id": CourtId(1)}
    )
    stages = [_stage(1, [[in_progress, not_started]])]

    # Default mode: both are scheduled, so both are pinned and nothing is re-placed.
    assert build_schedule_plan(stages, [_court(1)], _tournament()) == []

    # Reoptimize mode: the not-started match becomes movable; the in-progress one stays put.
    ops = build_schedule_plan(stages, [_court(1)], _tournament(), reoptimize=True)
    assert {op.match.id for op in ops} == {not_started.id}


def test_reoptimize_pins_completed_match() -> None:
    """A completed match is held fixed too; only not-started matches are re-flowed."""
    completed = _match(1).model_copy(
        update={"start_time": T0, "court_id": CourtId(1), "state": MatchState.COMPLETED}
    )
    not_started = _match(2)
    stages = [_stage(1, [[completed, not_started]])]

    ops = build_schedule_plan(stages, [_court(1)], _tournament(), reoptimize=True)

    assert {op.match.id for op in ops} == {not_started.id}


def test_reoptimize_flows_movable_matches_around_pinned_slot() -> None:
    """Re-flowed not-started matches never overlap a pinned in-progress match's court slot."""
    in_progress = _match(1).model_copy(
        update={"start_time": T0, "court_id": CourtId(1), "state": MatchState.IN_PROGRESS}
    )
    # Two not-started matches sitting on top of the in-progress slot; reoptimize must move them.
    movable_a = _match(2).model_copy(update={"start_time": T0, "court_id": CourtId(1)})
    movable_b = _match(3).model_copy(update={"start_time": T0, "court_id": CourtId(1)})
    stages = [_stage(1, [[in_progress, movable_a, movable_b]])]

    ops = build_schedule_plan(stages, [_court(1)], _tournament(), reoptimize=True)

    assert {op.match.id for op in ops} == {movable_a.id, movable_b.id}
    for op in ops:
        if op.court_id == in_progress.court_id:
            assert op.start_time >= in_progress.end_time + timedelta(minutes=MARGIN)
    _assert_default_break_between_court_matches(ops)


# ── reorder_all_matches ──────────────────────────────────────────────────────


def _on_court(match: MatchWithDetails, court_id: int) -> MatchWithDetails:
    return match.model_copy(update={"court_id": CourtId(court_id)})


@pytest.fixture
def capture_sql_calls(monkeypatch: pytest.MonkeyPatch) -> list[SqlCall]:
    """Replace the DB-writing helper with a list recorder."""
    calls: list[SqlCall] = []

    async def fake_reschedule(court_id, start_time, match, tournament):  # type: ignore[no-untyped-def]
        calls.append((court_id, start_time, match.id))

    monkeypatch.setattr(
        planning_matches,
        "sql_reschedule_match_and_determine_duration",
        fake_reschedule,
    )
    return calls


async def test_reorder_respects_cross_level_position_ordering(
    capture_sql_calls: list[SqlCall],
) -> None:
    """A match dragged to position 0 stays before others on the same court, regardless of level."""
    level_a = _on_court(_match(1), 1)
    level_b = _on_court(_match(2), 1)
    # Level B was dragged before Level A (fractional position from handle_match_reschedule)
    positions = [
        MatchPosition(match=level_a, position=1.0),
        MatchPosition(match=level_b, position=0.5),
    ]

    await reorder_all_matches(_tournament(), positions)

    assert capture_sql_calls == [
        (CourtId(1), T0, level_b.id),
        (CourtId(1), T0 + timedelta(minutes=SLOT), level_a.id),
    ]


async def test_reorder_keeps_same_level_matches_sequential(
    capture_sql_calls: list[SqlCall],
) -> None:
    """Two matches on the same court are scheduled back-to-back from tournament start."""
    m1 = _on_court(_match(1), 1)
    m2 = _on_court(_match(2), 1)
    positions = [
        MatchPosition(match=m1, position=0.0),
        MatchPosition(match=m2, position=1.0),
    ]

    await reorder_all_matches(_tournament(), positions)

    assert capture_sql_calls == [
        (CourtId(1), T0, m1.id),
        (CourtId(1), T0 + timedelta(minutes=SLOT), m2.id),
    ]


async def test_reorder_courts_are_independent(
    capture_sql_calls: list[SqlCall],
) -> None:
    """Each court starts at tournament.start_time — no court waits for another."""
    c1_match = _on_court(_match(1), 1)
    c2_match = _on_court(_match(2), 2)
    positions = [
        MatchPosition(match=c1_match, position=0.0),
        MatchPosition(match=c2_match, position=0.0),
    ]

    await reorder_all_matches(_tournament(), positions)

    by_court = {call[0]: call for call in capture_sql_calls}
    assert by_court[CourtId(1)] == (CourtId(1), T0, c1_match.id)
    assert by_court[CourtId(2)] == (CourtId(2), T0, c2_match.id)


async def test_reorder_empty_input_is_noop(capture_sql_calls: list[SqlCall]) -> None:
    await reorder_all_matches(_tournament(), [])
    assert capture_sql_calls == []


async def test_reorder_skips_matches_without_court(
    capture_sql_calls: list[SqlCall],
) -> None:
    """Matches with court_id=None (unscheduled) are ignored."""
    with_court = _on_court(_match(1), 1)
    no_court = _match(2)  # court_id is None
    positions = [
        MatchPosition(match=with_court, position=0.0),
        MatchPosition(match=no_court, position=1.0),
    ]

    await reorder_all_matches(_tournament(), positions)

    assert capture_sql_calls == [(CourtId(1), T0, with_court.id)]


# ── Referee assignment helpers ────────────────────────────────────────────────


def _tournament_with_referees() -> Tournament:
    data = {**DUMMY_TOURNAMENT.model_dump(), "referees_enabled": True}
    return Tournament(**data, id=TournamentId(-1))


def _team(team_id: int, level_id: LevelId | None = None) -> Team:
    return Team(
        id=TeamId(team_id),
        created=T0,
        name=f"Team {team_id}",
        tournament_id=TournamentId(-1),
        active=True,
        level_id=level_id,
    )


def _final_input(
    input_id: int,
    team_id: int,
    level_id: LevelId | None = None,
    stage_item_id: int = -1,
) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(input_id),
        slot=1,
        tournament_id=TournamentId(-1),
        stage_item_id=StageItemId(stage_item_id),
        team_id=TeamId(team_id),
        team=_team(team_id, level_id),
    )


def _match_with_teams(
    id_: int,
    team_a_id: int,
    team_b_id: int,
    level_id: LevelId | None = None,
) -> MatchWithDetails:
    """Match with two defined teams (StageItemInputFinal) for referee tests."""
    inp_a = _final_input(id_ * 10 + 1, team_a_id, level_id)
    inp_b = _final_input(id_ * 10 + 2, team_b_id, level_id)
    return MatchWithDetails(
        id=MatchId(id_),
        created=T0,
        duration_minutes=DURATION,
        round_id=RoundId(id_),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
        stage_item_input1_id=inp_a.id,
        stage_item_input2_id=inp_b.id,
        stage_item_input1=inp_a,
        stage_item_input2=inp_b,
    )


def _stage_with_inputs(
    stage_id: int,
    matches: list[MatchWithDetails],
    inputs: list[StageItemInputFinal],
    level_id: LevelId | None = None,
) -> StageWithStageItems:
    """Stage with one stage item, the given matches, and explicit team inputs."""
    return _stage_with_rounds(
        stage_id,
        [[matches]],
        level_id=level_id,
        inputs_per_item=[list(inputs)],
    )


def _referee(team_id: int) -> Referee:
    return Referee(
        id=RefereeId(team_id),
        tournament_id=TournamentId(-1),
        team_id=TeamId(team_id),
        created=T0,
    )


def _match_with_referee(match: MatchWithDetails, team_id: int) -> MatchWithDetails:
    ref = _referee(team_id)
    return match.model_copy(update={"referee": ref, "referee_id": ref.id})


# ── Referee assignment: level restriction ─────────────────────────────────────


def test_referee_only_assigned_to_teams_of_own_level() -> None:
    """A team is only a candidate for matches of its own level."""
    level_a = LevelId(1)
    level_b = LevelId(2)
    # Teams 1,2 play in level A; team 3 is in level B
    m = _match_with_teams(1, 1, 2, level_a)
    inp_3 = _final_input(99, 3, level_b)
    stages = [
        _stage_with_inputs(
            1,
            [m],
            [_final_input(11, 1, level_a), _final_input(12, 2, level_a), inp_3],
            level_id=level_a,
        )
    ]
    tournament = _tournament_with_referees()

    ops = build_schedule_plan(stages, [_court(1)], tournament)

    assert len(ops) == 1
    # Team 3 is level_b, match is level_a → should NOT be assigned
    assert ops[0].referee_team_id != TeamId(3)
    # Teams 1 and 2 play in the match → should NOT be assigned either
    assert ops[0].referee_team_id not in (TeamId(1), TeamId(2))
    # No eligible referee → left unassigned
    assert ops[0].referee_team_id is None


def test_referee_not_assigned_to_playing_team() -> None:
    """A team playing in a match is never chosen as its referee."""
    level = LevelId(1)
    # Teams 1,2 play match 1; team 3 is the only referee candidate
    m = _match_with_teams(1, 1, 2, level)
    stages = [
        _stage_with_inputs(
            1,
            [m],
            [_final_input(11, 1, level), _final_input(12, 2, level), _final_input(13, 3, level)],
            level_id=level,
        )
    ]
    tournament = _tournament_with_referees()

    ops = build_schedule_plan(stages, [_court(1)], tournament)

    assert len(ops) == 1
    assert ops[0].referee_team_id == TeamId(3)


# ── Referee assignment: no-overlap (play vs referee) ─────────────────────────


def test_referee_not_assigned_when_playing_overlapping_match() -> None:
    """A team assigned as referee cannot simultaneously play another match."""
    level = LevelId(1)
    # Two matches: m1 (teams 1 vs 2) and m2 (teams 3 vs 4). Both at same time on different courts.
    # Teams 5,6 are referee candidates for both. A team can only referee ONE of the two.
    m1 = _match_with_teams(1, 1, 2, level)
    m2 = _match_with_teams(2, 3, 4, level)
    inputs = [
        _final_input(11, 1, level),
        _final_input(12, 2, level),
        _final_input(13, 3, level),
        _final_input(14, 4, level),
        _final_input(15, 5, level),
        _final_input(16, 6, level),
    ]
    stages = [_stage_with_inputs(1, [m1, m2], inputs, level_id=level)]
    tournament = _tournament_with_referees()

    ops = build_schedule_plan(stages, [_court(1), _court(2)], tournament)

    assert len(ops) == 2
    op_by_id = {op.match.id: op for op in ops}

    # Find matches that overlap in time
    overlapping_pairs = [
        (op_by_id[m1.id], op_by_id[m2.id])
        for op in ops
        if op_by_id[m1.id].start_time == op_by_id[m2.id].start_time
    ]
    if overlapping_pairs:
        op1, op2 = overlapping_pairs[0]
        # The same team must not referee both overlapping matches
        assert op1.referee_team_id != op2.referee_team_id or (
            op1.referee_team_id is None and op2.referee_team_id is None
        )


def test_referee_team_never_plays_and_referees_same_time_window() -> None:
    """If team 3 plays in m2, it must not be assigned to referee m1 if they overlap."""
    level = LevelId(1)
    # m1: teams 1 vs 2; m2: teams 3 vs 4 — both on 1 court = sequential
    # Team 5 is the extra referee candidate.
    m1 = _match_with_teams(1, 1, 2, level)
    m2 = _match_with_teams(2, 3, 4, level)
    inputs = [
        _final_input(11, 1, level),
        _final_input(12, 2, level),
        _final_input(13, 3, level),
        _final_input(14, 4, level),
        _final_input(15, 5, level),
    ]
    stages = [_stage_with_inputs(1, [m1, m2], inputs, level_id=level)]
    tournament = _tournament_with_referees()

    ops = build_schedule_plan(stages, [_court(1)], tournament)

    assert len(ops) == 2
    op_by_id = {op.match.id: op for op in ops}
    op1, op2 = op_by_id[MatchId(1)], op_by_id[MatchId(2)]
    end1 = op1.start_time + timedelta(minutes=DURATION)
    end2 = op2.start_time + timedelta(minutes=DURATION)

    # Check each op: if it overlaps with a match where the referee is playing, that's a conflict
    if op1.start_time < end2 and op2.start_time < end1:
        # They overlap (shouldn't happen on 1 court, but check anyway)
        if op1.referee_team_id == TeamId(3):
            assert False, "Team 3 plays m2 and should not referee m1 if they overlap"
        if op2.referee_team_id == TeamId(1) or op2.referee_team_id == TeamId(2):
            assert False, "Teams 1/2 play m1 and should not referee m2 if they overlap"
    # On one court matches are sequential → no overlap → any eligible team is fine


# ── Referee assignment: balanced load ─────────────────────────────────────────


def test_referee_load_is_balanced_across_eligible_teams() -> None:
    """Referee assignments are spread across all eligible teams (max - min load <= 1)."""
    level = LevelId(1)
    # 4 matches: teams 1-8 playing (pairs), teams 9,10 are referee-only candidates
    matches = [_match_with_teams(i, i * 2 - 1, i * 2, level) for i in range(1, 5)]
    inputs = [_final_input(i * 10, i, level) for i in range(1, 11)]
    stages = [_stage_with_inputs(1, matches, inputs, level_id=level)]
    tournament = _tournament_with_referees()

    ops = build_schedule_plan(stages, [_court(1), _court(2)], tournament)

    assert len(ops) == 4
    load: dict[TeamId, int] = defaultdict(int)
    for op in ops:
        if op.referee_team_id is not None:
            load[op.referee_team_id] += 1

    if load:
        assert max(load.values()) - min(load.values()) <= 1


# ── Referee assignment: preserve existing assignments ─────────────────────────


def test_existing_referee_assignment_not_overwritten() -> None:
    """Matches that already have a referee are left untouched."""
    level = LevelId(1)
    m = _match_with_teams(1, 1, 2, level)
    m_with_ref = _match_with_referee(m, team_id=3)
    inputs = [
        _final_input(11, 1, level),
        _final_input(12, 2, level),
        _final_input(13, 3, level),
        _final_input(14, 4, level),
    ]
    stages = [_stage_with_inputs(1, [m_with_ref], inputs, level_id=level)]
    tournament = _tournament_with_referees()

    ops = build_schedule_plan(stages, [_court(1)], tournament)

    assert len(ops) == 1
    # The solver should not produce a referee_team_id for a match that already has one
    assert ops[0].referee_team_id is None


def test_free_text_referee_match_not_overwritten() -> None:
    """A match with a free-text referee (no team_id) is also left as-is."""
    level = LevelId(1)
    m = _match_with_teams(1, 1, 2, level)
    free_text_ref = Referee(
        id=RefereeId(99),
        tournament_id=TournamentId(-1),
        name="External Ref",
        created=T0,
    )
    m_with_ref = m.model_copy(update={"referee": free_text_ref, "referee_id": free_text_ref.id})
    inputs = [_final_input(11, 1, level), _final_input(12, 2, level), _final_input(13, 3, level)]
    stages = [_stage_with_inputs(1, [m_with_ref], inputs, level_id=level)]
    tournament = _tournament_with_referees()

    ops = build_schedule_plan(stages, [_court(1)], tournament)

    assert len(ops) == 1
    assert ops[0].referee_team_id is None


# ── Referee assignment: no rest penalty ───────────────────────────────────────


def test_refereeing_does_not_add_rest_penalty() -> None:
    """Assigning a team as referee adjacent to its own match does not change the rest objective.

    Team 1 plays match m1 and another team referees m2 immediately before m1. The rest
    penalty should be the same regardless of who referees m2 — refereeing itself adds
    no shortfall.
    """
    level = LevelId(1)
    # m1: team 1 vs 2; m2: team 3 vs 4 — team 1 is an eligible referee for m2
    m1 = _match_with_teams(1, 1, 2, level)
    m2 = _match_with_teams(2, 3, 4, level)
    inputs = [
        _final_input(11, 1, level),
        _final_input(12, 2, level),
        _final_input(13, 3, level),
        _final_input(14, 4, level),
    ]

    # With referees_enabled: team 1 might referee m2
    stages_on = [_stage_with_inputs(1, [m1, m2], inputs, level_id=level)]
    ops_on = build_schedule_plan(stages_on, [_court(1)], _tournament_with_referees())

    # Without referees: baseline schedule
    stages_off = [_stage_with_inputs(1, [m1, m2], inputs, level_id=level)]
    ops_off = build_schedule_plan(stages_off, [_court(1)], _tournament())

    # Both should schedule the same times (rest penalty unchanged by refereeing)
    times_on = sorted(op.start_time for op in ops_on)
    times_off = sorted(op.start_time for op in ops_off)
    assert times_on == times_off


# ── Referee assignment: feature flag ──────────────────────────────────────────


def test_referees_disabled_produces_no_referee_assignments() -> None:
    """When referees_enabled=False, no referee_team_id is set on any operation."""
    level = LevelId(1)
    m = _match_with_teams(1, 1, 2, level)
    inputs = [_final_input(11, 1, level), _final_input(12, 2, level), _final_input(13, 3, level)]
    stages = [_stage_with_inputs(1, [m], inputs, level_id=level)]

    ops = build_schedule_plan(stages, [_court(1)], _tournament())  # referees_enabled=False

    assert len(ops) == 1
    assert ops[0].referee_team_id is None


def test_no_eligible_referee_leaves_match_unassigned() -> None:
    """If all level-matching teams are playing in the match, the match stays unassigned."""
    level = LevelId(1)
    m = _match_with_teams(1, 1, 2, level)
    # Only teams 1 and 2 exist and both play in m → no candidate
    inputs = [_final_input(11, 1, level), _final_input(12, 2, level)]
    stages = [_stage_with_inputs(1, [m], inputs, level_id=level)]
    tournament = _tournament_with_referees()

    ops = build_schedule_plan(stages, [_court(1)], tournament)

    assert len(ops) == 1
    assert ops[0].referee_team_id is None


# ── build_referee_assignment_plan (assign-missing-only, schedule pinned) ─────


def _scheduled_match_with_teams(
    id_: int,
    team_a_id: int,
    team_b_id: int,
    level_id: LevelId | None = None,
    start_offset_minutes: int = 0,
    court_id: int = 1,
) -> MatchWithDetails:
    """Match with two defined teams, already scheduled at a fixed time on a court."""
    inp_a = _final_input(id_ * 10 + 1, team_a_id, level_id)
    inp_b = _final_input(id_ * 10 + 2, team_b_id, level_id)
    return MatchWithDetails(
        id=MatchId(id_),
        created=T0,
        duration_minutes=DURATION,
        round_id=RoundId(id_),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
        stage_item_input1_id=inp_a.id,
        stage_item_input2_id=inp_b.id,
        stage_item_input1=inp_a,
        stage_item_input2=inp_b,
        start_time=T0 + timedelta(minutes=start_offset_minutes),
        court_id=CourtId(court_id),
    )


def test_assign_referees_only_fills_missing_not_existing() -> None:
    """Only fills matches with no referee; never overwrites existing assignments."""
    level = LevelId(1)
    m1 = _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0)
    m2 = _scheduled_match_with_teams(2, 3, 4, level, start_offset_minutes=SLOT)
    m3 = _scheduled_match_with_teams(3, 5, 6, level, start_offset_minutes=2 * SLOT)
    m2_with_ref = _match_with_referee(m2, team_id=9)
    inputs = [_final_input(i * 10, i, level) for i in range(1, 11)]
    stages = [_stage_with_inputs(1, [m1, m2_with_ref, m3], inputs, level_id=level)]

    result = build_referee_assignment_plan(stages, _tournament_with_referees())

    assert MatchId(2) not in result, "Should not overwrite existing referee"
    assert MatchId(1) in result
    assert MatchId(3) in result


def test_assign_referees_schedule_unchanged() -> None:
    """Match court_id and start_time in the stage objects are untouched after the call."""
    level = LevelId(1)
    m = _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0, court_id=7)
    inputs = [_final_input(11, 1, level), _final_input(12, 2, level), _final_input(13, 3, level)]
    stages = [_stage_with_inputs(1, [m], inputs, level_id=level)]

    court_before = m.court_id
    time_before = m.start_time

    build_referee_assignment_plan(stages, _tournament_with_referees())

    # The match object in the stage is the same reference — verify it was not mutated
    match_after = stages[0].stage_items[0].rounds[0].matches[0]
    assert match_after.court_id == court_before
    assert match_after.start_time == time_before


def test_assign_referees_level_restriction() -> None:
    """Teams of a different level than the match are excluded as candidates."""
    level_a = LevelId(1)
    level_b = LevelId(2)
    m = _scheduled_match_with_teams(1, 1, 2, level_a, start_offset_minutes=0)
    inputs = [
        _final_input(11, 1, level_a),
        _final_input(12, 2, level_a),
        _final_input(13, 3, level_b),
    ]
    stages = [_stage_with_inputs(1, [m], inputs, level_id=level_a)]

    result = build_referee_assignment_plan(stages, _tournament_with_referees())

    assert result == {}


def test_assign_referees_excludes_playing_team() -> None:
    """A team playing in the match is not assigned as its referee."""
    level = LevelId(1)
    m1 = _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0)
    m2 = _scheduled_match_with_teams(2, 3, 4, level, start_offset_minutes=SLOT)
    inputs = [
        _final_input(11, 1, level),
        _final_input(12, 2, level),
        _final_input(13, 3, level),
        _final_input(14, 4, level),
        _final_input(15, 5, level),
    ]
    stages = [_stage_with_inputs(1, [m1, m2], inputs, level_id=level)]

    result = build_referee_assignment_plan(stages, _tournament_with_referees())

    assert result.get(MatchId(1)) not in (TeamId(1), TeamId(2))
    assert result.get(MatchId(2)) not in (TeamId(3), TeamId(4))


def test_assign_referees_excludes_team_playing_overlapping_match() -> None:
    """A team playing in a simultaneously-scheduled match cannot referee the other."""
    level = LevelId(1)
    m1 = _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0, court_id=1)
    m2 = _scheduled_match_with_teams(2, 3, 4, level, start_offset_minutes=0, court_id=2)
    inputs = [
        _final_input(11, 1, level),
        _final_input(12, 2, level),
        _final_input(13, 3, level),
        _final_input(14, 4, level),
        _final_input(15, 5, level),
        _final_input(16, 6, level),
    ]
    stages = [_stage_with_inputs(1, [m1, m2], inputs, level_id=level)]

    result = build_referee_assignment_plan(stages, _tournament_with_referees())

    if MatchId(1) in result and MatchId(2) in result:
        assert result[MatchId(1)] != result[MatchId(2)]


def test_assign_referees_no_candidate_leaves_match_unassigned() -> None:
    """A match is left unassigned when no eligible team is available; no error raised."""
    level = LevelId(1)
    m = _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0)
    inputs = [_final_input(11, 1, level), _final_input(12, 2, level)]
    stages = [_stage_with_inputs(1, [m], inputs, level_id=level)]

    result = build_referee_assignment_plan(stages, _tournament_with_referees())

    assert result == {}


def test_assign_referees_balanced_load() -> None:
    """Referee load is balanced across eligible teams (max − min ≤ 1)."""
    level = LevelId(1)
    matches = [
        _scheduled_match_with_teams(i, i * 2 - 1, i * 2, level, start_offset_minutes=(i - 1) * SLOT)
        for i in range(1, 5)
    ]
    inputs = [_final_input(i * 10, i, level) for i in range(1, 11)]
    stages = [_stage_with_inputs(1, matches, inputs, level_id=level)]

    result = build_referee_assignment_plan(stages, _tournament_with_referees())

    assert len(result) == 4
    load: dict[TeamId, int] = defaultdict(int)
    for team_id in result.values():
        load[team_id] += 1
    if load:
        assert max(load.values()) - min(load.values()) <= 1


def test_assign_referees_deterministic_tiebreak() -> None:
    """Repeated calls with the same inputs and fixed seed yield identical assignments."""
    level = LevelId(1)
    # 2 non-overlapping matches, 4 eligible teams — multiple balanced solutions exist,
    # so the tie-break (fixed solver seed) must select the same one every time.
    matches = [
        _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0, court_id=1),
        _scheduled_match_with_teams(2, 3, 4, level, start_offset_minutes=SLOT, court_id=1),
    ]
    inputs = [_final_input(i * 10, i, level) for i in range(1, 7)]
    stages = [_stage_with_inputs(1, matches, inputs, level_id=level)]
    tournament = _tournament_with_referees()

    result_a = build_referee_assignment_plan(stages, tournament)
    result_b = build_referee_assignment_plan(stages, tournament)

    assert result_a == result_b


def test_assign_referees_no_free_text() -> None:
    """All result values are integer TeamIds, never free-text strings."""
    level = LevelId(1)
    m = _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0)
    inputs = [_final_input(11, 1, level), _final_input(12, 2, level), _final_input(13, 3, level)]
    stages = [_stage_with_inputs(1, [m], inputs, level_id=level)]

    result = build_referee_assignment_plan(stages, _tournament_with_referees())

    for team_id in result.values():
        assert isinstance(team_id, int)


def test_assign_referees_disabled_returns_empty() -> None:
    """When referees_enabled is False the function returns an empty dict immediately."""
    level = LevelId(1)
    m = _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0)
    inputs = [_final_input(11, 1, level), _final_input(12, 2, level), _final_input(13, 3, level)]
    stages = [_stage_with_inputs(1, [m], inputs, level_id=level)]

    result = build_referee_assignment_plan(stages, _tournament())

    assert result == {}


def test_assign_referees_skips_unscheduled_matches() -> None:
    """Unscheduled matches (no start_time / court_id) are not considered."""
    level = LevelId(1)
    m_scheduled = _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0)
    m_unscheduled = _match_with_teams(2, 3, 4, level)
    inputs = [
        _final_input(11, 1, level),
        _final_input(12, 2, level),
        _final_input(13, 3, level),
        _final_input(14, 4, level),
        _final_input(15, 5, level),
    ]
    stages = [_stage_with_inputs(1, [m_scheduled, m_unscheduled], inputs, level_id=level)]

    result = build_referee_assignment_plan(stages, _tournament_with_referees())

    assert MatchId(2) not in result


def test_assign_referees_existing_counts_toward_fairness() -> None:
    """Existing referee assignments are counted toward the fairness balance."""
    level = LevelId(1)
    m1 = _scheduled_match_with_teams(1, 1, 2, level, start_offset_minutes=0)
    m2 = _scheduled_match_with_teams(2, 3, 4, level, start_offset_minutes=SLOT)
    m3 = _scheduled_match_with_teams(3, 5, 6, level, start_offset_minutes=2 * SLOT)
    m1_with_ref = _match_with_referee(m1, team_id=9)
    inputs = [_final_input(i * 10, i, level) for i in range(1, 11)]
    stages = [_stage_with_inputs(1, [m1_with_ref, m2, m3], inputs, level_id=level)]

    result = build_referee_assignment_plan(stages, _tournament_with_referees())

    assert MatchId(1) not in result
    load: dict[TeamId, int] = defaultdict(int)
    load[TeamId(9)] = 1  # already assigned
    for team_id in result.values():
        load[team_id] += 1
    if load:
        assert max(load.values()) - min(load.values()) <= 1
