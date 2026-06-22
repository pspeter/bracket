"""Unit tests for the Swiss resolution policy (issue #153)."""

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
) -> RoundWithMatches:
    return RoundWithMatches(
        id=RoundId(round_id),
        matches=[_make_match(round_id * 100 + i, s) for i, s in enumerate(match_states)],
        lifecycle_state=lifecycle_state,
        stage_item_id=StageItemId(-1),
        name=f"R{round_id}",
        created=DUMMY_MOCK_TIME,
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
