import pytest

from bracket.models.db.stage_item import StageType
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import DUMMY_STAGE1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_stage,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_swiss_placeholder_skeleton_created_on_create(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Creating a Swiss stage item with games_per_player generates placeholder rounds and
    slot-matches.  4 teams, N=2 → 2 rounds × 2 matches each; matches have slot ids set but
    no concrete team assignments yet."""
    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as stage_inserted:
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

        stages_in_tournament = await get_full_tournament_details(auth_context.tournament.id)
        stage_item = next(
            si
            for stage in stages_in_tournament
            if stage.id == stage_inserted.id
            for si in stage.stage_items
        )

        try:
            # 4 teams (even), N=2 → exactly 2 rounds
            assert len(stage_item.rounds) == 2
            for round_ in stage_item.rounds:
                # 4 teams ÷ 2 = 2 matches per round
                assert len(round_.matches) == 2
                for match in round_.matches:
                    # Placeholder: no concrete teams assigned yet
                    assert match.stage_item_input1_id is None
                    assert match.stage_item_input2_id is None
                    # Abstract slot ids must be set and distinct
                    assert match.input1_slot is not None
                    assert match.input2_slot is not None
                    assert match.input1_slot != match.input2_slot
        finally:
            # Clean up in dependency order so the stage FK is satisfied when
            # the inserted_stage context manager runs its DELETE.
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
