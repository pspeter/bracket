"""Integration tests for Swiss pinned rounds (issue #155).

Covers:
1. POST rounds/{id}/swap_inputs swaps match inputs and pins the round.
2. A pinned RESOLVED round is not re-resolved after an upstream score correction.
"""

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.handle_stage_activation import (
    _resolve_round_1_for_swiss_stage_item,
)
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage import Stage
from bracket.models.db.stage_item import StageItem, StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from bracket.utils.id_types import TournamentId
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    complete_match,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_stage,
    inserted_team,
)


async def _build_resolved_swiss_stage(
    tournament_id: TournamentId,
    auth_context: AuthContext,
    stage_inserted: Stage,
    t1: Team,
    t2: Team,
    t3: Team,
    t4: Team,
) -> tuple[StageItem, RoundWithMatches, RoundWithMatches]:
    """Helper: create a 4-team 2-round Swiss stage, resolve round 1, complete all round 1 matches.

    Returns (stage_item_raw, round1, round2_resolved).
    round2_resolved is RESOLVED with concrete team assignments.
    """
    stage_item_raw = await sql_create_stage_item_with_inputs(
        tournament_id,
        StageItemWithInputsCreate(
            stage_id=stage_inserted.id,
            type=StageType.SWISS,
            team_count=4,
            games_per_player=2,
            ranking_id=auth_context.ranking.id,
            inputs=[
                StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
            ],
        ),
    )
    await build_matches_for_stage_item(stage_item_raw, tournament_id)

    stage_item: StageItemWithRounds = await get_stage_item(tournament_id, stage_item_raw.id)
    await _resolve_round_1_for_swiss_stage_item(tournament_id, stage_item)

    stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
    round1, _ = sorted(stage_item.rounds, key=lambda r: r.id)

    for match in round1.matches:
        set_id = match.match_sets[0].id
        resp = await complete_match(auth_context, match.id, set_id, score1=1, score2=0)
        assert resp["data"]["id"] == match.id

    stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
    round1, round2 = sorted(stage_item.rounds, key=lambda r: r.id)
    assert round2.lifecycle_state == RoundLifecycleState.RESOLVED

    return stage_item_raw, round1, round2


@pytest.mark.asyncio(loop_scope="session")
async def test_swap_inputs_pins_round_and_swaps_match_assignments(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """POST rounds/{id}/swap_inputs swaps team assignments and sets is_pinned=True on the round."""
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        try:
            stage_item_raw, _round1, round2 = await _build_resolved_swiss_stage(
                tournament_id, auth_context, stage_inserted, t1, t2, t3, t4
            )

            match_a, match_b = sorted(round2.matches, key=lambda m: m.id)
            assert match_a.stage_item_input1_id is not None
            assert match_a.stage_item_input2_id is not None
            assert match_b.stage_item_input1_id is not None
            assert match_b.stage_item_input2_id is not None

            original_b_input1 = match_b.stage_item_input1_id
            original_b_input2 = match_b.stage_item_input2_id

            resp = await send_tournament_request(
                HTTPMethod.POST,
                f"rounds/{round2.id}/swap_inputs",
                auth_context,
                json={"match1_id": match_a.id, "match2_id": match_b.id},
            )
            assert resp == SUCCESS_RESPONSE

            stage_item: StageItemWithRounds = await get_stage_item(tournament_id, stage_item_raw.id)
            round2_pinned = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2_pinned.is_pinned is True

            swapped_a, swapped_b = sorted(round2_pinned.matches, key=lambda m: m.id)
            assert swapped_a.stage_item_input1_id == original_b_input1
            assert swapped_a.stage_item_input2_id == original_b_input2

        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_pinned_round_survives_upstream_correction(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """After pinning round 2 via swap_inputs, correcting a round-1 score leaves it unchanged."""
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        try:
            stage_item_raw, round1, round2 = await _build_resolved_swiss_stage(
                tournament_id, auth_context, stage_inserted, t1, t2, t3, t4
            )

            match_a, match_b = sorted(round2.matches, key=lambda m: m.id)

            resp = await send_tournament_request(
                HTTPMethod.POST,
                f"rounds/{round2.id}/swap_inputs",
                auth_context,
                json={"match1_id": match_a.id, "match2_id": match_b.id},
            )
            assert resp == SUCCESS_RESPONSE

            stage_item: StageItemWithRounds = await get_stage_item(tournament_id, stage_item_raw.id)
            round2_pinned = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2_pinned.is_pinned is True

            pinned_a, pinned_b = sorted(round2_pinned.matches, key=lambda m: m.id)
            pinned_a_input1 = pinned_a.stage_item_input1_id
            pinned_a_input2 = pinned_a.stage_item_input2_id
            pinned_b_input1 = pinned_b.stage_item_input1_id
            pinned_b_input2 = pinned_b.stage_item_input2_id

            # Upstream correction: reopen a round-1 match and flip its score to shift ELO
            # (triggers orchestrator).
            first_r1_match = sorted(round1.matches, key=lambda m: m.id)[0]
            first_r1_set_id = first_r1_match.match_sets[0].id
            await send_tournament_request(
                HTTPMethod.POST, f"matches/{first_r1_match.id}/reopen", auth_context
            )
            resp = await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{first_r1_match.id}/sets/{first_r1_set_id}/score-edit",
                auth_context,
                json={"stage_item_input1_score": 0, "stage_item_input2_score": 1},
            )
            assert resp["data"]["id"] == first_r1_match.id

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2_after = sorted(stage_item.rounds, key=lambda r: r.id)[1]

            # Pinned round must be untouched by the orchestrator
            assert round2_after.is_pinned is True
            after_a, after_b = sorted(round2_after.matches, key=lambda m: m.id)
            assert after_a.stage_item_input1_id == pinned_a_input1
            assert after_a.stage_item_input2_id == pinned_a_input2
            assert after_b.stage_item_input1_id == pinned_b_input1
            assert after_b.stage_item_input2_id == pinned_b_input2

        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
