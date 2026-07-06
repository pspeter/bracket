"""Unit tests for the Mexicano round pairing selector (issues #259, #260)."""

from decimal import Decimal

from bracket.logic.scheduling.mexicano_round_pairing import select_mexicano_round_pairing
from bracket.models.db.match import Match, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches
from bracket.utils.dummy_records import DUMMY_MATCH1, DUMMY_MOCK_TIME, DUMMY_TEAM1
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


def _input(
    slot: int,
    *,
    points: str = "0",
    set_difference: int = 0,
    point_difference: int = 0,
) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(slot),
        slot=slot,
        tournament_id=TournamentId(-1),
        team_id=TeamId(slot),
        points=Decimal(points),
        set_difference=set_difference,
        point_difference=point_difference,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(slot)),
    )


def _round_with_playing_pairs(
    round_id: int, pairs: list[tuple[StageItemInputFinal, StageItemInputFinal]]
) -> RoundWithMatches:
    """Build a completed round whose matches cover exactly the given playing pairs (no bye)."""
    matches: list[MatchWithDetailsDefinitive | MatchWithDetails] = []
    for i, (inp1, inp2) in enumerate(pairs):
        base = Match.model_validate(
            DUMMY_MATCH1.model_dump()
            | {
                "id": MatchId(round_id * 10 + i),
                "stage_item_input1_id": inp1.id,
                "stage_item_input2_id": inp2.id,
            }
        )
        matches.append(
            MatchWithDetailsDefinitive(
                **base.model_dump(),
                stage_item_input1=inp1,
                stage_item_input2=inp2,
                court=None,
            )
        )
    return RoundWithMatches(
        id=RoundId(round_id),
        matches=matches,
        lifecycle_state=RoundLifecycleState.LOCKED,
        stage_item_id=StageItemId(-1),
        name=f"R{round_id}",
        created=DUMMY_MOCK_TIME,
    )


def test_round_one_pairs_by_slot_order() -> None:
    """With no points yet, ordering falls back to slot: (1,2), (3,4)."""
    inputs = [_input(1), _input(2), _input(3), _input(4)]
    pairs, bye = select_mexicano_round_pairing(inputs, [])

    assert bye is None
    assert [(a.slot, b.slot) for a, b in pairs] == [(1, 2), (3, 4)]


def test_pairs_adjacent_teams_by_standings() -> None:
    """Highest points meets second highest, third meets fourth."""
    inputs = [
        _input(1, points="10"),
        _input(2, points="40"),
        _input(3, points="20"),
        _input(4, points="30"),
    ]
    pairs, bye = select_mexicano_round_pairing(inputs, [])

    assert bye is None
    # sorted by points desc: slot2 (40), slot4 (30), slot3 (20), slot1 (10)
    assert [(a.slot, b.slot) for a, b in pairs] == [(2, 4), (3, 1)]


def test_slot_is_final_tiebreaker() -> None:
    """Teams tied on points/set-diff/point-diff are ordered by slot ascending."""
    inputs = [_input(3), _input(1), _input(4), _input(2)]
    pairs, bye = select_mexicano_round_pairing(inputs, [])

    assert bye is None
    assert [(a.slot, b.slot) for a, b in pairs] == [(1, 2), (3, 4)]


def test_set_and_point_difference_break_points_ties() -> None:
    inputs = [
        _input(1, points="10", set_difference=1, point_difference=5),
        _input(2, points="10", set_difference=1, point_difference=9),
        _input(3, points="10", set_difference=2, point_difference=0),
        _input(4, points="10", set_difference=1, point_difference=5),
    ]
    pairs, bye = select_mexicano_round_pairing(inputs, [])

    assert bye is None
    # order: slot3 (sd 2), slot2 (sd1,pd9), then slot1 & slot4 tie (sd1,pd5) -> slot asc
    assert [(a.slot, b.slot) for a, b in pairs] == [(3, 2), (1, 4)]


def test_odd_count_round_one_byes_the_lowest_slot() -> None:
    """With no history, all bye-counts tie at zero; the deterministic tiebreak is ascending slot."""
    inputs = [_input(1), _input(2), _input(3), _input(4), _input(5)]
    pairs, bye = select_mexicano_round_pairing(inputs, [])

    assert bye is not None
    assert bye.slot == 1
    assert [(a.slot, b.slot) for a, b in pairs] == [(2, 3), (4, 5)]


def test_odd_count_bye_rotates_to_whoever_has_sat_out_least() -> None:
    """After slot 1 has already sat out once, the next bye goes to the next-fewest-byes entrant,
    not back to slot 1 and not to whoever is bottom of the standings."""
    inputs = [
        _input(1, points="0"),
        _input(2, points="50"),  # standings leader -- must not be trapped as bye
        _input(3, points="10"),
        _input(4, points="20"),
        _input(5, points="5"),  # standings last -- a standings-based bye would pick this one
    ]
    history = [
        _round_with_playing_pairs(
            1,
            [(inputs[1], inputs[2]), (inputs[3], inputs[4])],  # slot 1 sat out round 1
        )
    ]
    pairs, bye = select_mexicano_round_pairing(inputs, history)

    assert bye is not None
    assert bye.slot == 2  # slot 2 has 0 byes so far like slots 3-5, but ties break by slot asc
    remaining_slots = {a.slot for pair in pairs for a in pair}
    assert remaining_slots == {1, 3, 4, 5}


def test_odd_count_bye_never_repeats_before_everyone_else_has_had_one() -> None:
    """After slot 1 sat out round 1 and slot 2 sat out round 2, round 3's bye must go to one of
    the never-yet-byed slots (3, 4, or 5) -- not back to slot 1 or slot 2."""
    inputs = [_input(1), _input(2), _input(3), _input(4), _input(5)]
    history = [
        _round_with_playing_pairs(1, [(inputs[1], inputs[2]), (inputs[3], inputs[4])]),  # 1 sits
        _round_with_playing_pairs(2, [(inputs[0], inputs[2]), (inputs[3], inputs[4])]),  # 2 sits
    ]
    _pairs, bye = select_mexicano_round_pairing(inputs, history)

    assert bye is not None
    assert bye.slot not in (1, 2)
    assert bye.slot == 3  # fewest byes (0) tied among 3/4/5 -> ascending slot tiebreak
