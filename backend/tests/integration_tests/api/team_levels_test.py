"""Integration tests for team level assignment and validation (issue #20)."""

import pytest

from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.schema import teams
from bracket.sql.teams import get_team_by_id, get_teams_with_members
from bracket.utils.dummy_records import (
    DUMMY_LEVEL1,
    DUMMY_LEVEL2,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_level,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team_requires_level_id_when_tournament_has_levels(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_level(
        DUMMY_LEVEL1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        body = {"name": "Team A", "active": True, "player_ids": []}
        response = await send_tournament_request(
            HTTPMethod.POST, "teams", auth_context, None, body
        )
    assert response == {"detail": "level_id is required when the tournament has levels"}
    await assert_row_count_and_clear(teams, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team_persists_level_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tid = auth_context.tournament.id
    async with inserted_level(
        DUMMY_LEVEL1.model_copy(update={"tournament_id": tid})
    ) as level:
        body = {
            "name": "Team A",
            "active": True,
            "player_ids": [],
            "level_id": level.id,
        }
        response = await send_tournament_request(
            HTTPMethod.POST, "teams", auth_context, None, body
        )
        assert response["data"]["level_id"] == level.id

        team = await get_team_by_id(response["data"]["id"], tid)
        assert team is not None
        assert team.level_id == level.id

        get_response = await send_tournament_request(HTTPMethod.GET, "teams", auth_context, {})
        assert get_response["data"]["teams"][0]["level_id"] == level.id

        await assert_row_count_and_clear(teams, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team_rejects_level_id_when_no_levels(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Team A", "active": True, "player_ids": [], "level_id": 1}
    response = await send_tournament_request(
        HTTPMethod.POST, "teams", auth_context, None, body
    )
    assert response == {"detail": "level_id must be null when the tournament has no levels"}
    await assert_row_count_and_clear(teams, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_teams_multi_applies_level_id_to_batch(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tid = auth_context.tournament.id
    async with inserted_level(
        DUMMY_LEVEL1.model_copy(update={"tournament_id": tid})
    ) as level:
        body = {
            "names": "Team -1,\nTeam -2,",
            "active": True,
            "level_id": level.id,
        }
        response = await send_tournament_request(
            HTTPMethod.POST, "teams_multi", auth_context, None, body
        )
        assert response["success"] is True

        created = await get_teams_with_members(tid)
        assert len(created) == 2
        assert all(t.level_id == level.id for t in created)

        await assert_row_count_and_clear(teams, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_changes_level_when_unassigned(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tid = auth_context.tournament.id
    async with (
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tid})) as level_a,
        inserted_level(DUMMY_LEVEL2.model_copy(update={"tournament_id": tid})) as level_b,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tid, "level_id": level_a.id})
        ) as team,
    ):
        body = {
            "name": team.name,
            "active": True,
            "player_ids": [],
            "level_id": level_b.id,
        }
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team.id}", auth_context, None, body
        )
        assert response["data"]["level_id"] == level_b.id

        refreshed = await get_team_by_id(team.id, tid)
        assert refreshed is not None
        assert refreshed.level_id == level_b.id


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_rejects_level_change_when_assigned_to_stage_item(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tid = auth_context.tournament.id
    async with (
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tid})) as level_a,
        inserted_level(DUMMY_LEVEL2.model_copy(update={"tournament_id": tid})) as level_b,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tid, "level_id": level_a.id})
        ) as team,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tid, "level_id": level_a.id})
        ) as stage,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team.id,
                tournament_id=tid,
                stage_item_id=stage_item.id,
            )
        ),
    ):
        body = {
            "name": team.name,
            "active": True,
            "player_ids": [],
            "level_id": level_b.id,
        }
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team.id}", auth_context, None, body
        )
        assert response == {
            "detail": "Cannot change level: team is assigned to a stage item"
        }

        refreshed = await get_team_by_id(team.id, tid)
        assert refreshed is not None
        assert refreshed.level_id == level_a.id


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_allows_other_changes_when_assigned_if_level_unchanged(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tid = auth_context.tournament.id
    async with (
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tid})) as level_a,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tid, "level_id": level_a.id})
        ) as team,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tid, "level_id": level_a.id})
        ) as stage,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team.id,
                tournament_id=tid,
                stage_item_id=stage_item.id,
            )
        ),
    ):
        body = {
            "name": "Renamed",
            "active": False,
            "player_ids": [],
            "level_id": level_a.id,
        }
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team.id}", auth_context, None, body
        )
        assert response["data"]["name"] == "Renamed"
        assert response["data"]["level_id"] == level_a.id
