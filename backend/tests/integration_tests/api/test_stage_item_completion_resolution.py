"""Integration test: completing a source stage item auto-resolves dependent inputs in later stages.

This replaces the manual "stage activation" step: a placeholder input like "winner of stage item
foo" resolves to a concrete team as soon as that source stage item completes, without an admin
having to activate the next stage.
"""

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
    StageItemInputFinal,
)
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
)
from tests.integration_tests.api.shared import complete_match
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_stage, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_completing_source_stage_item_resolves_dependent_inputs(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted_1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted_2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        stage_item_1 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM1.name,
                team_count=DUMMY_STAGE_ITEM1.team_count,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                ],
            ),
        )
        stage_item_2 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_2.id,
                name=DUMMY_STAGE_ITEM3.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM3.type,
                inputs=[
                    StageItemInputCreateBodyTentative(
                        slot=1, winner_from_stage_item_id=stage_item_1.id, winner_position=1
                    ),
                    StageItemInputCreateBodyTentative(
                        slot=2, winner_from_stage_item_id=stage_item_1.id, winner_position=2
                    ),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item_1, tournament_id)
        await build_matches_for_stage_item(stage_item_2, tournament_id)

        try:
            # Complete every match in stage item 1 via the transition verbs, which triggers the
            # recalculation + resolution hook. No stage activation is performed.
            [stage_1, _] = await get_full_tournament_details(tournament_id)
            for round_ in stage_1.stage_items[0].rounds:
                for match in round_.matches:
                    for match_set in match.match_sets:
                        await complete_match(auth_context, match.id, match_set.id)

            # The dependent inputs in stage item 2 must now reference concrete teams.
            stages = await get_full_tournament_details(tournament_id)
            next_stage = next(s for s in stages if s.id == stage_inserted_2.id)
            inputs = sorted(next_stage.stage_items[0].inputs, key=lambda i: i.slot)
            assert len(inputs) == 2
            for input_ in inputs:
                assert isinstance(input_, StageItemInputFinal), (
                    f"Expected resolved input, got {type(input_).__name__}"
                )
            assert inputs[0].team_id != inputs[1].team_id
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
            await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)
