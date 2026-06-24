"""Integration test: a Swiss stage item created inside an already-active stage resolves round 1
once all of its teams are assigned, without needing the stage to be (re)activated."""

import pytest

from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageType
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_stage,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_swiss_round1_resolves_when_assigned_in_active_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Assigning all teams to a Swiss stage item in an active stage auto-resolves round 1."""
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
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "stage_items",
                auth_context,
                json={
                    "type": StageType.SWISS.value,
                    "team_count": 4,
                    "stage_id": stage_inserted.id,
                    "games_per_player": 2,
                },
            )
            == SUCCESS_RESPONSE
        )

        stages_in_tournament = await get_full_tournament_details(tournament_id)
        stage_item = next(
            si
            for stage in stages_in_tournament
            if stage.id == stage_inserted.id
            for si in stage.stage_items
        )

        try:
            inputs_sorted = sorted(stage_item.inputs, key=lambda input_: input_.slot)
            teams = [t1, t2, t3, t4]

            # Assign all but the last team; round 1 must stay a placeholder until complete.
            for input_, team in zip(inputs_sorted[:-1], teams[:-1]):
                assert (
                    await send_tournament_request(
                        HTTPMethod.PUT,
                        f"stage_items/{stage_item.id}/inputs/{input_.id}",
                        auth_context,
                        json={"team_id": team.id},
                    )
                    == SUCCESS_RESPONSE
                )

            stages_in_tournament = await get_full_tournament_details(tournament_id)
            stage_item = next(
                si
                for stage in stages_in_tournament
                if stage.id == stage_inserted.id
                for si in stage.stage_items
            )
            first_round = min(stage_item.rounds, key=lambda round_: round_.id)
            assert first_round.lifecycle_state == RoundLifecycleState.PLACEHOLDER

            # Assign the final team — this completes the inputs and resolves round 1.
            assert (
                await send_tournament_request(
                    HTTPMethod.PUT,
                    f"stage_items/{stage_item.id}/inputs/{inputs_sorted[-1].id}",
                    auth_context,
                    json={"team_id": teams[-1].id},
                )
                == SUCCESS_RESPONSE
            )

            stages_in_tournament = await get_full_tournament_details(tournament_id)
            stage_item = next(
                si
                for stage in stages_in_tournament
                if stage.id == stage_inserted.id
                for si in stage.stage_items
            )
            rounds_sorted = sorted(stage_item.rounds, key=lambda round_: round_.id)

            # Round 1 is resolved with concrete teams; later rounds stay placeholders.
            assert rounds_sorted[0].lifecycle_state == RoundLifecycleState.RESOLVED
            for match in rounds_sorted[0].matches:
                assert match.stage_item_input1_id is not None
                assert match.stage_item_input2_id is not None
            for round_ in rounds_sorted[1:]:
                assert round_.lifecycle_state == RoundLifecycleState.PLACEHOLDER
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
