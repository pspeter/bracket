"""Unit tests for the Swiss pair→slot assigner (issue #152)."""

from decimal import Decimal

from bracket.logic.scheduling.swiss_skeleton import RoundSkeleton
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.utils.dummy_records import DUMMY_TEAM1
from bracket.utils.id_types import StageItemInputId, TeamId, TournamentId


def _input(n: int, elo: int = 1000) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(n),
        slot=n,
        tournament_id=TournamentId(-1),
        team_id=TeamId(n),
        points=Decimal(str(elo)),
        wins=0,
        draws=0,
        losses=0,
        team=Team(**{**DUMMY_TEAM1.model_dump(), "id": TeamId(n), "active": True}),
    )


# ── Test 5: All skeleton slots are covered ────────────────────────────────────


def test_all_skeleton_slots_covered() -> None:
    """The returned mapping covers every slot index declared in the skeleton."""
    from bracket.logic.scheduling.swiss_slot_assigner import assign_pairs_to_slots

    a, b, c, d = _input(1), _input(2), _input(3), _input(4)
    pairs = [(a, b), (c, d)]
    bye = None
    skeleton = RoundSkeleton(matches=((0, 1), (2, 3)), bye_slot=None)

    result = assign_pairs_to_slots(pairs, bye, skeleton)

    assert set(result.keys()) == {0, 1, 2, 3}


# ── Test 6: Each pair occupies the same match slot ────────────────────────────


def test_each_pair_in_same_match_slot() -> None:
    """Both members of a pair land in the same skeleton match (same slot pair)."""
    from bracket.logic.scheduling.swiss_slot_assigner import assign_pairs_to_slots

    a, b, c, d = _input(1), _input(2), _input(3), _input(4)
    pairs = [(a, b), (c, d)]
    skeleton = RoundSkeleton(matches=((0, 1), (2, 3)), bye_slot=None)

    result = assign_pairs_to_slots(pairs, None, skeleton)

    # a and b should be in the same match slot pair
    for slot1, slot2 in skeleton.matches:
        slot_set = {result[slot1], result[slot2]}
        assert slot_set in ({a.id, b.id}, {c.id, d.id}), (
            f"Match slots ({slot1},{slot2}) contain mixed-pair teams: {slot_set}"
        )


# ── Test 7: Bye team is referee and never a player ────────────────────────────


def test_bye_team_is_referee_not_player() -> None:
    """Bye team appears only in the bye_slot (referee position), not in any match slot."""
    from bracket.logic.scheduling.swiss_slot_assigner import assign_pairs_to_slots

    a, b, c, d, e = _input(1), _input(2), _input(3), _input(4), _input(5)
    pairs = [(a, b), (c, d)]
    skeleton = RoundSkeleton(matches=((0, 1), (2, 3)), bye_slot=4)

    result = assign_pairs_to_slots(pairs, e, skeleton)

    assert result[4] == e.id
    playing_ids = {result[s] for s in (0, 1, 2, 3)}
    assert e.id not in playing_ids


# ── Test 8: Fairness — minimise slot reuse from previous round ────────────────


def test_fairness_minimizes_slot_reuse() -> None:
    """When pairs are the same as last round, assigner picks a different slot arrangement.

    Round 1 had A@0, B@1, C@2, D@3. Same pairs (A,B) and (C,D) must be assigned again
    (forced-rematch scenario for the slot-assigner unit test). The optimal assignment has
    zero slot reuses; the naive ordering has four. The assigner must choose the former.
    """
    from bracket.logic.scheduling.swiss_slot_assigner import assign_pairs_to_slots

    a, b, c, d = _input(1), _input(2), _input(3), _input(4)
    prev_slots = [{0: a.id, 1: b.id, 2: c.id, 3: d.id}]
    pairs = [(a, b), (c, d)]
    skeleton = RoundSkeleton(matches=((0, 1), (2, 3)), bye_slot=None)

    result = assign_pairs_to_slots(pairs, None, skeleton, previous_slot_assignments=prev_slots)

    reuses = sum(1 for slot, inp_id in result.items() if prev_slots[0].get(slot) == inp_id)
    assert reuses == 0


# ── Test 9: skeleton_from_matches reconstructs the round skeleton correctly ───


def test_skeleton_from_matches_even_teams() -> None:
    """Slot pairs and bye_slot are correctly extracted from placeholder match data."""
    from bracket.logic.scheduling.swiss_slot_assigner import skeleton_from_slot_pairs

    slot_pairs = [(0, 1), (2, 3)]
    skeleton = skeleton_from_slot_pairs(slot_pairs, bye_slot=None)

    assert skeleton.matches == ((0, 1), (2, 3))
    assert skeleton.bye_slot is None


def test_skeleton_from_matches_odd_teams() -> None:
    """Bye slot is preserved when reconstructing skeleton from placeholder matches."""
    from bracket.logic.scheduling.swiss_slot_assigner import skeleton_from_slot_pairs

    slot_pairs = [(0, 1), (2, 3)]
    skeleton = skeleton_from_slot_pairs(slot_pairs, bye_slot=4)

    assert skeleton.matches == ((0, 1), (2, 3))
    assert skeleton.bye_slot == 4
