"""Integration tests for per-level stages (issue #19)."""

import pytest

from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import DUMMY_LEVEL1, DUMMY_RANKING1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_level,
    inserted_ranking,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage_requires_level_id_when_tournament_has_levels(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_level(
        DUMMY_LEVEL1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        response = await send_tournament_request(HTTPMethod.POST, "stages", auth_context, json={})

    assert response == {"detail": "level_id is required when the tournament has levels"}
    assert await get_full_tournament_details(auth_context.tournament.id) == []


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage_rejects_level_id_for_non_leveled_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(
        HTTPMethod.POST, "stages", auth_context, json={"level_id": 1}
    )

    assert response == {"detail": "level_id must be null when the tournament has no levels"}
    assert await get_full_tournament_details(auth_context.tournament.id) == []


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage_with_level_id_persists_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_level(
        DUMMY_LEVEL1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as level:
        response = await send_tournament_request(
            HTTPMethod.POST, "stages", auth_context, json={"level_id": level.id}
        )

        assert response == SUCCESS_RESPONSE

        [created_stage] = await get_full_tournament_details(auth_context.tournament.id)
        assert created_stage.level_id == level.id

        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stages_from_template_requires_level_id_when_tournament_has_levels(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_level(
        DUMMY_LEVEL1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stages/from-template",
            auth_context,
            json={
                "groups": 2,
                "total_teams": 8,
                "until_rank": 4,
                "include_semi_final": True,
            },
        )

    assert response == {"detail": "level_id is required when the tournament has levels"}
    assert await get_full_tournament_details(auth_context.tournament.id) == []


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stages_from_template_persists_level_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})) as level,
        inserted_ranking(
            DUMMY_RANKING1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level.id, "position": 1}
            )
        ),
    ):
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stages/from-template",
            auth_context,
            json={
                "groups": 2,
                "total_teams": 8,
                "until_rank": 4,
                "include_semi_final": True,
                "level_id": level.id,
            },
        )

        assert "detail" not in response
        stages_after = await get_full_tournament_details(tournament_id)
        assert len(stages_after) > 0
        assert {s.level_id for s in stages_after} == {level.id}

        await assert_row_count_and_clear(matches, 0)
        await assert_row_count_and_clear(stage_item_inputs, 0)
        await assert_row_count_and_clear(rounds, 0)
        await assert_row_count_and_clear(stage_items, 0)
        await assert_row_count_and_clear(stages, 0)
