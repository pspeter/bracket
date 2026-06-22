"""Unit tests for the Swiss resolution policy (issues #153 and #154)."""

from bracket.models.db.match import MatchState, MatchWithDetails
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.util import RoundWithMatches
from bracket.utils.dummy_records import DUMMY_MATCH1, DUMMY_MOCK_TIME
from bracket.utils.id_types import MatchId, RoundId, StageItemId


def _make_match(match_id: int, state: MatchState) -> MatchWithDetails:
    return MatchWithDetails(
        **DUMMY_MATCH1.model_dump()
        | {
            "id": MatchId(match_id),
            "state": state,
            "stage_item_input1_id": None,
            "stage_item_input2_id": None,
            "court_id": None,
        }
    )


def _make_round(
    round_id: int,
    lifecycle_state: RoundLifecycleState,
    match_states: list[MatchState],
    is_pinned: bool = False,
) -> RoundWithMatches:
    return RoundWithMatches(
        id=RoundId(round_id),
        matches=[_make_match(round_id * 100 + i, s) for i, s in enumerate(match_states)],
        lifecycle_state=lifecycle_state,
        stage_item_id=StageItemId(-1),
        name=f"R{round_id}",
        created=DUMMY_MOCK_TIME,
        is_pinned=is_pinned,
    )


# ── Test 1: Empty list ─────────────────────────────────────────────────────────


def test_returns_none_for_no_rounds() -> None:
    from bracket.logic.scheduling.swiss_resolution_policy import get_next_round_to_resolve

    assert get_next_round_to_resolve([]) is None


# ── Test 2: Single PLACEHOLDER, no predecessor ────────────────────────────────


def test_placeholder_with_no_predecessor_resolves() -> None:
    from bracket.logic.scheduling.swiss_resolution_policy import get_next_round_to_resolve

    r1 = _make_round(1, RoundLifecycleState.PLACEHOLDER, [MatchState.NOT_STARTED])
    result = get_next_round_to_resolve([r1])
    assert result is not None
    assert result.id == r1.id


# ── Test 3: PLACEHOLDER after a fully completed predecessor ───────────────────


def test_placeholder_after_completed_round_resolves() -> None:
    from bracket.logic.scheduling.swiss_resolution_policy import get_next_round_to_resolve

    r1 = _make_round(1, RoundLifecycleState.LOCKED, [MatchState.COMPLETED])
    r2 = _make_round(2, RoundLifecycleState.PLACEHOLDER, [MatchState.NOT_STARTED])
    result = get_next_round_to_resolve([r1, r2])
    assert result is not None
    assert result.id == r2.id


# ── Test 4: PLACEHOLDER blocked when predecessor is incomplete ────────────────


def test_placeholder_blocked_when_predecessor_incomplete() -> None:
    from bracket.logic.scheduling.swiss_resolution_policy import get_next_round_to_resolve

    r1 = _make_round(1, RoundLifecycleState.LOCKED, [MatchState.COMPLETED, MatchState.NOT_STARTED])
    r2 = _make_round(2, RoundLifecycleState.PLACEHOLDER, [MatchState.NOT_STARTED])
    result = get_next_round_to_resolve([r1, r2])
    assert result is None


# ── Test 5: Sequential — only the next PLACEHOLDER is returned ────────────────


def test_sequential_only_next_placeholder_returned() -> None:
    """When R1 is complete and R2+R3 are PLACEHOLDER, only R2 is returned."""
    from bracket.logic.scheduling.swiss_resolution_policy import get_next_round_to_resolve

    r1 = _make_round(1, RoundLifecycleState.LOCKED, [MatchState.COMPLETED])
    r2 = _make_round(2, RoundLifecycleState.PLACEHOLDER, [MatchState.NOT_STARTED])
    r3 = _make_round(3, RoundLifecycleState.PLACEHOLDER, [MatchState.NOT_STARTED])
    result = get_next_round_to_resolve([r1, r2, r3])
    assert result is not None
    assert result.id == r2.id


