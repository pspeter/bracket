"""Unit tests for the Mexicano round pairing selector (issue #259)."""

from decimal import Decimal

from bracket.logic.scheduling.mexicano_round_pairing import select_mexicano_round_pairing
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.utils.dummy_records import DUMMY_TEAM1
from bracket.utils.id_types import StageItemInputId, TeamId, TournamentId


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
