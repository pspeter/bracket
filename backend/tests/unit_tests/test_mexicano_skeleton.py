"""Unit tests for the Mexicano placeholder skeleton builder (issue #259)."""

import pytest

from bracket.logic.scheduling.mexicano_skeleton import build_mexicano_skeleton


def test_skeleton_has_games_per_player_rounds() -> None:
    skeleton = build_mexicano_skeleton(team_count=4, games_per_player=3)
    assert skeleton.round_count == 3


def test_every_round_pairs_adjacent_slots_with_no_bye() -> None:
    skeleton = build_mexicano_skeleton(team_count=6, games_per_player=2)
    assert skeleton.round_count == 2
    for round_skeleton in skeleton.rounds:
        assert round_skeleton.bye_slot is None
        assert round_skeleton.matches == ((0, 1), (2, 3), (4, 5))


def test_odd_team_count_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_mexicano_skeleton(team_count=5, games_per_player=2)
