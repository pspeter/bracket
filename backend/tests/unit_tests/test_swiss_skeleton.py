import pytest

from bracket.logic.scheduling.swiss_skeleton import build_swiss_skeleton
from bracket.models.db.match import MatchCreateBody
from bracket.utils.id_types import RoundId


def test_even_teams_round_count() -> None:
    skeleton = build_swiss_skeleton(team_count=4, games_per_player=3)
    assert skeleton.round_count == 3


def test_odd_teams_round_count() -> None:
    # ceil(3 * 5 / 4) = ceil(3.75) = 4
    skeleton = build_swiss_skeleton(team_count=5, games_per_player=3)
    assert skeleton.round_count == 4


def test_odd_teams_n_not_exact_divisor() -> None:
    # 5 teams, N=2 → ceil(2 * 5 / 4) = ceil(2.5) = 3 rounds
    skeleton = build_swiss_skeleton(team_count=5, games_per_player=2)
    assert skeleton.round_count == 3


@pytest.mark.parametrize(
    "team_count, games_per_player",
    [
        (4, 3),
        (5, 3),
        (5, 4),
        (6, 5),
        (3, 3),
        (7, 4),
    ],
)
def test_all_slots_reach_games_per_player(team_count: int, games_per_player: int) -> None:
    skeleton = build_swiss_skeleton(team_count=team_count, games_per_player=games_per_player)
    games: list[int] = [0] * team_count
    for round_ in skeleton.rounds:
        for s1, s2 in round_.matches:
            games[s1] += 1
            games[s2] += 1
    assert all(g >= games_per_player for g in games)


@pytest.mark.parametrize(
    "team_count, games_per_player",
    [(4, 3), (5, 3), (6, 4), (7, 5)],
)
def test_no_double_booking_per_round(team_count: int, games_per_player: int) -> None:
    skeleton = build_swiss_skeleton(team_count=team_count, games_per_player=games_per_player)
    for round_ in skeleton.rounds:
        used: set[int] = set()
        for s1, s2 in round_.matches:
            assert s1 not in used
            assert s2 not in used
            used.add(s1)
            used.add(s2)
        if round_.bye_slot is not None:
            assert round_.bye_slot not in used


def test_rotating_bye_all_slots_covered_in_one_cycle() -> None:
    # With 5 teams, 5 rounds = one full cycle; every slot gets exactly 1 bye
    skeleton = build_swiss_skeleton(team_count=5, games_per_player=4)
    assert skeleton.round_count == 5
    bye_slots = [r.bye_slot for r in skeleton.rounds if r.bye_slot is not None]
    assert sorted(bye_slots) == [0, 1, 2, 3, 4]


def test_even_teams_have_no_bye() -> None:
    skeleton = build_swiss_skeleton(team_count=6, games_per_player=4)
    for round_ in skeleton.rounds:
        assert round_.bye_slot is None


@pytest.mark.parametrize("team_count, games_per_player", [(3, 2), (5, 3), (6, 4), (8, 5)])
def test_slot_indices_are_valid(team_count: int, games_per_player: int) -> None:
    skeleton = build_swiss_skeleton(team_count=team_count, games_per_player=games_per_player)
    valid = set(range(team_count))
    for round_ in skeleton.rounds:
        for s1, s2 in round_.matches:
            assert s1 in valid, f"slot {s1} out of range for team_count={team_count}"
            assert s2 in valid, f"slot {s2} out of range for team_count={team_count}"
        if round_.bye_slot is not None:
            assert round_.bye_slot in valid


def test_bye_slot_used_as_referee_slot_in_match_create_body() -> None:
    """Fix #3: referee_slot in MatchCreateBody should be set to the round's bye_slot."""
    skeleton = build_swiss_skeleton(team_count=5, games_per_player=3)
    for round_skeleton in skeleton.rounds:
        for slot1, slot2 in round_skeleton.matches:
            match_body = MatchCreateBody(
                round_id=RoundId(-1),
                court_id=None,
                stage_item_input1_id=None,
                stage_item_input2_id=None,
                stage_item_input1_winner_from_match_id=None,
                stage_item_input2_winner_from_match_id=None,
                duration_minutes=15,
                custom_duration_minutes=None,
                input1_slot=slot1,
                input2_slot=slot2,
                referee_slot=round_skeleton.bye_slot,
            )
            assert match_body.referee_slot == round_skeleton.bye_slot
