from bracket.models.db.match import MatchState


class IllegalMatchTransitionError(ValueError):
    pass


def derive_match_state_from_pointer(
    completed_set_count: int,
    num_sets: int,
    current_set_in_progress: bool,
    *,
    match_decided: bool = False,
) -> MatchState:
    if completed_set_count == 0 and not current_set_in_progress:
        return MatchState.NOT_STARTED
    if not current_set_in_progress and (completed_set_count >= num_sets or match_decided):
        return MatchState.COMPLETED
    return MatchState.IN_PROGRESS


def apply_start(
    completed_set_count: int,
    current_set_in_progress: bool,
    num_sets: int,
    *,
    match_decided: bool = False,
) -> tuple[int, bool]:
    if current_set_in_progress:
        raise IllegalMatchTransitionError("Cannot start: a set is already in progress")
    if completed_set_count >= num_sets:
        raise IllegalMatchTransitionError("Cannot start: all sets are already completed")
    if match_decided:
        raise IllegalMatchTransitionError("Cannot start: the match is already decided")
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
