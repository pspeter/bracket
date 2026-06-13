from datetime import timedelta

import pytest

from bracket.logic.planning.conflicts import (
    get_conflicting_matches,
    get_match_conflict_flags,
    matches_overlap,
)
from bracket.models.db.match import MatchState, MatchWithDetailsDefinitive
from bracket.models.db.stage_item_inputs import StageItemInputTentative
from bracket.models.db.util import RoundWithMatches, StageWithStageItems
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.id_types import (
    CourtId,
    MatchId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TournamentId,
)
from tests.integration_tests.mocks import MOCK_NOW
from tests.unit_tests.mocks import (
    get_2_definitive_and_2_tentative_matches_mock,
    get_2_definitive_matches_mock,
    get_one_round_with_two_definitive_matches,
    get_stage_item_inputs_mock,
    get_stage_item_mock,
    get_two_round_with_one_tentative_match_each,
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
    # Overlap only within the default break, not the playing interval
    (T, 10, 5, T + timedelta(minutes=12), 10, 5, False),
    # Symmetric
    (T + timedelta(minutes=12), 10, 5, T, 10, 5, False),
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
    Matches separated by more than their duration do not conflict.

    Each match is 90 min; a 2-hour (120 min) gap between starts means no overlap.
    """
    stage = _make_stage(T, T + timedelta(hours=2))
    assert get_conflicting_matches([stage]) == ({}, {-1, -2})


def test_get_conflicting_matches_back_to_back_no_conflict() -> None:
    """Back-to-back matches (end1 == start2) must not be flagged."""
    stage = _make_stage(T, T + timedelta(minutes=90))
    assert get_conflicting_matches([stage]) == ({}, {-1, -2})


def test_get_match_conflict_flags_marks_match_before_winner_feeder() -> None:
    """A match that starts before one of its winner-of feeder matches ends is flagged."""
    tournament_id = TournamentId(-1)
    stage_item_inputs = get_stage_item_inputs_mock(tournament_id)
    feeder1, feeder2, final, consolation = get_2_definitive_and_2_tentative_matches_mock(
        stage_item_inputs
    )
    final = final.model_copy(
        update={
            "court_id": CourtId(-3),
            "start_time": T + timedelta(minutes=30),
        }
    )
    first_round = get_one_round_with_two_definitive_matches(feeder1, feeder2)
    final_round, _ = get_two_round_with_one_tentative_match_each(final, consolation)
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[get_stage_item_mock(stage_item_inputs, [first_round, final_round])],
    )

    flags = get_match_conflict_flags([stage], default_break_minutes=5)

    assert flags[final.id].precedence_conflict is True
    assert flags[feeder1.id].precedence_conflict is False
    assert flags[feeder2.id].precedence_conflict is False


def test_get_match_conflict_flags_marks_match_before_feeding_stage_item_finishes() -> None:
    """A match using a previous stage item's ranking waits for that group's last match."""
    tournament_id = TournamentId(-1)
    source_inputs = get_stage_item_inputs_mock(tournament_id)
    source_match1, source_match2 = get_2_definitive_matches_mock(
        source_inputs,
        match1_start_time=T,
        match2_start_time=T + timedelta(minutes=10),
        duration_minutes=10,
    )
    source_round = get_one_round_with_two_definitive_matches(source_match1, source_match2)
    source_stage_item = get_stage_item_mock(source_inputs, [source_round])

    target_input = StageItemInputTentative(
        id=StageItemInputId(-10),
        slot=1,
        tournament_id=tournament_id,
        stage_item_id=StageItemId(-2),
        winner_from_stage_item_id=source_stage_item.id,
        winner_position=1,
    )
    target_match = MatchWithDetailsDefinitive(
        id=MatchId(-3),
        stage_item_input1=target_input,
        stage_item_input2=source_inputs[1],
        stage_item_input1_id=target_input.id,
        stage_item_input2_id=source_inputs[1].id,
        created=T,
        start_time=T + timedelta(minutes=15),
        duration_minutes=10,
        round_id=RoundId(-4),
        court_id=CourtId(-3),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
        state=MatchState.NOT_STARTED,
        completed_at=None,
    )
    target_round = RoundWithMatches(
        id=RoundId(-4),
        matches=[target_match],
        stage_item_id=StageItemId(-2),
        created=T,
        is_draft=False,
        name="",
    )
    target_stage_item = get_stage_item_mock(source_inputs, [target_round]).model_copy(
        update={"id": StageItemId(-2), "inputs": [target_input, source_inputs[1]]}
    )
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[source_stage_item, target_stage_item],
    )

    flags = get_match_conflict_flags([stage], default_break_minutes=5)

    assert flags[target_match.id].precedence_conflict is True
    assert flags[source_match1.id].precedence_conflict is False
    assert flags[source_match2.id].precedence_conflict is False


def test_get_match_conflict_flags_marks_sub_default_break_on_later_match() -> None:
    """A court gap shorter than the default break flags the later match only."""
    tournament_id = TournamentId(-1)
    stage_item_inputs = get_stage_item_inputs_mock(tournament_id)
    match1, match2 = get_2_definitive_matches_mock(
        stage_item_inputs,
        match1_start_time=T,
        match2_start_time=T + timedelta(minutes=12),
        duration_minutes=10,
    )
    match2 = match2.model_copy(update={"court_id": match1.court_id})
    round_ = get_one_round_with_two_definitive_matches(match1, match2)
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[get_stage_item_mock(stage_item_inputs, [round_])],
    )

    flags = get_match_conflict_flags([stage], default_break_minutes=5)

    assert flags[match1.id].short_break_conflict is False
    assert flags[match2.id].short_break_conflict is True
