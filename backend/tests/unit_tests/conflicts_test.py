from datetime import timedelta

import pytest

from bracket.logic.planning.conflicts import (
    get_conflicting_matches,
    get_match_conflict_flags,
    matches_overlap,
)
from bracket.logic.planning.team_windows import get_team_playing_windows
from bracket.models.db.match import MatchState, MatchWithDetailsDefinitive
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInput,
    StageItemInputFinal,
    StageItemInputTentative,
)
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.utils.dummy_records import (
    DUMMY_MOCK_TIME,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
    DUMMY_TEAM4,
)
from bracket.utils.id_types import (
    CourtId,
    MatchId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
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
# get_team_playing_windows tests
# ---------------------------------------------------------------------------


def test_get_team_playing_windows_maps_stage_matches_by_team_id() -> None:
    """Scheduled definitive matches are grouped by player team, not input id."""
    tournament_id = TournamentId(-1)
    stage_item_inputs = get_stage_item_inputs_mock(tournament_id)
    second_team1_input = stage_item_inputs[2].model_copy(
        update={"id": StageItemInputId(-3), "team_id": TeamId(-1)}
    )
    stage_item_inputs = [
        stage_item_inputs[0],
        stage_item_inputs[1],
        second_team1_input,
        stage_item_inputs[3],
    ]
    match1, match2 = get_2_definitive_matches_mock(
        stage_item_inputs,
        match1_start_time=T,
        match2_start_time=T + timedelta(minutes=90),
        duration_minutes=90,
    )
    round_ = get_one_round_with_two_definitive_matches(match1, match2)
    stage_item = get_stage_item_mock(stage_item_inputs, [round_]).model_copy(
        update={"inputs": stage_item_inputs}
    )
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[stage_item],
    )

    windows = get_team_playing_windows([stage])

    assert [
        (match.id, window.stage_item_input_id, window.start_time, window.end_time)
        for match, window in windows[TeamId(-1)]
    ] == [
        (match1.id, stage_item_inputs[0].id, T, T + timedelta(minutes=90)),
        (match2.id, second_team1_input.id, T + timedelta(minutes=90), T + timedelta(minutes=180)),
    ]
    assert [(match.id, window.stage_item_input_id) for match, window in windows[TeamId(-2)]] == [
        (match1.id, stage_item_inputs[1].id)
    ]


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


# ---------------------------------------------------------------------------
# Referee conflict tests
# ---------------------------------------------------------------------------


def _make_definitive_match(
    match_id: MatchId,
    input1: StageItemInput,
    input2: StageItemInput,
    round_id: RoundId,
    court_id: CourtId,
    start_time: object,
    duration_minutes: int = 60,
    referee: StageItemInput | None = None,
    referee_name: str | None = None,
) -> MatchWithDetailsDefinitive:
    return MatchWithDetailsDefinitive(
        id=match_id,
        stage_item_input1=input1,
        stage_item_input2=input2,
        stage_item_input1_id=input1.id,
        stage_item_input2_id=input2.id,
        created=DUMMY_MOCK_TIME,
        start_time=start_time,  # type: ignore[arg-type]
        duration_minutes=duration_minutes,
        round_id=round_id,
        court_id=court_id,
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
        state=MatchState.NOT_STARTED,
        completed_at=None,
        referee=referee,
        referee_stage_item_input_id=referee.id if referee is not None else None,
        referee_name=referee_name,
    )


def _make_stage_with_two_matches(
    match1: MatchWithDetailsDefinitive,
    match2: MatchWithDetailsDefinitive,
) -> StageWithStageItems:
    round1 = RoundWithMatches(
        id=RoundId(-10),
        matches=[match1],
        stage_item_id=StageItemId(-10),
        created=MOCK_NOW,
        is_draft=False,
        name="",
    )
    round2 = RoundWithMatches(
        id=RoundId(-11),
        matches=[match2],
        stage_item_id=StageItemId(-10),
        created=MOCK_NOW,
        is_draft=False,
        name="",
    )
    stage_item = StageItemWithRounds(
        rounds=[round1, round2],
        inputs=[match1.stage_item_input1, match1.stage_item_input2],
        type_name="Single Elimination",
        team_count=4,
        ranking_id=None,
        id=StageItemId(-10),
        stage_id=StageId(-10),
        name="",
        created=MOCK_NOW,
        type=StageType.SINGLE_ELIMINATION,
    )
    return StageWithStageItems(
        id=StageId(-10),
        tournament_id=TournamentId(-1),
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[stage_item],
    )


