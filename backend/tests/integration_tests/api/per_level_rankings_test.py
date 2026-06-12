"""Integration tests for per-level rankings (issue #21)."""

import pytest

from bracket.logic.tournaments import sql_delete_tournament_completely
from bracket.models.db.stage_item import StageType
from bracket.sql.rankings import get_all_rankings_in_tournament
from bracket.sql.stages import get_full_tournament_details
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


def _create_body(endpoint: str, club_id: int, levels: list[str] | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "Per-Level Rankings Tournament",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "club_id": club_id,
        "dashboard_public": True,
        "dashboard_endpoint": endpoint,
        "players_can_be_in_multiple_teams": False,
        "auto_assign_courts": False,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "signup_enabled": False,
        "max_team_size": 4,
        "signup_team_choice_enabled": True,
    }
    if levels is not None:
        body["levels"] = levels
    return body


@pytest.mark.asyncio(loop_scope="session")
async def test_tournament_with_levels_creates_one_default_ranking_per_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    endpoint = "per-level-rankings-create"
    body = _create_body(endpoint, auth_context.club.id, levels=["Beginners", "Advanced"])
    assert (
        await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body)
        == SUCCESS_RESPONSE
    )

    tournament = assert_some(await sql_get_tournament_by_endpoint_name(endpoint))
    tournament_response = await send_auth_request(
        HTTPMethod.GET, f"tournaments/{tournament.id}", auth_context
    )
    levels_by_name = {lvl["name"]: lvl for lvl in tournament_response["data"]["levels"]}

    rankings = await get_all_rankings_in_tournament(tournament.id)
    assert len(rankings) == 2

    rankings_by_level = {r.level_id: r for r in rankings}
    assert rankings_by_level.keys() == {
        levels_by_name["Beginners"]["id"],
        levels_by_name["Advanced"]["id"],
    }
    for ranking in rankings:
        assert ranking.position == 0

    await sql_delete_tournament_completely(tournament.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_rankings_api_response_includes_level_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    endpoint = "per-level-rankings-api"
    body = _create_body(endpoint, auth_context.club.id, levels=["Beginners", "Advanced"])
    assert (
        await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body)
        == SUCCESS_RESPONSE
    )

    tournament = assert_some(await sql_get_tournament_by_endpoint_name(endpoint))
    tournament_response = await send_auth_request(
        HTTPMethod.GET, f"tournaments/{tournament.id}", auth_context
    )
    level_ids = {lvl["id"] for lvl in tournament_response["data"]["levels"]}

    temp_context = auth_context.model_copy(update={"tournament": tournament})
    rankings_response = await send_tournament_request(HTTPMethod.GET, "rankings", temp_context)

    response_level_ids = {r["level_id"] for r in rankings_response["data"]}
    assert response_level_ids == level_ids

    await sql_delete_tournament_completely(tournament.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_stage_item_defaults_to_its_levels_ranking(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    endpoint = "per-level-rankings-stageitem-default"
    body = _create_body(endpoint, auth_context.club.id, levels=["Beginners", "Advanced"])
    assert (
        await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body)
        == SUCCESS_RESPONSE
    )

    tournament = assert_some(await sql_get_tournament_by_endpoint_name(endpoint))
    tournament_response = await send_auth_request(
        HTTPMethod.GET, f"tournaments/{tournament.id}", auth_context
    )
    levels = tournament_response["data"]["levels"]
    advanced_level_id = next(lvl["id"] for lvl in levels if lvl["name"] == "Advanced")

    rankings = await get_all_rankings_in_tournament(tournament.id)
    advanced_ranking = next(r for r in rankings if r.level_id == advanced_level_id)

    temp_context = auth_context.model_copy(update={"tournament": tournament})
    assert (
        await send_tournament_request(
            HTTPMethod.POST,
            "stages",
            temp_context,
            json={"level_id": advanced_level_id},
        )
        == SUCCESS_RESPONSE
    )
    [stage] = await get_full_tournament_details(tournament.id)

    assert (
        await send_tournament_request(
            HTTPMethod.POST,
            "stage_items",
            temp_context,
            json={
                "type": StageType.SINGLE_ELIMINATION.value,
                "team_count": 2,
                "stage_id": stage.id,
            },
        )
        == SUCCESS_RESPONSE
    )

    [stage_after] = await get_full_tournament_details(tournament.id)
    [stage_item] = stage_after.stage_items
    assert stage_item.ranking_id == advanced_ranking.id

    await sql_delete_tournament_completely(tournament.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_extra_tournament_wide_ranking_can_be_assigned_to_leveled_stage_item(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Additional rankings are level-agnostic (level_id NULL) and usable anywhere."""
    endpoint = "per-level-rankings-extra-shared"
    body = _create_body(endpoint, auth_context.club.id, levels=["Beginners", "Advanced"])
    assert (
        await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body)
        == SUCCESS_RESPONSE
    )

    tournament = assert_some(await sql_get_tournament_by_endpoint_name(endpoint))
    tournament_response = await send_auth_request(
        HTTPMethod.GET, f"tournaments/{tournament.id}", auth_context
    )
    beginners_level_id = next(
        lvl["id"] for lvl in tournament_response["data"]["levels"] if lvl["name"] == "Beginners"
    )

    temp_context = auth_context.model_copy(update={"tournament": tournament})
    assert (
        await send_tournament_request(HTTPMethod.POST, "rankings", temp_context, json={})
        == SUCCESS_RESPONSE
    )

    rankings = await get_all_rankings_in_tournament(tournament.id)
    extra_ranking = next(r for r in rankings if r.level_id is None)

    assert (
        await send_tournament_request(
            HTTPMethod.POST,
            "stages",
            temp_context,
            json={"level_id": beginners_level_id},
        )
        == SUCCESS_RESPONSE
    )
    [stage] = await get_full_tournament_details(tournament.id)

    assert (
        await send_tournament_request(
            HTTPMethod.POST,
            "stage_items",
            temp_context,
            json={
                "type": StageType.SINGLE_ELIMINATION.value,
                "team_count": 2,
                "stage_id": stage.id,
                "ranking_id": extra_ranking.id,
            },
        )
        == SUCCESS_RESPONSE
    )

    [stage_after] = await get_full_tournament_details(tournament.id)
    [stage_item] = stage_after.stage_items
    assert stage_item.ranking_id == extra_ranking.id

    await sql_delete_tournament_completely(tournament.id)
