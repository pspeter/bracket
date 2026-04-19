import aiofiles.os
import aiohttp
import pytest

from bracket.database import database
from bracket.models.db.team import Team
from bracket.schema import players, players_x_teams, teams, tournaments
from bracket.sql.teams import get_teams_with_members
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_PLAYER1, DUMMY_PLAYER2, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_player,
    inserted_player_in_team,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_teams_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        assert await send_tournament_request(HTTPMethod.GET, "teams", auth_context, {}) == {
            "data": {
                "teams": [
                    {
                        "active": True,
                        "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                        "id": team_inserted.id,
                        "name": "Team 1",
                        "players": [],
                        "tournament_id": team_inserted.tournament_id,
                        "elo_score": "1200.0",
                        "swiss_score": "0.0",
                        "wins": 0,
                        "draws": 0,
                        "losses": 0,
                        "logo_path": None,
                    }
                ],
                "count": 1,
            },
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True, "player_ids": []}
    response = await send_tournament_request(HTTPMethod.POST, "teams", auth_context, None, body)
    assert response["data"]["name"] == body["name"]
    await assert_row_count_and_clear(teams, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_teams(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"names": "Team -1,Player 42,Player 43\nTeam -2,", "active": True}
    response = await send_tournament_request(
        HTTPMethod.POST, "teams_multi", auth_context, None, body
    )
    assert response["success"] is True
    await assert_row_count_and_clear(teams, 2)
    await assert_row_count_and_clear(players, 3)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        assert (
            await send_tournament_request(
                HTTPMethod.DELETE, f"teams/{team_inserted.id}", auth_context, {}
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(teams, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True, "player_ids": []}
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team_inserted.id}", auth_context, None, body
        )
        updated_team = await fetch_one_parsed_certain(
            database, Team, query=teams.select().where(teams.c.id == team_inserted.id)
        )
        assert updated_team.name == body["name"]
        assert response["data"]["name"] == body["name"]

        await assert_row_count_and_clear(teams, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_rejects_more_players_than_max_team_size(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tid = auth_context.tournament.id
    await database.execute(
        tournaments.update().where(tournaments.c.id == tid).values(max_team_size=1)
    )
    try:
        async with inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tid})
        ) as team_inserted:
            async with inserted_player(
                DUMMY_PLAYER1.model_copy(update={"tournament_id": tid})
            ) as p1:
                async with inserted_player(
                    DUMMY_PLAYER2.model_copy(update={"tournament_id": tid})
                ) as p2:
                    body = {
                        "name": team_inserted.name,
                        "active": True,
                        "player_ids": [p1.id, p2.id],
                    }
                    response = await send_tournament_request(
                        HTTPMethod.PUT, f"teams/{team_inserted.id}", auth_context, None, body
                    )
                    assert response == {"detail": "This team is full"}
    finally:
        await database.execute(
            tournaments.update().where(tournaments.c.id == tid).values(max_team_size=4)
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_invalid_players(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True, "player_ids": [-1]}
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team_inserted.id}", auth_context, None, body
        )
        assert response == {"detail": "Could not find Player(s) with ID {-1}"}


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team_rejects_players_already_on_other_team_when_disabled(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tid = auth_context.tournament.id
    await database.execute(
        tournaments.update()
        .where(tournaments.c.id == tid)
        .values(players_can_be_in_multiple_teams=False)
    )
    try:
        async with inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tid})
        ) as existing_team:
            async with inserted_player_in_team(
                DUMMY_PLAYER1.model_copy(update={"tournament_id": tid}), existing_team.id
            ) as assigned_player:
                response = await send_tournament_request(
                    HTTPMethod.POST,
                    "teams",
                    auth_context,
                    None,
                    {"name": "Another team", "active": True, "player_ids": [assigned_player.id]},
                )
                assert response == {
                    "detail": "One or more players are already assigned to another team"
                }
    finally:
        await database.execute(
            tournaments.update()
            .where(tournaments.c.id == tid)
            .values(players_can_be_in_multiple_teams=True)
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_rejects_players_already_on_other_team_when_disabled(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tid = auth_context.tournament.id
    await database.execute(
        tournaments.update()
        .where(tournaments.c.id == tid)
        .values(players_can_be_in_multiple_teams=False)
    )
    try:
        async with (
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as existing_team,
            inserted_team(
                DUMMY_TEAM1.model_copy(update={"tournament_id": tid, "name": "Team 2"})
            ) as edited_team,
            inserted_player_in_team(
                DUMMY_PLAYER1.model_copy(update={"tournament_id": tid}), existing_team.id
            ) as assigned_player,
        ):
            response = await send_tournament_request(
                HTTPMethod.PUT,
                f"teams/{edited_team.id}",
                auth_context,
                None,
                {
                    "name": edited_team.name,
                    "active": True,
                    "player_ids": [assigned_player.id],
                },
            )
            assert response == {
                "detail": "One or more players are already assigned to another team"
            }
    finally:
        await database.execute(
            tournaments.update()
            .where(tournaments.c.id == tid)
            .values(players_can_be_in_multiple_teams=True)
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_bulk_create_teams_skips_existing_player_already_on_other_team_when_disabled(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tid = auth_context.tournament.id
    await database.execute(
        tournaments.update()
        .where(tournaments.c.id == tid)
        .values(players_can_be_in_multiple_teams=False)
    )
    try:
        async with inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tid})
        ) as existing_team:
            async with inserted_player_in_team(
                DUMMY_PLAYER1.model_copy(update={"tournament_id": tid, "name": "Assigned Player"}),
                existing_team.id,
            ) as assigned_player:
                response = await send_tournament_request(
                    HTTPMethod.POST,
                    "teams_multi",
                    auth_context,
                    None,
                    {"names": "Fresh Team,Assigned Player", "active": True},
                )
                assert response == SUCCESS_RESPONSE

                tournament_teams = await get_teams_with_members(tid)
                [fresh_team] = [team for team in tournament_teams if team.name == "Fresh Team"]
                assert fresh_team.players == []

                player_links = await database.fetch_all(players_x_teams.select())
                assert len(player_links) == 1
                assert player_links[0]["player_id"] == assigned_player.id

                await database.execute(teams.delete().where(teams.c.id == fresh_team.id))
    finally:
        await database.execute(
            tournaments.update()
            .where(tournaments.c.id == tid)
            .values(players_can_be_in_multiple_teams=True)
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_team_upload_and_remove_logo(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    test_file_path = "tests/integration_tests/assets/test_logo.png"
    data = aiohttp.FormData()
    data.add_field(
        "file",
        open(test_file_path, "rb"),  # pylint: disable=consider-using-with
        filename="test_logo.png",
        content_type="image/png",
    )

    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        response = await send_tournament_request(
            method=HTTPMethod.POST,
            endpoint=f"teams/{team_inserted.id}/logo",
            auth_context=auth_context,
            body=data,
        )

        assert response["data"]["logo_path"], f"Response: {response}"
        assert await aiofiles.os.path.exists(f"static/team-logos/{response['data']['logo_path']}")

        response = await send_tournament_request(
            method=HTTPMethod.POST,
            endpoint="logo",
            auth_context=auth_context,
            body=aiohttp.FormData(),
        )

        assert response["data"]["logo_path"] is None, f"Response: {response}"
        assert not await aiofiles.os.path.exists(
            f"static/team-logos/{response['data']['logo_path']}"
        )