def _make_inputs(
    tournament_id: TournamentId,
) -> tuple[StageItemInputFinal, StageItemInputFinal, StageItemInputFinal, StageItemInputFinal]:
    return (
        StageItemInputFinal(
            id=StageItemInputId(-20),
            team_id=TeamId(-20),
            slot=1,
            tournament_id=tournament_id,
            team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-20)),
        ),
        StageItemInputFinal(
            id=StageItemInputId(-21),
            team_id=TeamId(-21),
            slot=2,
            tournament_id=tournament_id,
            team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-21)),
        ),
        StageItemInputFinal(
            id=StageItemInputId(-22),
            team_id=TeamId(-22),
            slot=3,
            tournament_id=tournament_id,
            team=Team(**DUMMY_TEAM3.model_dump(), id=TeamId(-22)),
        ),
        StageItemInputFinal(
            id=StageItemInputId(-23),
            team_id=TeamId(-23),
            slot=4,
            tournament_id=tournament_id,
            team=Team(**DUMMY_TEAM4.model_dump(), id=TeamId(-23)),
        ),
    )


def test_referee_conflict_flags_both_sides() -> None:
    """A team playing and refereeing in overlapping windows flags both matches."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    # inp[0] (team -20) plays in playing_match; refereeing_match has team -20 as referee
    playing_match = _make_definitive_match(
        MatchId(-20), inp[0], inp[1], RoundId(-10), CourtId(-1), T
    )
    refereeing_match = _make_definitive_match(
        MatchId(-21),
        inp[2],
        inp[3],
        RoundId(-11),
        CourtId(-2),
        T,
        referee=inp[0],
    )
    stage = _make_stage_with_two_matches(playing_match, refereeing_match)

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[refereeing_match.id].referee_conflict is True
    assert flags[playing_match.id].stage_item_input1_conflict is True
    assert flags[playing_match.id].stage_item_input2_conflict is False
    assert flags[playing_match.id].referee_conflict is False


def test_referee_conflict_free_text_no_conflict() -> None:
    """A free-text referee (no team_id) never produces a conflict."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    playing_match = _make_definitive_match(
        MatchId(-20), inp[0], inp[1], RoundId(-10), CourtId(-1), T
    )
    refereeing_match = _make_definitive_match(
        MatchId(-21),
        inp[2],
        inp[3],
        RoundId(-11),
        CourtId(-2),
        T,
        referee=None,
        referee_name="John Smith",
    )
    stage = _make_stage_with_two_matches(playing_match, refereeing_match)

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[refereeing_match.id].referee_conflict is False
    assert flags[playing_match.id].stage_item_input1_conflict is False
    assert flags[playing_match.id].stage_item_input2_conflict is False


