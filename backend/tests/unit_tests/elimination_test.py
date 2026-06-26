from bracket.logic.ranking.elimination import get_inputs_to_update_in_subsequent_elimination_rounds
from bracket.models.db.match import MatchSet, MatchSetState, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.util import RoundWithMatches
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.id_types import (
    MatchId,
    MatchSetId,
    RoundId,
    StageItemId,
    TournamentId,
)
from tests.unit_tests.mocks import (
    _single_set,
    get_2_definitive_and_2_tentative_matches_mock,
    get_one_round_with_two_definitive_matches,
    get_stage_item_inputs_mock,
    get_stage_item_mock,
    get_two_round_with_one_tentative_match_each,
)


def test_elimination_input_updates() -> None:
    tournament_id = TournamentId(-1)
    stage_item_inputs = get_stage_item_inputs_mock(tournament_id)
    matches = get_2_definitive_and_2_tentative_matches_mock(stage_item_inputs)
    rounds = [
        get_one_round_with_two_definitive_matches(matches[0], matches[1]),
        *get_two_round_with_one_tentative_match_each(matches[2], matches[3]),
    ]

    updates = get_inputs_to_update_in_subsequent_elimination_rounds(
        RoundId(-3),
        get_stage_item_mock(stage_item_inputs, rounds),
        {matches[0].id, matches[1].id},
    )

    assert updates == {
        matches[2].id: matches[2].model_copy(
            update={
                "stage_item_input1_id": stage_item_inputs[0].id,
                "stage_item_input2_id": stage_item_inputs[3].id,
                "stage_item_input1": stage_item_inputs[0],
                "stage_item_input2": stage_item_inputs[3],
            }
        ),
        matches[3].id: matches[3].model_copy(
            update={
                "stage_item_input1_id": stage_item_inputs[3].id,
                "stage_item_input2_id": None,
                "stage_item_input1": stage_item_inputs[3],
                "stage_item_input2": None,
            }
        ),
    }


def test_elimination_propagation_skips_none_winner() -> None:
    """When get_winner() returns None (draw), the previously-set downstream input is preserved."""
    tournament_id = TournamentId(-1)
    stage_item_inputs = get_stage_item_inputs_mock(tournament_id)

    # A drawn match: 2 sets, each player wins one → get_winner() = None
    drawn_match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=stage_item_inputs[0],
        stage_item_input2=stage_item_inputs[1],
        stage_item_input1_id=stage_item_inputs[0].id,
        stage_item_input2_id=stage_item_inputs[1].id,
        created=DUMMY_MOCK_TIME,
        duration_minutes=90,
        round_id=RoundId(-3),
        match_sets=[
            MatchSet(
                id=MatchSetId(-10),
                match_id=MatchId(-1),
                set_number=1,
                stage_item_input1_score=21,
                stage_item_input2_score=10,
                state=MatchSetState.COMPLETED,
            ),
            MatchSet(
                id=MatchSetId(-11),
                match_id=MatchId(-1),
                set_number=2,
                stage_item_input1_score=10,
                stage_item_input2_score=21,
                state=MatchSetState.COMPLETED,
            ),
        ],
        completed_at=DUMMY_MOCK_TIME,
    )

    # A normal match: input2 wins
    normal_match = MatchWithDetailsDefinitive(
        id=MatchId(-2),
        stage_item_input1=stage_item_inputs[2],
        stage_item_input2=stage_item_inputs[3],
        stage_item_input1_id=stage_item_inputs[2].id,
        stage_item_input2_id=stage_item_inputs[3].id,
        created=DUMMY_MOCK_TIME,
        duration_minutes=90,
        round_id=RoundId(-3),
        match_sets=[_single_set(MatchId(-2), 2, 3, MatchSetState.COMPLETED)],
        completed_at=DUMMY_MOCK_TIME,
    )

    # Subsequent match: input1 was previously propagated from drawn_match, input2 from normal_match.
    # Since drawn_match has no winner, input1 must NOT be cleared.
    subsequent_match = MatchWithDetails(
        id=MatchId(-3),
        created=DUMMY_MOCK_TIME,
        duration_minutes=90,
        round_id=RoundId(-2),
        match_sets=[],
        stage_item_input1=stage_item_inputs[0],
        stage_item_input1_id=stage_item_inputs[0].id,
        stage_item_input1_winner_from_match_id=drawn_match.id,
        stage_item_input2_winner_from_match_id=normal_match.id,
    )

    round1 = RoundWithMatches(
        id=RoundId(-3),
        matches=[drawn_match, normal_match],
        stage_item_id=StageItemId(-1),
        created=DUMMY_MOCK_TIME,
        lifecycle_state=RoundLifecycleState.ACTIVE,
        name="",
    )
    round2 = RoundWithMatches(
        id=RoundId(-2),
        matches=[subsequent_match],
        stage_item_id=StageItemId(-1),
        created=DUMMY_MOCK_TIME,
        lifecycle_state=RoundLifecycleState.ACTIVE,
        name="",
    )

    updates = get_inputs_to_update_in_subsequent_elimination_rounds(
        RoundId(-3),
        get_stage_item_mock(stage_item_inputs, [round1, round2]),
        {drawn_match.id, normal_match.id},
    )

    # Only input2 should be updated (from normal_match winner = stage_item_inputs[3]).
    # input1 must be preserved as stage_item_inputs[0] — draw must NOT clear it.
    assert subsequent_match.id in updates
    updated = updates[subsequent_match.id]
    assert updated.stage_item_input1 == stage_item_inputs[0]
    assert updated.stage_item_input1_id == stage_item_inputs[0].id
    assert updated.stage_item_input2 == stage_item_inputs[3]
    assert updated.stage_item_input2_id == stage_item_inputs[3].id
