import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import rounds, stage_items, stages
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_MOCK_TIME,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_team,
)


@pytest.mark.parametrize(("with_auth",), [(True,), (False,)])
@pytest.mark.asyncio(loop_scope="session")
async def test_stages_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext, with_auth: bool
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
    ):
        if with_auth:
            response = await send_tournament_request(HTTPMethod.GET, "stages", auth_context, {})
        else:
            response = await send_request(
                HTTPMethod.GET,
                f"tournaments/{auth_context.tournament.id}/stages?no_draft_rounds=true",
            )
        assert response == {
            "data": [
                {
                    "id": stage_inserted.id,
                    "tournament_id": auth_context.tournament.id,
                    "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                    "is_active": True,
                    "name": "Group Stage",
                    "stage_items": [
                        {
                            "id": stage_item_inserted.id,
                            "stage_id": stage_inserted.id,
                            "ranking_id": auth_context.ranking.id,
                            "name": "Group A",
                            "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                            "type": "ROUND_ROBIN",
                            "team_count": 4,
                            "rounds": [
                                {
                                    "id": round_inserted.id,
                                    "stage_item_id": stage_item_inserted.id,
                                    "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                                    "is_draft": False,
                                    "name": "Round 1",
                                    "matches": [],
                                }
                            ],
                            "inputs": [],
                            "type_name": "Round robin",
                        }
                    ],
                }
            ]
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "stages",
                auth_context,
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(rounds, 1)
        await assert_row_count_and_clear(stage_items, 1)
        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.DELETE, f"stages/{stage_inserted.id}", auth_context, {}
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Optimus"}
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ),
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.PUT, f"stages/{stage_inserted.id}", auth_context, None, body
            )
            == SUCCESS_RESPONSE
        )
        [updated_stage] = await get_full_tournament_details(auth_context.tournament.id)
        assert len(updated_stage.stage_items) == 1
        assert updated_stage.name == body["name"]

        await assert_row_count_and_clear(stage_items, 1)
        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_activate_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.POST, "stages/activate?direction=next", auth_context, json={}
            )
            == SUCCESS_RESPONSE
        )

        await assert_row_count_and_clear(stage_items, 1)
        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_get_next_stage_rankings(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ),
    ):
        response = await send_tournament_request(
            HTTPMethod.GET, "next_stage_rankings", auth_context
        )

    assert response == {
        "data": {},
        "has_pending_matches": False,
        "pending_match_count": 0,
        "pending_matches_message": None,
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_get_next_stage_rankings_includes_pending_match_warning(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
    ):
        stage_item_1 = await sql_create_stage_item_with_inputs(
            auth_context.tournament.id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM1.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM1.type,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id),
                ],
            ),
        )
        stage_item_2 = await sql_create_stage_item_with_inputs(
            auth_context.tournament.id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_2.id,
                name=DUMMY_STAGE_ITEM1.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM1.type,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item_1, auth_context.tournament.id)

        response = await send_tournament_request(
            HTTPMethod.GET, "next_stage_rankings", auth_context
        )

        await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
        await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)

    assert response["data"] == {}
    assert response["has_pending_matches"] is True
    assert response["pending_match_count"] == 1
    assert response["pending_matches_message"] == (
        "The active stage still has pending matches. "
        "Complete all 1 pending match before starting the next stage."
    )