def test_referee_conflict_non_overlapping_no_conflict() -> None:
    """Non-overlapping windows (refereeing ends before playing starts) produce no conflict."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    # playing_match: T to T+60min; refereeing_match: T+120min onwards — no overlap
    playing_match = _make_definitive_match(
        MatchId(-20), inp[0], inp[1], RoundId(-10), CourtId(-1), T
    )
    refereeing_match = _make_definitive_match(
        MatchId(-21),
        inp[2],
        inp[3],
        RoundId(-11),
        CourtId(-2),
        T + timedelta(hours=2),
        referee=inp[0],
    )
    stage = _make_stage_with_two_matches(playing_match, refereeing_match)

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[refereeing_match.id].referee_conflict is False
    assert flags[playing_match.id].stage_item_input1_conflict is False


def test_referee_conflict_no_playing_match_no_conflict() -> None:
    """A team referee whose team has no scheduled playing match produces no conflict."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    # Only one match: team -22 and -23 play; referee is team -20 (not playing anywhere)
    refereeing_match = _make_definitive_match(
        MatchId(-21),
        inp[2],
        inp[3],
        RoundId(-11),
        CourtId(-2),
        T,
        referee=inp[0],
    )
    round1 = RoundWithMatches(
        id=RoundId(-11),
        matches=[refereeing_match],
        stage_item_id=StageItemId(-10),
        created=MOCK_NOW,
        is_draft=False,
        name="",
    )
    stage_item = StageItemWithRounds(
        rounds=[round1],
        inputs=[inp[2], inp[3]],
        type_name="Single Elimination",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-10),
        stage_id=StageId(-10),
        name="",
        created=MOCK_NOW,
        type=StageType.SINGLE_ELIMINATION,
    )
    stage = StageWithStageItems(
        id=StageId(-10),
        tournament_id=tid,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[stage_item],
    )

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[refereeing_match.id].referee_conflict is False


def test_referee_conflict_team_referees_two_overlapping_matches() -> None:
    """A team assigned as referee to two overlapping matches flags both matches."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    # inp[0] (team -20) referees both matches, which overlap in time.
    refereeing_match1 = _make_definitive_match(
        MatchId(-20),
        inp[1],
        inp[2],
        RoundId(-10),
        CourtId(-1),
        T,
        referee=inp[0],
    )
    refereeing_match2 = _make_definitive_match(
        MatchId(-21),
        inp[1],
        inp[3],
        RoundId(-11),
        CourtId(-2),
        T + timedelta(minutes=30),
        referee=inp[0],
    )
    stage = _make_stage_with_two_matches(refereeing_match1, refereeing_match2)

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[refereeing_match1.id].referee_conflict is True
    assert flags[refereeing_match2.id].referee_conflict is True


def test_referee_conflict_team_referees_two_non_overlapping_matches() -> None:
    """A team refereeing two matches that do not overlap is not flagged."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    # inp[0] (team -20) referees both matches, two hours apart — no overlap.
    refereeing_match1 = _make_definitive_match(
        MatchId(-20),
        inp[1],
        inp[2],
        RoundId(-10),
        CourtId(-1),
        T,
        referee=inp[0],
    )
    refereeing_match2 = _make_definitive_match(
        MatchId(-21),
        inp[1],
        inp[3],
        RoundId(-11),
        CourtId(-2),
        T + timedelta(hours=2),
        referee=inp[0],
    )
    stage = _make_stage_with_two_matches(refereeing_match1, refereeing_match2)

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[refereeing_match1.id].referee_conflict is False
    assert flags[refereeing_match2.id].referee_conflict is False


