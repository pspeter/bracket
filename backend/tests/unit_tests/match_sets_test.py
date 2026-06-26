import pytest

from bracket.models.db.match import (
    Match,
    MatchSet,
    MatchSetState,
    MatchState,
    derive_match_state,
)
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.id_types import MatchId, MatchSetId, RoundId


def _set(state: MatchSetState, score1: int = 0, score2: int = 0) -> MatchSet:
    return MatchSet(
        id=MatchSetId(1),
        match_id=MatchId(1),
        set_number=1,
        stage_item_input1_score=score1,
        stage_item_input2_score=score2,
        state=state,
    )


@pytest.mark.parametrize(
    ("sets", "expected"),
    [
        ([], MatchState.NOT_STARTED),
        ([_set(MatchSetState.NOT_STARTED)], MatchState.NOT_STARTED),
        (
            [_set(MatchSetState.NOT_STARTED), _set(MatchSetState.NOT_STARTED)],
            MatchState.NOT_STARTED,
        ),
        ([_set(MatchSetState.COMPLETED)], MatchState.COMPLETED),
        (
            [_set(MatchSetState.COMPLETED), _set(MatchSetState.COMPLETED)],
            MatchState.COMPLETED,
        ),
        ([_set(MatchSetState.IN_PROGRESS)], MatchState.IN_PROGRESS),
        (
            [_set(MatchSetState.COMPLETED), _set(MatchSetState.NOT_STARTED)],
            MatchState.IN_PROGRESS,
        ),
        (
            [_set(MatchSetState.COMPLETED), _set(MatchSetState.IN_PROGRESS)],
            MatchState.IN_PROGRESS,
        ),
    ],
)
def test_derive_match_state(sets: list[MatchSet], expected: MatchState) -> None:
    assert derive_match_state(sets) is expected


def _match_with_sets(sets: list[MatchSet]) -> Match:
    return Match(
        id=MatchId(1),
        created=DUMMY_MOCK_TIME,
        duration_minutes=10,
        round_id=RoundId(1),
        match_sets=sets,
    )


def test_get_winner_not_completed_returns_none() -> None:
    match = _match_with_sets([_set(MatchSetState.IN_PROGRESS, 5, 3)])
    assert match.get_winner() is None


def _match_with_inputs(sets: list[MatchSet]) -> Match:
    from bracket.models.db.stage_item_inputs import StageItemInputEmpty
    from bracket.utils.id_types import StageItemInputId, TournamentId

    input1 = StageItemInputEmpty(
        id=StageItemInputId(1), slot=1, tournament_id=TournamentId(1), team_id=None
    )
    input2 = StageItemInputEmpty(
        id=StageItemInputId(2), slot=2, tournament_id=TournamentId(1), team_id=None
    )
    return Match(
        id=MatchId(1),
        created=DUMMY_MOCK_TIME,
        duration_minutes=10,
        round_id=RoundId(1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        match_sets=sets,
    )


def _completed(score1: int, score2: int) -> MatchSet:
    return _set(MatchSetState.COMPLETED, score1, score2)


def test_get_winner_single_set() -> None:
    match = _match_with_inputs([_completed(21, 10)])
    assert match.get_winner() is match.stage_item_input1


def test_get_winner_two_sets_split_is_draw() -> None:
    match = _match_with_inputs([_completed(21, 10), _completed(5, 21)])
    assert match.get_winner() is None


def test_get_winner_three_sets_majority() -> None:
    match = _match_with_inputs([_completed(21, 10), _completed(5, 21), _completed(21, 19)])
    assert match.get_winner() is match.stage_item_input1
    match2 = _match_with_inputs([_completed(10, 21), _completed(21, 5), _completed(19, 21)])
    assert match2.get_winner() is match2.stage_item_input2


def test_derived_state_property_matches_helper() -> None:
    match = _match_with_sets(
        [_set(MatchSetState.COMPLETED, 21, 10), _set(MatchSetState.COMPLETED, 21, 12)]
    )
    assert match.state is MatchState.COMPLETED
