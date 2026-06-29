import pytest

from bracket.logic.match_sets.pointer import (
    IllegalSetTransitionError,
    apply_pointer_transition,
    derive_match_state_from_pointer,
    derive_set_state,
)
from bracket.models.db.match import MatchSetState, MatchState


@pytest.mark.parametrize(
    ("set_number", "completed", "in_progress", "expected"),
    [
        (1, 0, False, MatchSetState.NOT_STARTED),
        (1, 0, True, MatchSetState.IN_PROGRESS),
        (1, 1, False, MatchSetState.COMPLETED),
        (2, 1, False, MatchSetState.NOT_STARTED),
        (2, 1, True, MatchSetState.IN_PROGRESS),
        (2, 2, False, MatchSetState.COMPLETED),
    ],
)
def test_derive_set_state(
    set_number: int,
    completed: int,
    in_progress: bool,
    expected: MatchSetState,
) -> None:
    assert derive_set_state(set_number, completed, in_progress) is expected


@pytest.mark.parametrize(
    ("completed", "num_sets", "in_progress", "expected"),
    [
        (0, 3, False, MatchState.NOT_STARTED),
        (0, 3, True, MatchState.IN_PROGRESS),
        (1, 3, False, MatchState.IN_PROGRESS),
        (3, 3, False, MatchState.COMPLETED),
    ],
)
def test_derive_match_state_from_pointer(
    completed: int, num_sets: int, in_progress: bool, expected: MatchState
) -> None:
    assert derive_match_state_from_pointer(completed, num_sets, in_progress) is expected


def test_apply_pointer_transition_start_and_complete() -> None:
    completed, in_progress = apply_pointer_transition(
        0, False, 1, MatchSetState.IN_PROGRESS
    )
    assert (completed, in_progress) == (0, True)

    completed, in_progress = apply_pointer_transition(
        completed, in_progress, 1, MatchSetState.COMPLETED
    )
    assert (completed, in_progress) == (1, False)


def test_apply_pointer_transition_rejects_skipping_a_set() -> None:
    with pytest.raises(IllegalSetTransitionError):
        apply_pointer_transition(0, False, 2, MatchSetState.COMPLETED)
