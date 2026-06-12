import pytest

from bracket.database import database
from bracket.schema import players, teams
from bracket.utils.dummy_records import DUMMY_LEVEL1, DUMMY_LEVEL2, DUMMY_TEAM1, DUMMY_TEAM2
from bracket.utils.http import HTTPMethod
from bracket.utils.types import JsonDict
from tests.integration_tests.api.shared import send_request, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import enabled_signup, inserted_level, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_none_team_action_without_levels_creates_player_with_no_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    signup_token = "teamless-no-levels-token"
    tournament_id = auth_context.tournament.id

    async with enabled_signup(tournament_id, signup_token):
        response: JsonDict = await send_request(
            HTTPMethod.POST,
            f"signup/{signup_token}",
            json={"player_name": "Teamless Player", "team_action": "none"},
        )
        players_response: JsonDict = await send_tournament_request(
            HTTPMethod.GET, "players", auth_context
        )
        await database.execute(
            query=players.delete().where(players.c.tournament_id == tournament_id)
        )

    assert response == {"success": True}
    player = next(p for p in players_response["data"]["players"] if p["name"] == "Teamless Player")
    assert player["level_id"] is None


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_none_team_action_with_levels_requires_level_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    signup_token = "teamless-levels-no-level-id-token"
    tournament_id = auth_context.tournament.id

    async with (
        enabled_signup(tournament_id, signup_token),
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})),
    ):
        response: JsonDict = await send_request(
            HTTPMethod.POST,
            f"signup/{signup_token}",
            json={"player_name": "Teamless Player", "team_action": "none"},
        )

    assert response["detail"] == "level_id is required when not joining or creating a team"


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_none_team_action_with_level_id_sets_player_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    signup_token = "teamless-with-level-id-token"
    tournament_id = auth_context.tournament.id

    async with (
        enabled_signup(tournament_id, signup_token),
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})) as level,
    ):
        await send_request(
            HTTPMethod.POST,
            f"signup/{signup_token}",
            json={"player_name": "Leveled Teamless", "team_action": "none", "level_id": level.id},
        )
        players_response: JsonDict = await send_tournament_request(
            HTTPMethod.GET, "players", auth_context
        )
        await database.execute(
            query=players.delete().where(players.c.tournament_id == tournament_id)
        )

    player = next(p for p in players_response["data"]["players"] if p["name"] == "Leveled Teamless")
    assert player["level_id"] == level.id


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_create_team_copies_level_to_player(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    signup_token = "create-team-copies-level-token"
    tournament_id = auth_context.tournament.id

    async with (
        enabled_signup(tournament_id, signup_token),
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})) as level,
    ):
        await send_request(
            HTTPMethod.POST,
            f"signup/{signup_token}",
            json={
                "player_name": "Team Creator",
                "team_action": "create",
                "team_name": "New Team",
                "level_id": level.id,
            },
        )
        players_response: JsonDict = await send_tournament_request(
            HTTPMethod.GET, "players", auth_context
        )
        await database.execute(query=teams.delete().where(teams.c.tournament_id == tournament_id))
        await database.execute(
            query=players.delete().where(players.c.tournament_id == tournament_id)
        )

    player = next(p for p in players_response["data"]["players"] if p["name"] == "Team Creator")
    assert player["level_id"] == level.id


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_join_team_copies_level_to_player(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    signup_token = "join-team-copies-level-token"
    tournament_id = auth_context.tournament.id

    async with (
        enabled_signup(tournament_id, signup_token),
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})) as level,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "level_id": level.id})
        ) as team,
    ):
        await send_request(
            HTTPMethod.POST,
            f"signup/{signup_token}",
            json={"player_name": "Team Joiner", "team_action": "join", "team_id": team.id},
        )
        players_response: JsonDict = await send_tournament_request(
            HTTPMethod.GET, "players", auth_context
        )
        await database.execute(
            query=players.delete().where(players.c.tournament_id == tournament_id)
        )

    player = next(p for p in players_response["data"]["players"] if p["name"] == "Team Joiner")
    assert player["level_id"] == level.id


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_unknown_token_returns_404(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    response: JsonDict = await send_request(
        HTTPMethod.GET,
        "signup/nonexistent-token-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )
    assert response == {"detail": "Signup link is invalid or signup is closed"}


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_info_includes_levels_and_team_levels(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    signup_token = "leveled-signup-info-token"
    tournament_id = auth_context.tournament.id

    async with (
        enabled_signup(tournament_id, signup_token),
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})) as level_a,
        inserted_level(DUMMY_LEVEL2.model_copy(update={"tournament_id": tournament_id})) as level_b,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "level_id": level_a.id})
        ) as team_a,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": tournament_id, "level_id": level_b.id})
        ) as team_b,
    ):
        response: JsonDict = await send_request(HTTPMethod.GET, f"signup/{signup_token}")

    assert response["data"]["levels"] == [
        {"id": level_a.id, "name": "Beginners", "position": 0},
        {"id": level_b.id, "name": "Advanced", "position": 1},
    ]
    assert response["data"]["teams"] == [
        {
            "id": team_a.id,
            "name": "Team 1",
            "player_count": 0,
            "is_full": False,
            "level_id": level_a.id,
        },
        {
            "id": team_b.id,
            "name": "Team 2",
            "player_count": 0,
            "is_full": False,
            "level_id": level_b.id,
        },
    ]


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_create_team_requires_level_for_leveled_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    signup_token = "leveled-signup-create-requires-level-token"
    tournament_id = auth_context.tournament.id

    async with (
        enabled_signup(tournament_id, signup_token),
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})),
    ):
        response: JsonDict = await send_request(
            HTTPMethod.POST,
            f"signup/{signup_token}",
            json={
                "player_name": "Signup Player",
                "team_action": "create",
                "team_name": "New Team",
                "team_id": None,
            },
        )

    assert response["detail"] == "level_id is required when creating a team"


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_create_team_assigns_selected_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    signup_token = "leveled-signup-create-team-token"
    tournament_id = auth_context.tournament.id

    async with (
        enabled_signup(tournament_id, signup_token),
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})) as level,
    ):
        response: JsonDict = await send_request(
            HTTPMethod.POST,
            f"signup/{signup_token}",
            json={
                "player_name": "Signup Player",
                "team_action": "create",
                "team_name": "New Team",
                "team_id": None,
                "level_id": level.id,
            },
        )
        signup_info: JsonDict = await send_request(HTTPMethod.GET, f"signup/{signup_token}")
        await database.execute(query=teams.delete().where(teams.c.tournament_id == tournament_id))
        await database.execute(
            query=players.delete().where(players.c.tournament_id == tournament_id)
        )

    assert response == {"success": True}
    assert signup_info["data"]["teams"] == [
        {
            "id": signup_info["data"]["teams"][0]["id"],
            "name": "New Team",
            "player_count": 1,
            "is_full": False,
            "level_id": level.id,
        }
    ]


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_join_existing_leveled_team_does_not_require_level_selection(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    signup_token = "leveled-signup-join-team-token"
    tournament_id = auth_context.tournament.id

    async with (
        enabled_signup(tournament_id, signup_token),
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})) as level,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id, "level_id": level.id})
        ) as team,
    ):
        response: JsonDict = await send_request(
            HTTPMethod.POST,
            f"signup/{signup_token}",
            json={
                "player_name": "Signup Player",
                "team_action": "join",
                "team_id": team.id,
                "team_name": None,
            },
        )
        signup_info: JsonDict = await send_request(HTTPMethod.GET, f"signup/{signup_token}")
        await database.execute(
            query=players.delete().where(players.c.tournament_id == tournament_id)
        )

    assert response == {"success": True}
    assert signup_info["data"]["teams"] == [
        {
            "id": team.id,
            "name": "Team 1",
            "player_count": 1,
            "is_full": False,
            "level_id": level.id,
        }
    ]