def test_referee_conflict_team_plays_and_referees_same_match() -> None:
    """A team that is both a player and referee in the same match is flagged."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    # inp[0] (team -20) plays as input1; same team is also the referee for this match
    match = _make_definitive_match(
        MatchId(-20),
        inp[0],
        inp[1],
        RoundId(-10),
        CourtId(-1),
        T,
        referee=inp[0],
    )
    round1 = RoundWithMatches(
        id=RoundId(-10),
        matches=[match],
        stage_item_id=StageItemId(-10),
        created=MOCK_NOW,
        is_draft=False,
        name="",
    )
    stage_item = StageItemWithRounds(
        rounds=[round1],
        inputs=[inp[0], inp[1]],
        type_name="Single Elimination",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-10),
        stage_id=StageId(-10),
        name="",
        created=MOCK_NOW,
        type=StageType.SINGLE_ELIMINATION,
    )
    stage = StageWithStageItems(
        id=StageId(-10),
        tournament_id=tid,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[stage_item],
    )

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[match.id].referee_conflict is True
    assert flags[match.id].stage_item_input1_conflict is True
    assert flags[match.id].stage_item_input2_conflict is False


# ---------------------------------------------------------------------------
# Placeholder (tentative/empty) slot conflict tests (issue #132)
# ---------------------------------------------------------------------------


def _make_tentative(
    input_id: int, slot: int, tournament_id: TournamentId
) -> StageItemInputTentative:
    """A placeholder ("winner of …") slot: a real stage_item_input with team_id = None."""
    return StageItemInputTentative(
        id=StageItemInputId(input_id),
        slot=slot,
        tournament_id=tournament_id,
        stage_item_id=StageItemId(-10),
        winner_from_stage_item_id=StageItemId(-99),
        winner_position=slot,
    )


def test_referee_conflict_placeholder_slot_plays_and_referees() -> None:
    """The issue's example: a tentative slot referees one match and plays in an overlapping one.

    Inputs [A, B, C(tentative), D]: match1 is ``A vs B`` refereed by ``C``; match2 is ``C vs D``
    overlapping. ``C`` both plays and referees, so the backend must flag it even though ``C`` has
    no resolved team_id yet — matching the auto-scheduler and the frontend placement preview.
    """
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    tentative_c = _make_tentative(-30, 3, tid)
    referee_match = _make_definitive_match(
        MatchId(-20), inp[0], inp[1], RoundId(-10), CourtId(-1), T, referee=tentative_c
    )
    playing_match = _make_definitive_match(
        MatchId(-21), tentative_c, inp[3], RoundId(-11), CourtId(-2), T
    )
    stage = _make_stage_with_two_matches(referee_match, playing_match)

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[referee_match.id].referee_conflict is True
    assert flags[playing_match.id].stage_item_input1_conflict is True
    assert flags[playing_match.id].stage_item_input2_conflict is False
    assert flags[playing_match.id].referee_conflict is False


def test_referee_conflict_placeholder_slot_referees_two_overlapping_matches() -> None:
    """A tentative slot assigned as referee to two overlapping matches flags both."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    tentative_c = _make_tentative(-30, 3, tid)
    referee_match1 = _make_definitive_match(
        MatchId(-20), inp[0], inp[1], RoundId(-10), CourtId(-1), T, referee=tentative_c
    )
    referee_match2 = _make_definitive_match(
        MatchId(-21),
        inp[2],
        inp[3],
        RoundId(-11),
        CourtId(-2),
        T + timedelta(minutes=30),
        referee=tentative_c,
    )
    stage = _make_stage_with_two_matches(referee_match1, referee_match2)

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[referee_match1.id].referee_conflict is True
    assert flags[referee_match2.id].referee_conflict is True


def test_conflict_two_matches_share_placeholder_playing_slot() -> None:
    """Two overlapping matches that both use the same placeholder playing slot are flagged."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    tentative_c = _make_tentative(-30, 3, tid)
    # tentative_c plays input1 in both matches, which overlap in time.
    match1 = _make_definitive_match(MatchId(-20), tentative_c, inp[1], RoundId(-10), CourtId(-1), T)
    match2 = _make_definitive_match(
        MatchId(-21), tentative_c, inp[3], RoundId(-11), CourtId(-2), T + timedelta(minutes=30)
    )
    stage = _make_stage_with_two_matches(match1, match2)

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[match1.id].stage_item_input1_conflict is True
    assert flags[match2.id].stage_item_input1_conflict is True
    assert flags[match1.id].stage_item_input2_conflict is False
    assert flags[match2.id].stage_item_input2_conflict is False


def test_conflict_placeholder_playing_slots_non_overlapping_no_conflict() -> None:
    """The same placeholder playing slot in two non-overlapping matches is not flagged."""
    tid = TournamentId(-1)
    inp = _make_inputs(tid)
    tentative_c = _make_tentative(-30, 3, tid)
    match1 = _make_definitive_match(MatchId(-20), tentative_c, inp[1], RoundId(-10), CourtId(-1), T)
    match2 = _make_definitive_match(
        MatchId(-21), tentative_c, inp[3], RoundId(-11), CourtId(-2), T + timedelta(hours=2)
    )
    stage = _make_stage_with_two_matches(match1, match2)

    flags = get_match_conflict_flags([stage], default_break_minutes=0)

    assert flags[match1.id].stage_item_input1_conflict is False
    assert flags[match2.id].stage_item_input1_conflict is False
