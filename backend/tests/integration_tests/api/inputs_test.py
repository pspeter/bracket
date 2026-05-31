import pytest

from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.utils.dummy_records import (
    DUMMY_LEVEL1,
    DUMMY_LEVEL2,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import (
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_level,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_available_inputs(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted_1.id, "ranking_id": auth_context.ranking.id}
            )
        ),
    ):
        response = await send_tournament_request(HTTPMethod.GET, "available_inputs", auth_context)

    assert response == {
        "data": {str(stage_inserted_1.id): [{"team_id": team_inserted.id, "already_taken": False}]}
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_available_inputs_are_scoped_to_stage_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_level(
            DUMMY_LEVEL1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as level_a,
        inserted_level(
            DUMMY_LEVEL2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as level_b,
        inserted_team(
            DUMMY_TEAM1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "level_id": level_a.id}
            )
        ) as team_a,
        inserted_team(
            DUMMY_TEAM2.model_copy(
                update={"tournament_id": auth_context.tournament.id, "level_id": level_b.id}
            )
        ) as team_b,
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "level_id": level_a.id}
            )
        ) as stage_a,
        inserted_stage(
            DUMMY_STAGE2.model_copy(
                update={"tournament_id": auth_context.tournament.id, "level_id": level_b.id}
            )
        ) as stage_b,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_a.id, "ranking_id": auth_context.ranking.id}
            )
        ),
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_b.id, "ranking_id": auth_context.ranking.id}
            )
        ),
    ):
        response = await send_tournament_request(HTTPMethod.GET, "available_inputs", auth_context)

    assert response["data"][str(stage_a.id)] == [{"team_id": team_a.id, "already_taken": False}]
    assert response["data"][str(stage_b.id)] == [
        {"team_id": team_b.id, "already_taken": False},
    ]


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_input_rejects_team_from_another_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_level(
            DUMMY_LEVEL1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as level_a,
        inserted_level(
            DUMMY_LEVEL2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as level_b,
        inserted_team(
            DUMMY_TEAM2.model_copy(
                update={"tournament_id": auth_context.tournament.id, "level_id": level_b.id}
            )
        ) as team_b,
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "level_id": level_a.id}
            )
        ) as stage_a,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_a.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_a,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_a.id,
            )
        ) as stage_item_input_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_a.id}/inputs/{stage_item_input_inserted.id}",
            auth_context,
            json={"team_id": team_b.id},
        )

    assert response == {"detail": "Team must belong to the same level as the stage item"}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_input(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted_1.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input1_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_inserted.id}/inputs/{stage_item_input1_inserted.id}",
            auth_context,
            json={"team_id": team_inserted.id},
        )

    assert response == {"success": True}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_input_invalid_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted_1.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input1_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_inserted.id}/inputs/{stage_item_input1_inserted.id}",
            auth_context,
            json={"team_id": -42},
        )

    assert response == {"detail": "Could not find team with id -42"}
