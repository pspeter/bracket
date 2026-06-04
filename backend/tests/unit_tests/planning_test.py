from collections import defaultdict
from datetime import timedelta

from bracket.logic.planning.matches import build_schedule_plan
from bracket.models.db.court import Court
from bracket.models.db.match import MatchWithDetails
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
    stage_items = []
    for item_idx, matches in enumerate(matches_per_item):
        item_id = stage_id * 100 + item_idx
        round_ = RoundWithMatches(
            id=RoundId(item_id),
            matches=matches,
            stage_item_id=StageItemId(item_id),
            created=T0,
            is_draft=False,
            name="",
        )
        stage_items.append(
            StageItemWithRounds(
                id=StageItemId(item_id),
                stage_id=StageId(stage_id),
                rounds=[round_],
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
    court_times: dict[CourtId, list[tuple]] = defaultdict(list)
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
