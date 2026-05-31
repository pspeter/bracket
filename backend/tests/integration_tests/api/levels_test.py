import pytest

from bracket.logic.tournaments import sql_delete_tournament_completely
from bracket.sql.tournaments import sql_get_tournament_by_endpoint_name
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.http import HTTPMethod
from bracket.utils.types import assert_some
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_auth_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext


@pytest.mark.asyncio(loop_scope="session")
async def test_create_tournament_with_levels(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    dashboard_endpoint = "levels-test-endpoint"
    body = {
        "name": "Leveled Tournament",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "club_id": auth_context.club.id,
        "dashboard_public": True,
        "dashboard_endpoint": dashboard_endpoint,
        "players_can_be_in_multiple_teams": False,
        "auto_assign_courts": False,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "signup_enabled": False,
        "max_team_size": 4,
        "signup_team_choice_enabled": True,
        "levels": ["Beginners", "Advanced"],
    }
    assert (
        await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body)
        == SUCCESS_RESPONSE
    )

    tournament = assert_some(await sql_get_tournament_by_endpoint_name(dashboard_endpoint))
    response = await send_auth_request(HTTPMethod.GET, f"tournaments/{tournament.id}", auth_context)

    levels = response["data"]["levels"]
    assert len(levels) == 2
    assert levels[0]["name"] == "Beginners"
    assert levels[0]["position"] == 0
    assert levels[1]["name"] == "Advanced"
    assert levels[1]["position"] == 1
    assert all("id" in level for level in levels)

    await sql_delete_tournament_completely(tournament.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_cannot_add_levels_after_creation(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Sending levels on tournament PUT is rejected with a validation error."""
    dashboard_endpoint = "immutable-levels-test"
    create_body = {
        "name": "Immutable Levels Tournament",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "club_id": auth_context.club.id,
        "dashboard_public": True,
        "dashboard_endpoint": dashboard_endpoint,
        "players_can_be_in_multiple_teams": False,
        "auto_assign_courts": False,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "signup_enabled": False,
        "max_team_size": 4,
        "signup_team_choice_enabled": True,
        "levels": ["Beginners"],
    }
    assert (
        await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=create_body)
        == SUCCESS_RESPONSE
    )

    tournament = assert_some(await sql_get_tournament_by_endpoint_name(dashboard_endpoint))

    update_body = {
        "name": "Immutable Levels Tournament",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "dashboard_public": True,
        "dashboard_endpoint": dashboard_endpoint,
        "players_can_be_in_multiple_teams": False,
        "auto_assign_courts": False,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "signup_enabled": False,
        "max_team_size": 4,
        "signup_team_choice_enabled": True,
        "levels": ["Beginners", "Advanced", "Expert"],
    }
    temp_context = auth_context.model_copy(update={"tournament": tournament})
    response = await send_tournament_request(HTTPMethod.PUT, "", temp_context, json=update_body)
    assert "detail" in response
    error_msg = response["detail"][0]["msg"]
    assert "Levels cannot be changed after tournament creation" in error_msg

    await sql_delete_tournament_completely(tournament.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_rename_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    dashboard_endpoint = "rename-level-test"
    body = {
        "name": "Rename Test Tournament",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "club_id": auth_context.club.id,
        "dashboard_public": True,
        "dashboard_endpoint": dashboard_endpoint,
        "players_can_be_in_multiple_teams": False,
        "auto_assign_courts": False,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "signup_enabled": False,
        "max_team_size": 4,
        "signup_team_choice_enabled": True,
        "levels": ["Beginners", "Advanced"],
    }
    assert (
        await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body)
        == SUCCESS_RESPONSE
    )

    tournament = assert_some(await sql_get_tournament_by_endpoint_name(dashboard_endpoint))
    response = await send_auth_request(HTTPMethod.GET, f"tournaments/{tournament.id}", auth_context)
    level_id = response["data"]["levels"][0]["id"]

    temp_context = auth_context.model_copy(update={"tournament": tournament})
    assert (
        await send_tournament_request(
            HTTPMethod.PUT,
            f"levels/{level_id}",
            temp_context,
            json={"name": "Intermediate"},
        )
        == SUCCESS_RESPONSE
    )

    response = await send_auth_request(HTTPMethod.GET, f"tournaments/{tournament.id}", auth_context)
    assert response["data"]["levels"][0]["name"] == "Intermediate"
    assert response["data"]["levels"][1]["name"] == "Advanced"

    await sql_delete_tournament_completely(tournament.id)
