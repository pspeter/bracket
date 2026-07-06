"""Unit tests for the Mexicano identity slot assigner (issue #259)."""

from decimal import Decimal

from bracket.logic.scheduling.mexicano_slot_assigner import assign_mexicano_pairs_to_slots
from bracket.logic.scheduling.swiss_skeleton import RoundSkeleton
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.utils.dummy_records import DUMMY_TEAM1
from bracket.utils.id_types import StageItemInputId, TeamId, TournamentId


def _input(n: int) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(n),
        slot=n,
        tournament_id=TournamentId(-1),
        team_id=TeamId(n),
        points=Decimal("0"),
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(n)),
    )


def test_identity_maps_pairs_in_order_to_slots() -> None:
    a, b, c, d = _input(10), _input(11), _input(12), _input(13)
    skeleton = RoundSkeleton(matches=((0, 1), (2, 3)), bye_slot=None)

    mapping = assign_mexicano_pairs_to_slots([(a, b), (c, d)], None, skeleton)

    assert mapping == {0: a.id, 1: b.id, 2: c.id, 3: d.id}


def test_top_pair_lands_in_first_match_slot_regardless_of_skeleton_order() -> None:
    """The first (top-standings) pair always lands in the lowest match slot."""
    a, b, c, d = _input(10), _input(11), _input(12), _input(13)
    # Skeleton matches deliberately out of slot order.
    skeleton = RoundSkeleton(matches=((2, 3), (0, 1)), bye_slot=None)

    mapping = assign_mexicano_pairs_to_slots([(a, b), (c, d)], None, skeleton)

    assert mapping[0] == a.id
    assert mapping[1] == b.id