# ── Tests for get_rounds_to_re_resolve (issue #154) ───────────────────────────


def test_re_resolve_returns_empty_when_no_rounds() -> None:
    from bracket.logic.scheduling.swiss_resolution_policy import get_rounds_to_re_resolve

    assert get_rounds_to_re_resolve([]) == []


def test_re_resolve_includes_resolved_not_started_round() -> None:
    from bracket.logic.scheduling.swiss_resolution_policy import get_rounds_to_re_resolve

    r2 = _make_round(2, RoundLifecycleState.RESOLVED, [MatchState.NOT_STARTED])
    result = get_rounds_to_re_resolve([r2])
    assert len(result) == 1
    assert result[0].id == r2.id


def test_re_resolve_excludes_locked_round() -> None:
    """A LOCKED round (any match started) is never re-resolved."""
    from bracket.logic.scheduling.swiss_resolution_policy import get_rounds_to_re_resolve

    r2 = _make_round(2, RoundLifecycleState.LOCKED, [MatchState.IN_PROGRESS])
    assert get_rounds_to_re_resolve([r2]) == []


def test_re_resolve_excludes_placeholder_round() -> None:
    """PLACEHOLDER rounds are handled by forward resolution, not re-resolution."""
    from bracket.logic.scheduling.swiss_resolution_policy import get_rounds_to_re_resolve

    r2 = _make_round(2, RoundLifecycleState.PLACEHOLDER, [MatchState.NOT_STARTED])
    assert get_rounds_to_re_resolve([r2]) == []


def test_re_resolve_excludes_pinned_resolved_round() -> None:
    """A hand-edited (pinned) round must not be overwritten by re-resolution."""
    from bracket.logic.scheduling.swiss_resolution_policy import get_rounds_to_re_resolve

    r2 = _make_round(2, RoundLifecycleState.RESOLVED, [MatchState.NOT_STARTED], is_pinned=True)
    assert get_rounds_to_re_resolve([r2]) == []


def test_re_resolve_excludes_resolved_round_with_in_progress_match() -> None:
    """A RESOLVED round whose match has already started is frozen (defensive match-state check)."""
    from bracket.logic.scheduling.swiss_resolution_policy import get_rounds_to_re_resolve

    r2 = _make_round(2, RoundLifecycleState.RESOLVED, [MatchState.IN_PROGRESS])
    assert get_rounds_to_re_resolve([r2]) == []


def test_re_resolve_returns_multiple_eligible_rounds() -> None:
    """All RESOLVED not-started not-pinned rounds are returned, not just the first."""
    from bracket.logic.scheduling.swiss_resolution_policy import get_rounds_to_re_resolve

    r2 = _make_round(2, RoundLifecycleState.RESOLVED, [MatchState.NOT_STARTED])
    r3 = _make_round(3, RoundLifecycleState.RESOLVED, [MatchState.NOT_STARTED])
    result = get_rounds_to_re_resolve([r2, r3])
    assert [r.id for r in result] == [r2.id, r3.id]


def test_re_resolve_skips_locked_but_includes_subsequent_not_started() -> None:
    """A locked round is skipped; subsequent eligible rounds are still re-resolved.

    AC: 'If round 2 is already in progress/completed, the correction leaves it untouched
    and only affects round 3+.'
    """
    from bracket.logic.scheduling.swiss_resolution_policy import get_rounds_to_re_resolve

    r1 = _make_round(1, RoundLifecycleState.LOCKED, [MatchState.COMPLETED])
    r2 = _make_round(2, RoundLifecycleState.LOCKED, [MatchState.IN_PROGRESS])
    r3 = _make_round(3, RoundLifecycleState.RESOLVED, [MatchState.NOT_STARTED])
    result = get_rounds_to_re_resolve([r1, r2, r3])
    assert len(result) == 1
    assert result[0].id == r3.id
