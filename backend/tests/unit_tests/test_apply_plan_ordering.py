"""Unit tests for ordered_team_assignment_writes, the pure ordering decision behind apply_plan's
AssignTeamToInput batch handling. The end-to-end DB behavior (writes actually landing correctly
for a full swap) is covered by the integration test
rankings_test.py::test_update_ranking_swaps_teams_between_dependent_inputs.
"""

from bracket.logic.apply_plan import ordered_team_assignment_writes
from bracket.logic.plan import AssignTeamToInput
from bracket.utils.id_types import StageItemInputId, TeamId


def test_full_swap_clears_both_before_writing_either_final() -> None:
    """Two sibling inputs trading teams: both clears must precede both finals, else a write of
    one final could collide with the other input's still-unwritten old team_id.
    """
    a = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(1), team_id=TeamId(2), previous_team_id=TeamId(1)
    )
    b = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(2), team_id=TeamId(1), previous_team_id=TeamId(2)
    )

    ordered = ordered_team_assignment_writes([a, b])

    clear_a = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(1), team_id=None, previous_team_id=TeamId(1)
    )
    clear_b = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(2), team_id=None, previous_team_id=TeamId(2)
    )

    assert ordered == [clear_a, clear_b, a, b]


def test_unchanged_assignment_is_not_cleared() -> None:
    """An input whose team_id isn't actually changing gets no clear write."""
    unchanged = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(1), team_id=TeamId(1), previous_team_id=TeamId(1)
    )

    ordered = ordered_team_assignment_writes([unchanged])

    assert ordered == [unchanged]


def test_first_time_assignment_is_not_cleared() -> None:
    """An input with no previous team (previous_team_id=None) gets no clear write."""
    first_time = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(1), team_id=TeamId(1), previous_team_id=None
    )

    ordered = ordered_team_assignment_writes([first_time])

    assert ordered == [first_time]


def test_mixed_batch_clears_only_the_changing_ones_first() -> None:
    """A batch with both changing and unchanged/first-time inputs clears only the changing one,
    and every clear still precedes every final write.
    """
    changing = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(1), team_id=TeamId(2), previous_team_id=TeamId(1)
    )
    unchanged = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(2), team_id=TeamId(3), previous_team_id=TeamId(3)
    )
    first_time = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(3), team_id=TeamId(4), previous_team_id=None
    )

    ordered = ordered_team_assignment_writes([changing, unchanged, first_time])

    clear_changing = AssignTeamToInput(
        stage_item_input_id=StageItemInputId(1), team_id=None, previous_team_id=TeamId(1)
    )
    assert ordered == [clear_changing, changing, unchanged, first_time]
