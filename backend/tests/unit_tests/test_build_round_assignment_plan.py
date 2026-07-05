"""Unit tests for build_round_assignment_plan, the pure planner behind Swiss round resolution
(formerly the writing half of swiss_resolution_orchestrator._assign_teams_to_round).
"""

from collections.abc import Sequence
from decimal import Decimal

from bracket.logic.plan import SetMatchInputs, SetRoundLifecycleState
from bracket.logic.scheduling.swiss_resolution_orchestrator import build_round_assignment_plan
from bracket.models.db.match import Match, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputEmpty,
    StageItemInputFinal,
    StageItemInputTentative,
)
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.dummy_records import DUMMY_MATCH1, DUMMY_MOCK_TIME, DUMMY_TEAM1
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


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
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(n)),
    )


def _placeholder_match(
    match_id: int, round_id: int, input1_slot: int, input2_slot: int
) -> MatchWithDetails:
    base = Match.model_validate(
        DUMMY_MATCH1.model_dump()
        | {
            "id": MatchId(match_id),
            "round_id": RoundId(round_id),
            "stage_item_input1_id": None,
            "stage_item_input2_id": None,
            "input1_slot": input1_slot,
            "input2_slot": input2_slot,
        }
    )
    return MatchWithDetails(**base.model_dump(), court=None)


def _placeholder_round(
    round_id: int, matches: Sequence[MatchWithDetailsDefinitive | MatchWithDetails]
) -> RoundWithMatches:
    return RoundWithMatches(
        id=RoundId(round_id),
        matches=list(matches),
        lifecycle_state=RoundLifecycleState.PLACEHOLDER,
        stage_item_id=StageItemId(-1),
        name=f"R{round_id}",
        created=DUMMY_MOCK_TIME,
    )


def _stage_item(
    inputs: Sequence[StageItemInputTentative | StageItemInputFinal | StageItemInputEmpty],
    rounds: list[RoundWithMatches],
) -> StageItemWithRounds:
    return StageItemWithRounds(
        rounds=rounds,
        inputs=list(inputs),
        type_name="Swiss",
        team_count=max(len(inputs), 2),
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=DUMMY_MOCK_TIME,
        type=StageType.SWISS,
    )


def test_build_round_assignment_plan_pairs_all_inputs_and_advances_round() -> None:
    """For 4 active inputs and no round history, the plan wires both matches' slots to concrete
    inputs and, with advance_to_resolved=True, appends a RESOLVED lifecycle transition.
    """
    inputs = [_input(i) for i in range(1, 5)]
    match1 = _placeholder_match(1, round_id=-1, input1_slot=0, input2_slot=1)
    match2 = _placeholder_match(2, round_id=-1, input1_slot=2, input2_slot=3)
    round_ = _placeholder_round(-1, [match1, match2])
    stage_item = _stage_item(inputs, [round_])

    plan = build_round_assignment_plan(stage_item, round_, advance_to_resolved=True)

    set_match_inputs = [item for item in plan if isinstance(item, SetMatchInputs)]
    lifecycle_items = [item for item in plan if isinstance(item, SetRoundLifecycleState)]

    assert len(set_match_inputs) == 2
    all_assigned_ids = {
        input_id for item in set_match_inputs for input_id in item.input_ids if input_id is not None
    }
    assert all_assigned_ids == {inp.id for inp in inputs}
    for item in set_match_inputs:
        assert item.round_id == round_.id
        assert None not in item.input_ids

    assert lifecycle_items == [
        SetRoundLifecycleState(round_id=round_.id, state=RoundLifecycleState.RESOLVED)
    ]


def test_build_round_assignment_plan_no_lifecycle_item_when_not_advancing() -> None:
    """advance_to_resolved=False (the re-resolution pass) never appends a lifecycle transition."""
    inputs = [_input(i) for i in range(1, 5)]
    match1 = _placeholder_match(1, round_id=-1, input1_slot=0, input2_slot=1)
    match2 = _placeholder_match(2, round_id=-1, input1_slot=2, input2_slot=3)
    round_ = _placeholder_round(-1, [match1, match2])
    stage_item = _stage_item(inputs, [round_])

    plan = build_round_assignment_plan(stage_item, round_, advance_to_resolved=False)

    assert not any(isinstance(item, SetRoundLifecycleState) for item in plan)
    assert sum(1 for item in plan if isinstance(item, SetMatchInputs)) == 2


def test_build_round_assignment_plan_empty_when_no_active_inputs() -> None:
    """No active final inputs means nothing to pair: the plan is empty."""
    round_ = _placeholder_round(-1, [])
    stage_item = _stage_item([], [round_])

    plan = build_round_assignment_plan(stage_item, round_, advance_to_resolved=True)

    assert not plan
