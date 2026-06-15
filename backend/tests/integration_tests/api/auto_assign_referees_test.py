import pytest

from bracket.database import database
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import tournaments
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import DUMMY_COURT1, DUMMY_STAGE1, DUMMY_STAGE_ITEM1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_court, inserted_stage, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_auto_assign_referees(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Endpoint fills referee slots on scheduled matches without moving them."""
    tid = auth_context.tournament.id

    await database.execute(
        query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=True)
    )
    try:
        async with (
            inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
            inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t2,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t3,
        ):
            si = await sql_create_stage_item_with_inputs(
                tid,
                StageItemWithInputsCreate(
                    stage_id=stage.id,
                    name=DUMMY_STAGE_ITEM1.name,
                    team_count=3,
                    type=DUMMY_STAGE_ITEM1.type,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                        StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(si, tid)
            await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)

            response = await send_tournament_request(
                HTTPMethod.POST, "matches/auto-assign-referees", auth_context
            )

            stages = await get_full_tournament_details(tid)
            await sql_delete_stage_item_with_foreign_keys(si.id)
    finally:
        await database.execute(
            query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=False)
        )

    assert response == SUCCESS_RESPONSE

    scheduled = [
        match
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.court_id is not None and match.start_time is not None
    ]
    assert len(scheduled) > 0
    assert all(match.referee_id is not None for match in scheduled)
