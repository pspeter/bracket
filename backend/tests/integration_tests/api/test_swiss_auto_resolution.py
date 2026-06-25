"""Integration test: completing round 1 of a Swiss stage item auto-resolves round 2 (issue #153)."""

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.handle_stage_activation import (
    _resolve_round_1_for_swiss_stage_item,
)
from bracket.models.db.match import MatchSetState
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_stage,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_completing_round1_auto_resolves_round2(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Completing all matches in round 1 of a Swiss stage automatically fills round 2."""
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id, "is_active": True})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
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

        stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
        assert len(stage_item.rounds) == 2

        # Resolve round 1 (simulates stage activation)
        await _resolve_round_1_for_swiss_stage_item(tournament_id, stage_item)

        stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
        round1 = sorted(stage_item.rounds, key=lambda r: r.id)[0]
        round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
        assert round1.lifecycle_state == RoundLifecycleState.RESOLVED
        assert round2.lifecycle_state == RoundLifecycleState.PLACEHOLDER

        try:
            # Complete all round 1 matches via the per-set HTTP API — this triggers the orchestrator
            for match in round1.matches:
                set_id = match.match_sets[0].id
                resp = await send_tournament_request(
                    HTTPMethod.PUT,
                    f"matches/{match.id}/sets/{set_id}",
                    auth_context,
                    json={
                        "state": MatchSetState.COMPLETED.value,
                        "stage_item_input1_score": 0,
                        "stage_item_input2_score": 0,
                    },
                )
                assert resp["data"]["id"] == match.id

            # Round 2 must now be RESOLVED with concrete teams
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2_resolved = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2_resolved.lifecycle_state == RoundLifecycleState.RESOLVED
            for match in round2_resolved.matches:
                assert match.stage_item_input1_id is not None
                assert match.stage_item_input2_id is not None

        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
