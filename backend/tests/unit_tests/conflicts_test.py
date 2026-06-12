from datetime import timedelta

import pytest

from bracket.logic.planning.conflicts import get_conflicting_matches, matches_overlap
from bracket.models.db.util import StageWithStageItems
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.id_types import StageId, TournamentId
from tests.integration_tests.mocks import MOCK_NOW
from tests.unit_tests.mocks import (
    get_2_definitive_matches_mock,
    get_one_round_with_two_definitive_matches,
    get_stage_item_inputs_mock,
    get_stage_item_mock,
    make_simple_match,
)

T = DUMMY_MOCK_TIME


def _make_stage(
    match1_start: object, match2_start: object, **kwargs: object
) -> StageWithStageItems:
    tournament_id = TournamentId(-1)
    stage_item_inputs = get_stage_item_inputs_mock(tournament_id)
    match1, match2 = get_2_definitive_matches_mock(
        stage_item_inputs,
        match1_start_time=match1_start,  # type: ignore[arg-type]
        match2_start_time=match2_start,  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )
    rounds = get_one_round_with_two_definitive_matches(match1, match2)
    return StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[get_stage_item_mock(stage_item_inputs, [rounds])],
    )


# ---------------------------------------------------------------------------
# matches_overlap unit tests
# ---------------------------------------------------------------------------

_OVERLAP_CASES: list[tuple[object, int, int, object, int, int, bool]] = [
    # Partial overlap, match1 first
    (T, 15, 0, T + timedelta(minutes=5), 15, 0, True),
    # Partial overlap, match2 first (symmetric)
    (T + timedelta(minutes=5), 15, 0, T, 15, 0, True),
    # match1 fully contains match2
    (T, 30, 0, T + timedelta(minutes=5), 10, 0, True),
    # match2 fully contains match1 (symmetric)
    (T + timedelta(minutes=5), 10, 0, T, 30, 0, True),
    # Identical intervals
    (T, 15, 0, T, 15, 0, True),
    # Overlap only within margin window (durations disjoint, margins overlap)
    (T, 10, 5, T + timedelta(minutes=12), 10, 5, True),
    # Symmetric
    (T + timedelta(minutes=12), 10, 5, T, 10, 5, True),
    # Back-to-back: end1 == start2 — not a conflict (half-open intervals)
    (T, 15, 0, T + timedelta(minutes=15), 10, 0, False),
    # Back-to-back reversed (symmetric)
    (T + timedelta(minutes=15), 10, 0, T, 15, 0, False),
    # Disjoint with a gap
    (T, 10, 0, T + timedelta(minutes=20), 10, 0, False),
    # Symmetric
    (T + timedelta(minutes=20), 10, 0, T, 10, 0, False),
    # match1 start_time is None
    (None, 15, 0, T, 15, 0, False),
    # match2 start_time is None
    (T, 15, 0, None, 15, 0, False),
    # Both start_time are None
    (None, 15, 0, None, 15, 0, False),
]


@pytest.mark.parametrize("start1,dur1,margin1,start2,dur2,margin2,expected", _OVERLAP_CASES)
def test_matches_overlap(
    start1: object,
    dur1: int,
    margin1: int,
    start2: object,
    dur2: int,
    margin2: int,
    expected: bool,
) -> None:
    m1 = make_simple_match(start1, dur1, margin1)  # type: ignore[arg-type]
    m2 = make_simple_match(start2, dur2, margin2)  # type: ignore[arg-type]
    assert matches_overlap(m1, m2) == expected


# ---------------------------------------------------------------------------
# get_conflicting_matches tests
# ---------------------------------------------------------------------------


def test_get_conflicting_matches_conflicts_to_set() -> None:
    """Identical start times → both matches flagged on their shared input side."""
    stage = _make_stage(T, T)
    assert get_conflicting_matches([stage]) == ({-1: [True, False], -2: [True, False]}, set())


def test_get_conflicting_matches_partial_overlap_is_detected() -> None:
    """
    Staggered starts that partially overlap must be flagged.

    match1: T → T+105 min, match2: T+60 min → T+165 min  (45-min overlap)
    This is the bug scenario from issue #64.
    """
    stage = _make_stage(T, T + timedelta(hours=1))
    assert get_conflicting_matches([stage]) == ({-1: [True, False], -2: [True, False]}, set())


def test_get_conflicting_matches_conflicts_to_clear() -> None:
    """
    Matches separated by more than their combined duration+margin do not conflict.

    Each match is 90+15=105 min; a 2-hour (120 min) gap between starts means no overlap.
    """
    stage = _make_stage(T, T + timedelta(hours=2))
    assert get_conflicting_matches([stage]) == ({}, {-1, -2})


def test_get_conflicting_matches_back_to_back_no_conflict() -> None:
    """Back-to-back matches (end1 == start2) must not be flagged."""
    stage = _make_stage(T, T + timedelta(minutes=105))  # 90+15=105 min
    assert get_conflicting_matches([stage]) == ({}, {-1, -2})
