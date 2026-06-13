from collections import defaultdict
from datetime import timedelta

import pytest
from heliclockter import datetime_utc

from bracket.logic.planning import matches as planning_matches
from bracket.logic.planning.matches import (
    MatchPosition,
    ScheduleOperation,
    build_schedule_plan,
    reorder_all_matches,
)
from bracket.models.db.court import Court
from bracket.models.db.match import MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputTentative
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_TOURNAMENT
from bracket.utils.id_types import (
    CourtId,
    LevelId,
    MatchId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
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
) -> StageWithStageItems:
    return _stage_with_rounds(
        stage_id,
        [[matches] for matches in matches_per_item],
        level_id=level_id,
    )


def _stage_with_rounds(
    stage_id: int,
    rounds_per_item: list[list[list[MatchWithDetails]]],
    level_id: LevelId | None = None,
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
                inputs=[],
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
