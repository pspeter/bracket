from collections import defaultdict
from datetime import timedelta

import pytest
from heliclockter import datetime_utc

from bracket.logic.planning import matches as planning_matches
from bracket.logic.planning.matches import (
    MatchPosition,
    build_schedule_plan,
    reorder_all_matches,
)
from bracket.models.db.court import Court
from bracket.models.db.match import MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.stage_item import StageType
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
    TournamentId,
)

T0 = DUMMY_MOCK_TIME
DURATION = DUMMY_TOURNAMENT.duration_minutes  # 10
MARGIN = DUMMY_TOURNAMENT.margin_minutes  # 5
SLOT = DURATION + MARGIN  # 15 minutes per match
SqlCall = tuple[CourtId, datetime_utc, int, MatchId]


def _match(id_: int) -> MatchWithDetails:
    return MatchWithDetails(
        id=MatchId(id_),
        created=T0,
        duration_minutes=DURATION,
        margin_minutes=MARGIN,
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


# ── Cross-stage-item interleaving on one court ───────────────────────────────


def test_one_court_two_equal_sis_alternate() -> None:
    """1 court, 2 stage items × 2 matches → matches alternate by stage item."""
    a1, a2 = _match(1), _match(2)  # SI "Group 0"
    b1, b2 = _match(3), _match(4)  # SI "Group 1"
    stages = [_stage(1, [[a1, a2], [b1, b2]])]
    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    assert len(ops) == 4
    assert all(op.court_id == CourtId(1) for op in ops)
    ids_by_position = [op.match.id for op in sorted(ops, key=lambda o: o.position)]
    assert ids_by_position == [a1.id, b1.id, a2.id, b2.id], (
        f"Expected alternating SI pattern A,B,A,B but got {ids_by_position}"
    )


def test_two_courts_two_levels_two_sis_each_no_level_waits() -> None:
    """
    The original bug: 2 courts, 2 levels × 2 stage items × 2 matches.
    Before the fix, C1 ran all of Level A's SIs before any of Level B's.
    Now both levels must start at T0, and each court should interleave levels.
    """
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

    assert len(ops) == 8

    level_a_ids = {m.id for m in a1 + a2}
    level_b_ids = {m.id for m in b1 + b2}

    # Both levels must have at least one match scheduled at T0
    levels_at_t0 = set()
    for op in ops:
        if op.start_time == T0:
            if op.match.id in level_a_ids:
                levels_at_t0.add(level_a)
            elif op.match.id in level_b_ids:
                levels_at_t0.add(level_b)
    assert levels_at_t0 == {level_a, level_b}, f"Both levels must start at T0, got {levels_at_t0}"

    # Each court gets one SI from each level and alternates them.
    for court_id in (CourtId(1), CourtId(2)):
        court_seq = [
            op.match.id for op in sorted(ops, key=lambda o: o.position) if op.court_id == court_id
        ]
        level_seq = [
            level_a if mid in level_a_ids else level_b if mid in level_b_ids else None
            for mid in court_seq
        ]
        assert level_seq.count(level_a) == 2
        assert level_seq.count(level_b) == 2
        assert level_seq in (
            [level_a, level_b, level_a, level_b],
            [level_b, level_a, level_b, level_a],
        )


def test_two_courts_two_equal_sis_stay_on_separate_courts() -> None:
    """2 courts, 2 equal SIs → each SI stays on its own court (no within-court interleave)."""
    a_matches = [_match(10), _match(11), _match(12)]
    b_matches = [_match(20), _match(21), _match(22)]
    stages = [_stage(1, [a_matches, b_matches])]
    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    assert len(ops) == 6
    a_ids = {m.id for m in a_matches}
    b_ids = {m.id for m in b_matches}

    by_court: dict[CourtId, set[MatchId]] = defaultdict(set)
    for op in ops:
        by_court[op.court_id].add(op.match.id)

    # Each court must contain only one SI's matches
    courts_with_a = [c for c, ids in by_court.items() if ids & a_ids]
    courts_with_b = [c for c, ids in by_court.items() if ids & b_ids]
    assert len(courts_with_a) == 1, f"SI A split across courts: {courts_with_a}"
    assert len(courts_with_b) == 1, f"SI B split across courts: {courts_with_b}"
    assert courts_with_a != courts_with_b, "Both SIs on the same court"


def test_one_court_unequal_sis_interleave_smoothly() -> None:
    """1 court, SI sizes [4, 2] → smoothly interleaved, no 3 consecutive larger-SI matches."""
    a_matches = [_match(10 + i) for i in range(4)]  # SI "Group 0", size 4
    b_matches = [_match(20 + i) for i in range(2)]  # SI "Group 1", size 2
    stages = [_stage(1, [a_matches, b_matches])]
    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    assert len(ops) == 6
    a_ids = {m.id for m in a_matches}
    b_ids = {m.id for m in b_matches}
    sequence = [op.match.id for op in sorted(ops, key=lambda o: o.position)]

    # No 3 consecutive matches from the larger SI (smooth distribution)
    for i in range(len(sequence) - 2):
        from_a = sum(1 for mid in sequence[i : i + 3] if mid in a_ids)
        assert from_a < 3, f"3 consecutive A matches at index {i}: {sequence}"

    # B matches not bunched — at least one in first half, one in second half
    b_positions = [i for i, mid in enumerate(sequence) if mid in b_ids]
    assert any(p < 3 for p in b_positions), f"No B in first half: {b_positions}"
    assert any(p >= 3 for p in b_positions), f"No B in second half: {b_positions}"


def test_two_courts_imbalanced_sis_split_to_tight_loads() -> None:
    """2 courts, SI sizes [8, 2, 2] -> smart split balances court loads within one match."""
    large = [_match(10 + i) for i in range(8)]
    small_a = [_match(20 + i) for i in range(2)]
    small_b = [_match(30 + i) for i in range(2)]
    stages = [_stage(1, [large, small_a, small_b])]
    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    assert len(ops) == 12
    by_court: dict[CourtId, int] = defaultdict(int)
    large_courts: set[CourtId] = set()
    large_ids = {match.id for match in large}
    for op in ops:
        by_court[op.court_id] += 1
        if op.match.id in large_ids:
            large_courts.add(op.court_id)

    assert max(by_court.values()) - min(by_court.values()) <= 1
    assert large_courts == {CourtId(1), CourtId(2)}


def test_two_courts_multi_level_imbalanced_sis_split_to_tight_loads() -> None:
    """Smart split still applies when active levels have uneven current-stage SI sizes."""
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

    assert len(ops) == 12
    by_court: dict[CourtId, int] = defaultdict(int)
    large_courts: set[CourtId] = set()
    large_ids = {match.id for match in large}
    for op in ops:
        by_court[op.court_id] += 1
        if op.match.id in large_ids:
            large_courts.add(op.court_id)

    assert max(by_court.values()) - min(by_court.values()) <= 1
    assert large_courts == {CourtId(1), CourtId(2)}


def test_round_order_preserved_within_interleaved_stage_item() -> None:
    """An SI's round 1 matches stay before its round 2 matches while interleaving."""
    a_r1 = [_match(10), _match(11)]
    a_r2 = [_match(12), _match(13)]
    b_matches = [_match(20 + i) for i in range(4)]
    stages = [_stage_with_rounds(1, [[a_r1, a_r2], [b_matches]])]
    ops = build_schedule_plan(stages, [_court(1)], _tournament())

    positions = {op.match.id: op.position for op in ops}
    latest_a_r1 = max(positions[match.id] for match in a_r1)
    earliest_a_r2 = min(positions[match.id] for match in a_r2)

    assert latest_a_r1 < earliest_a_r2


# ── Single-level stage boundaries ────────────────────────────────────────────


def test_single_level_two_stages_stage_boundary_respected() -> None:
    """Stage 2 starts only after all Stage 1 matches have finished across all courts."""
    m1, m2, m3, m4 = _match(1), _match(2), _match(3), _match(4)
    # Stage 1: 1 item with 2 matches; after rebalancing → 1 per court
    # Stage 2: 1 item with 2 matches
    stages = [
        _stage(1, [[m1, m2]]),  # level_id=None
        _stage(2, [[m3, m4]]),
    ]
    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    assert len(ops) == 4

    stage1_match_ids = {m1.id, m2.id}
    stage2_match_ids = {m3.id, m4.id}

    s1_end = max(
        op.start_time + timedelta(minutes=SLOT) for op in ops if op.match.id in stage1_match_ids
    )
    s2_starts = [op.start_time for op in ops if op.match.id in stage2_match_ids]

    for start in s2_starts:
        assert start >= s1_end, "Stage 2 must not start before Stage 1 fully ends"


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


def test_level_a_stage2_starts_before_level_b_stage1_finishes() -> None:
    """
    Level A has a short Stage 1 (1 quick match) and a Stage 2.
    Level B has a long Stage 1 (many matches).
    Level A's Stage 2 must be able to start on a free court before Level B's Stage 1 finishes,
    demonstrating per-level independence of stage boundaries.
    """
    level_a = LevelId(1)
    level_b = LevelId(2)
    # Level A: Stage 1 = 1 match, Stage 2 = 1 match
    a_s1 = _match(1)
    a_s2 = _match(2)
    # Level B: Stage 1 = 4 matches (will occupy court 2 for 4 slots)
    b_s1 = [_match(10 + i) for i in range(4)]

    stages = [
        _stage(1, [[a_s1]], level_id=level_a),  # Level A Stage 1
        _stage(2, [[a_s2]], level_id=level_a),  # Level A Stage 2
        _stage(3, [b_s1], level_id=level_b),  # Level B Stage 1
    ]
    ops = build_schedule_plan(stages, [_court(1), _court(2)], _tournament())

    assert len(ops) == 6

    a_s1_end = next(op.start_time + timedelta(minutes=SLOT) for op in ops if op.match.id == a_s1.id)
    a_s2_start = next(op.start_time for op in ops if op.match.id == a_s2.id)
    b_s1_end = max(
        op.start_time + timedelta(minutes=SLOT) for op in ops if op.match.id in {m.id for m in b_s1}
    )

    # Level A boundary: Stage 2 must start after Stage 1
    assert a_s2_start >= a_s1_end, "Level A Stage 2 must follow Level A Stage 1"

    # Per-level independence: Level A Stage 2 can start before Level B Stage 1 finishes
    assert a_s2_start < b_s1_end, (
        "Level A Stage 2 should start before Level B Stage 1 finishes "
        "(different levels don't block each other)"
    )


def test_level_b_fills_courts_while_level_a_is_between_stages() -> None:
    """
    Level A: Stage 1 (1 match on C1), Stage 2 (1 match).
    Level B: Stage 1 (4 matches).
    After Level A Stage 1 finishes, courts are busy with Level B matches.
    Level A Stage 2 runs when courts are available — courts aren't idle during the gap.
    """
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

    assert len(ops) == 6

    # Every court's timeline should be contiguous — no court is idle while any match is waiting
    court_times: dict[CourtId, list[tuple[datetime_utc, datetime_utc]]] = defaultdict(list)
    for op in ops:
        court_times[op.court_id].append((op.start_time, op.start_time + timedelta(minutes=SLOT)))

    for court_id, slots in court_times.items():
        slots.sort()
        for i in range(1, len(slots)):
            # No gap between consecutive matches on the same court
            assert slots[i][0] == slots[i - 1][1], (
                f"Court {court_id} has an idle gap between matches: "
                f"{slots[i - 1][1]} → {slots[i][0]}"
            )


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
        margin_minutes=MARGIN,
        round_id=RoundId(99),
        start_time=T0,
        position_in_schedule=0,
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


# ── reorder_all_matches ──────────────────────────────────────────────────────


def _on_court(match: MatchWithDetails, court_id: int) -> MatchWithDetails:
    return match.model_copy(update={"court_id": CourtId(court_id)})


@pytest.fixture
def capture_sql_calls(monkeypatch: pytest.MonkeyPatch) -> list[SqlCall]:
    """Replace the DB-writing helper with a list recorder."""
    calls: list[SqlCall] = []

    async def fake_reschedule(court_id, start_time, position, match, tournament):  # type: ignore[no-untyped-def]
        calls.append((court_id, start_time, position, match.id))

    monkeypatch.setattr(
        planning_matches,
        "sql_reschedule_match_and_determine_duration_and_margin",
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
        (CourtId(1), T0, 0, level_b.id),
        (CourtId(1), T0 + timedelta(minutes=SLOT), 1, level_a.id),
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
        (CourtId(1), T0, 0, m1.id),
        (CourtId(1), T0 + timedelta(minutes=SLOT), 1, m2.id),
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
    assert by_court[CourtId(1)] == (CourtId(1), T0, 0, c1_match.id)
    assert by_court[CourtId(2)] == (CourtId(2), T0, 0, c2_match.id)


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

    assert capture_sql_calls == [(CourtId(1), T0, 0, with_court.id)]
