import pytest

from bracket.database import database
from bracket.models.db.player import Player
from bracket.schema import players
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_PLAYER1, DUMMY_PLAYER2, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import assert_row_count_and_clear, inserted_player, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_players_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_player(
            DUMMY_PLAYER1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as player_inserted:
            assert await send_tournament_request(HTTPMethod.GET, "players", auth_context, {}) == {
                "data": {
                    "players": [
                        {
                            "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                            "id": player_inserted.id,
                            "active": True,
                            "elo_score": "0.0",
                            "swiss_score": "0.0",
                            "wins": 0,
                            "draws": 0,
                            "losses": 0,
                            "name": "Player 01",
                            "tournament_id": auth_context.tournament.id,
                            "level_id": None,
                            "teams": [],
                        }
                    ],
                    "count": 1,
                },
            }


@pytest.mark.asyncio(loop_scope="session")
async def test_create_player(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True}
    response = await send_tournament_request(HTTPMethod.POST, "players", auth_context, json=body)
    assert response["success"] is True
    await assert_row_count_and_clear(players, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_player_with_duplicate_name_is_rejected(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_player(
        DUMMY_PLAYER1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        body = {"name": "player 01", "active": True}
        response = await send_tournament_request(
            HTTPMethod.POST, "players", auth_context, json=body
        )
        assert response["detail"] == "A player with this name already exists"

        remaining_players = await database.fetch_all(
            query=players.select().where(players.c.tournament_id == auth_context.tournament.id)
        )
        assert [p["name"] for p in remaining_players] == ["Player 01"]

        await assert_row_count_and_clear(players, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_players(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"names": "Player x\nPlayer y", "active": True}
    response = await send_tournament_request(
        HTTPMethod.POST, "players_multi", auth_context, json=body
    )
    assert response["success"] is True
    await assert_row_count_and_clear(players, 2)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_players_multi_rejects_name_that_already_exists(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_player(
        DUMMY_PLAYER1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        body = {"names": "Player x\nplayer 01", "active": True}
        response = await send_tournament_request(
            HTTPMethod.POST, "players_multi", auth_context, json=body
        )
        assert "already exists" in response["detail"]

        remaining_players = await database.fetch_all(
            query=players.select().where(players.c.tournament_id == auth_context.tournament.id)
        )
        assert [p["name"] for p in remaining_players] == ["Player 01"]

        await assert_row_count_and_clear(players, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_players_multi_rejects_duplicate_names_within_submission(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"names": "Player x\nplayer X", "active": True}
    response = await send_tournament_request(
        HTTPMethod.POST, "players_multi", auth_context, json=body
    )
    assert "already exists" in response["detail"]

    remaining_players = await database.fetch_all(
        query=players.select().where(players.c.tournament_id == auth_context.tournament.id)
    )
    assert remaining_players == []

    await assert_row_count_and_clear(players, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_player(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_player(
            DUMMY_PLAYER1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as player_inserted:
            assert (
                await send_tournament_request(
                    HTTPMethod.DELETE, f"players/{player_inserted.id}", auth_context
                )
                == SUCCESS_RESPONSE
            )
            await assert_row_count_and_clear(players, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_player_rejects_rename_to_existing_player_name(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_player(
            DUMMY_PLAYER1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as player1,
        inserted_player(
            DUMMY_PLAYER2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as player2,
    ):
        body = {"name": player1.name, "active": True}
        response = await send_tournament_request(
            HTTPMethod.PUT, f"players/{player2.id}", auth_context, json=body
        )
        assert response["detail"] == "A player with this name already exists"

        unchanged_player = await fetch_one_parsed_certain(
            database, Player, query=players.select().where(players.c.id == player2.id)
        )
        assert unchanged_player.name == "Player 02"

        await assert_row_count_and_clear(players, 2)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_player_allows_case_only_rename_to_own_name(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_player(
        DUMMY_PLAYER1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as player1:
        body = {"name": "PLAYER 01", "active": True}
        response = await send_tournament_request(
            HTTPMethod.PUT, f"players/{player1.id}", auth_context, json=body
        )
        assert response["data"]["name"] == "PLAYER 01"

        updated_player = await fetch_one_parsed_certain(
            database, Player, query=players.select().where(players.c.id == player1.id)
        )
        assert updated_player.name == "PLAYER 01"

        await assert_row_count_and_clear(players, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_player(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True}
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_player(
            DUMMY_PLAYER1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as player_inserted:
            response = await send_tournament_request(
                HTTPMethod.PUT, f"players/{player_inserted.id}", auth_context, json=body
            )
            updated_player = await fetch_one_parsed_certain(
                database, Player, query=players.select().where(players.c.id == player_inserted.id)
            )
            assert updated_player.name == body["name"]
            assert response["data"]["name"] == body["name"]

            await assert_row_count_and_clear(players, 1)
