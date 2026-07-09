"""Unit tests for the Swiss round pairing selector (issue #152)."""

from decimal import Decimal

from bracket.models.db.match import Match, MatchWithDetailsDefinitive
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches
from bracket.utils.dummy_records import DUMMY_MATCH1, DUMMY_MOCK_TIME, DUMMY_TEAM1
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


def _input(n: int, elo: int = 1000) -> StageItemInputFinal:
    """Build a StageItemInputFinal with a unique id and optional ELO."""
    return StageItemInputFinal(
        id=StageItemInputId(n),
        slot=n,
        tournament_id=TournamentId(-1),
        team_id=TeamId(n),
        points=Decimal(str(elo)),
        wins=0,
        draws=0,
        losses=0,
        team=Team.model_validate({**DUMMY_TEAM1.model_dump(), "id": TeamId(n), "active": True}),
    )


def _round_with_match(
    round_id: int,
    inp1: StageItemInputFinal,
    inp2: StageItemInputFinal,
) -> RoundWithMatches:
    """Build a completed round with a single match between inp1 and inp2."""
    base = Match.model_validate(
        DUMMY_MATCH1.model_dump()
        | {
            "id": MatchId(round_id),
            "stage_item_input1_id": inp1.id,
            "stage_item_input2_id": inp2.id,
        }
    )
    match = MatchWithDetailsDefinitive(
        **base.model_dump(),
        stage_item_input1=inp1,
        stage_item_input2=inp2,
        court=None,
    )
    return RoundWithMatches(
        id=RoundId(round_id),
        matches=[match],
        lifecycle_state=RoundLifecycleState.LOCKED,
        stage_item_id=StageItemId(-1),
        name=f"R{round_id}",
        created=DUMMY_MOCK_TIME,
    )


# ── Test 1: Complete matching for even number of teams ────────────────────────


def test_complete_matching_even_teams() -> None:
    """For 4 teams with no history, selector produces 2 pairs covering all teams."""
    from bracket.logic.scheduling.swiss_round_pairing import select_round_pairing

    inputs = [_input(i) for i in range(4)]
    pairs, bye = select_round_pairing(inputs, [])

    assert bye is None
    assert len(pairs) == 2
    all_ids = {inp.id for pair in pairs for inp in pair}
    assert all_ids == {inp.id for inp in inputs}


# ── Test 2: Bye for odd number of teams ───────────────────────────────────────


def test_bye_for_odd_teams() -> None:
    """For 3 teams with no history, selector produces 1 pair and 1 bye."""
    from bracket.logic.scheduling.swiss_round_pairing import select_round_pairing

    inputs = [_input(i) for i in range(3)]
    pairs, bye = select_round_pairing(inputs, [])

    assert bye is not None
    assert len(pairs) == 1
    pair_ids = {inp.id for inp in pairs[0]}
    assert bye.id not in pair_ids
    assert pair_ids | {bye.id} == {inp.id for inp in inputs}


# ── Test 3: Rematch avoidance ──────────────────────────────────────────────────


def test_rematch_avoidance() -> None:
    """Teams that already played each other are not paired again when alternatives exist."""
    from bracket.logic.scheduling.swiss_round_pairing import select_round_pairing

    a, b, c, d = _input(1), _input(2), _input(3), _input(4)
    # Round 1 history: a played b, c played d
    history = [_round_with_match(1, a, b), _round_with_match(2, c, d)]
    pairs, bye = select_round_pairing([a, b, c, d], history)

    assert bye is None
    assert len(pairs) == 2
    pair_sets = {frozenset(inp.id for inp in pair) for pair in pairs}
    assert frozenset({a.id, b.id}) not in pair_sets
    assert frozenset({c.id, d.id}) not in pair_sets


# ── Test 4: Games balance ──────────────────────────────────────────────────────


def test_games_balance_teams_behind_schedule_are_paired() -> None:
    """Teams with zero games played are prioritized over teams that already played.

    Setup: teams a and b have already played each other (1 game each); teams c and d
    are fresh (0 games each). The selector must pair c with d (behind schedule) over
    forcing a rematch of a vs b.
    """
    from bracket.logic.scheduling.swiss_round_pairing import select_round_pairing

    a, b, c, d = _input(1), _input(2), _input(3), _input(4)
    history = [_round_with_match(1, a, b)]
    pairs, bye = select_round_pairing([a, b, c, d], history)

    assert bye is None
    assert len(pairs) == 2
    pair_sets = {frozenset(inp.id for inp in pair) for pair in pairs}
    assert frozenset({c.id, d.id}) in pair_sets
