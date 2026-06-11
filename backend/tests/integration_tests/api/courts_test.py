import pytest

from bracket.database import database
from bracket.models.db.court import Court
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.schema import courts
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_MATCH1,
    DUMMY_MOCK_TIME,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_court,
    inserted_match,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_courts_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted:
            assert await send_tournament_request(HTTPMethod.GET, "courts", auth_context, {}) == {
                "data": [
                    {
                        "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                        "id": court_inserted.id,
                        "name": "Court 1",
                        "tournament_id": auth_context.tournament.id,
                    }
                ],
            }


@pytest.mark.asyncio(loop_scope="session")
async def test_courts_sorted_naturally(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "name": "Court 10"}
            )
        ),
        inserted_court(
            DUMMY_COURT1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "name": "Court 2"}
            )
        ),
    ):
        response = await send_tournament_request(HTTPMethod.GET, "courts", auth_context, {})
        # Numbered names sort numerically, not as plain strings ("10" < "2").
        assert [court["name"] for court in response["data"]] == ["Court 2", "Court 10"]


@pytest.mark.asyncio(loop_scope="session")
async def test_create_court(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True}
    response = await send_tournament_request(HTTPMethod.POST, "courts", auth_context, json=body)
    assert response["data"]["name"] == body["name"]
    await assert_row_count_and_clear(courts, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_court(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted:
            assert (
                await send_tournament_request(
                    HTTPMethod.DELETE, f"courts/{court_inserted.id}", auth_context
                )
                == SUCCESS_RESPONSE
            )
            await assert_row_count_and_clear(courts, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_court_used_by_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "ranking_id": auth_context.ranking.id,
                    "type": StageType.SWISS,
                }
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team1_inserted,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team2_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input1_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input2_inserted,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court_inserted.id,
                }
            )
        ),
    ):
        response = await send_tournament_request(
            HTTPMethod.DELETE, f"courts/{court_inserted.id}", auth_context
        )
        assert response == {"detail": "Could not delete court since it's used by 1 matches"}
        court_still_there = await fetch_one_parsed_certain(
            database, Court, query=courts.select().where(courts.c.id == court_inserted.id)
        )
        assert court_still_there.id == court_inserted.id


@pytest.mark.asyncio(loop_scope="session")
async def test_update_court(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name"}
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted:
            response = await send_tournament_request(
                HTTPMethod.PUT, f"courts/{court_inserted.id}", auth_context, json=body
            )
            updated_court = await fetch_one_parsed_certain(
                database, Court, query=courts.select().where(courts.c.id == court_inserted.id)
            )
            assert updated_court.name == body["name"]
            assert response["data"]["name"] == body["name"]

            await assert_row_count_and_clear(courts, 1)
