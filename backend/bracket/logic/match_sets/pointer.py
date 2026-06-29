from bracket.models.db.match import MatchSetState, MatchState


class IllegalSetTransitionError(ValueError):
    pass


class IllegalMatchTransitionError(ValueError):
    pass


def derive_set_state(
    set_number: int, completed_set_count: int, current_set_in_progress: bool
) -> MatchSetState:
    if set_number <= completed_set_count:
        return MatchSetState.COMPLETED
    if set_number == completed_set_count + 1 and current_set_in_progress:
        return MatchSetState.IN_PROGRESS
    return MatchSetState.NOT_STARTED


def derive_match_state_from_pointer(
    completed_set_count: int, num_sets: int, current_set_in_progress: bool
) -> MatchState:
    if completed_set_count == 0 and not current_set_in_progress:
        return MatchState.NOT_STARTED
    if completed_set_count >= num_sets:
        return MatchState.COMPLETED
    return MatchState.IN_PROGRESS


def apply_pointer_transition(
    completed_set_count: int,
    current_set_in_progress: bool,
    set_number: int,
    target_state: MatchSetState,
) -> tuple[int, bool]:
    """Return updated (completed_set_count, current_set_in_progress) for a set state change."""
    current_state = derive_set_state(set_number, completed_set_count, current_set_in_progress)
    if target_state == current_state:
        return completed_set_count, current_set_in_progress

    if target_state == MatchSetState.IN_PROGRESS:
        if set_number == completed_set_count and not current_set_in_progress:
            return completed_set_count - 1, True
        if set_number == completed_set_count + 1 and not current_set_in_progress:
            return completed_set_count, True
        raise IllegalSetTransitionError("Cannot update set state: sets must be completed in order")

    if target_state == MatchSetState.COMPLETED:
        if set_number == completed_set_count + 1:
            return completed_set_count + 1, False
        raise IllegalSetTransitionError("Cannot update set state: sets must be completed in order")

    if target_state == MatchSetState.NOT_STARTED:
        if set_number == completed_set_count + 1 and current_set_in_progress:
            return completed_set_count, False
        raise IllegalSetTransitionError("Cannot update set state: sets must be completed in order")

    raise IllegalSetTransitionError("Cannot update set state: sets must be completed in order")


def apply_start(
    completed_set_count: int, current_set_in_progress: bool, num_sets: int
) -> tuple[int, bool]:
    if current_set_in_progress:
        raise IllegalMatchTransitionError("Cannot start: a set is already in progress")
    if completed_set_count >= num_sets:
        raise IllegalMatchTransitionError("Cannot start: all sets are already completed")
    return completed_set_count, True


def apply_end(completed_set_count: int, current_set_in_progress: bool) -> tuple[int, bool]:
    if not current_set_in_progress:
        raise IllegalMatchTransitionError("Cannot end: no set is in progress")
    return completed_set_count + 1, False


def apply_reopen(completed_set_count: int, current_set_in_progress: bool) -> tuple[int, bool]:
    if completed_set_count <= 0:
        raise IllegalMatchTransitionError("Cannot reopen: no completed sets")
    return completed_set_count - 1, True


def apply_reset() -> tuple[int, bool]:
    return 0, False
