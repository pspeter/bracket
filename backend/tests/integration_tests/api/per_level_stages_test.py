"""Integration tests for per-level stage activation and progression (issue #19)."""

import asyncpg
import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_LEVEL1,
    DUMMY_LEVEL2,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_level,
    inserted_stage,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage_requires_level_id_when_tournament_has_levels(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_level(
        DUMMY_LEVEL1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        response = await send_tournament_request(
            HTTPMethod.POST, "stages", auth_context, json={}
        )

    assert response == {
        "detail": "level_id is required when the tournament has levels"
    }
    assert await get_full_tournament_details(auth_context.tournament.id) == []


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage_rejects_level_id_for_non_leveled_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(
        HTTPMethod.POST, "stages", auth_context, json={"level_id": 1}
    )

    assert response == {
        "detail": "level_id must be null when the tournament has no levels"
    }
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
async def test_activate_stage_in_level_a_does_not_affect_level_b(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_level(
            DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})
        ) as level_a,
        inserted_level(
            DUMMY_LEVEL2.model_copy(update={"tournament_id": tournament_id})
        ) as level_b,
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level_a.id}
            )
        ) as stage_a1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(
                update={
                    "tournament_id": tournament_id,
                    "level_id": level_a.id,
                    "is_active": False,
                }
            )
        ) as stage_a2,
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level_b.id}
            )
        ) as stage_b1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(
                update={
                    "tournament_id": tournament_id,
                    "level_id": level_b.id,
                    "is_active": False,
                }
            )
        ) as stage_b2,
    ):
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stages/activate",
            auth_context,
            json={"direction": "next", "level_id": level_b.id},
        )
        assert response == SUCCESS_RESPONSE

        stages_after = {
            s.id: s for s in await get_full_tournament_details(tournament_id)
        }

        # Level A unchanged
        assert stages_after[stage_a1.id].is_active is True
        assert stages_after[stage_a2.id].is_active is False
        # Level B progressed
        assert stages_after[stage_b1.id].is_active is False
        assert stages_after[stage_b2.id].is_active is True


@pytest.mark.asyncio(loop_scope="session")
async def test_activate_requires_level_id_when_tournament_has_levels(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_level(
            DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})
        ) as level_a,
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level_a.id}
            )
        ),
        inserted_stage(
            DUMMY_STAGE2.model_copy(
                update={
                    "tournament_id": tournament_id,
                    "level_id": level_a.id,
                    "is_active": False,
                }
            )
        ),
    ):
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stages/activate",
            auth_context,
            json={"direction": "next"},
        )

        assert response == {
            "detail": "level_id is required when the tournament has levels"
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_activate_rejects_level_id_for_non_leveled_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ),
        inserted_stage(
            DUMMY_STAGE2.model_copy(
                update={"tournament_id": tournament_id, "is_active": False}
            )
        ),
    ):
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stages/activate",
            auth_context,
            json={"direction": "next", "level_id": 1},
        )

        assert response == {
            "detail": "level_id must be null when the tournament has no levels"
        }


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

    assert response == {
        "detail": "level_id is required when the tournament has levels"
    }
    assert await get_full_tournament_details(auth_context.tournament.id) == []


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stages_from_template_persists_level_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with inserted_level(
        DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})
    ) as level:
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


@pytest.mark.asyncio(loop_scope="session")
async def test_db_rejects_two_active_stages_in_same_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """The DB itself must prevent two active stages from existing within one level."""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_level(
            DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})
        ) as level,
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level.id}
            )
        ),
    ):
        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            async with inserted_stage(
                DUMMY_STAGE2.model_copy(
                    update={
                        "tournament_id": tournament_id,
                        "level_id": level.id,
                        "is_active": True,
                    }
                )
            ):
                pass


@pytest.mark.asyncio(loop_scope="session")
async def test_db_rejects_two_active_stages_in_non_leveled_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """The original tournament-wide constraint still holds for non-leveled tournaments."""
    tournament_id = auth_context.tournament.id
    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
    ):
        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            async with inserted_stage(
                DUMMY_STAGE2.model_copy(
                    update={"tournament_id": tournament_id, "is_active": True}
                )
            ):
                pass


@pytest.mark.asyncio(loop_scope="session")
async def test_db_allows_one_active_stage_per_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Each level should be allowed exactly one active stage, independently."""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_level(
            DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})
        ) as level_a,
        inserted_level(
            DUMMY_LEVEL2.model_copy(update={"tournament_id": tournament_id})
        ) as level_b,
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level_a.id}
            )
        ),
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level_b.id}
            )
        ),
    ):
        # No exception — both levels can each have one active stage.
        pass


@pytest.mark.asyncio(loop_scope="session")
async def test_pending_matches_in_level_a_do_not_block_level_b(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Level B can advance even when level A's active stage has pending matches."""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_level(
            DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})
        ) as level_a,
        inserted_level(
            DUMMY_LEVEL2.model_copy(update={"tournament_id": tournament_id})
        ) as level_b,
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level_a.id}
            )
        ) as stage_a1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(
                update={
                    "tournament_id": tournament_id,
                    "level_id": level_a.id,
                    "is_active": False,
                }
            )
        ),
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level_b.id}
            )
        ) as stage_b1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(
                update={
                    "tournament_id": tournament_id,
                    "level_id": level_b.id,
                    "is_active": False,
                }
            )
        ) as stage_b2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})
        ) as team_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})
        ) as team_2,
    ):
        # Give level A's active stage a real stage item with pending matches.
        stage_item_a = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_a1.id,
                name=DUMMY_STAGE_ITEM1.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM1.type,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=team_1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=team_2.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item_a, tournament_id)

        # Level A is blocked by its own pending matches.
        blocked = await send_tournament_request(
            HTTPMethod.POST,
            "stages/activate",
            auth_context,
            json={"direction": "next", "level_id": level_a.id},
        )
        assert "pending" in blocked["detail"]

        # Level B can still progress despite level A's pending matches.
        ok = await send_tournament_request(
            HTTPMethod.POST,
            "stages/activate",
            auth_context,
            json={"direction": "next", "level_id": level_b.id},
        )

        stages_after = {
            s.id: s for s in await get_full_tournament_details(tournament_id)
        }
        await sql_delete_stage_item_with_foreign_keys(stage_item_a.id)

        assert ok == SUCCESS_RESPONSE
        assert stages_after[stage_b1.id].is_active is False
        assert stages_after[stage_b2.id].is_active is True


@pytest.mark.asyncio(loop_scope="session")
async def test_next_stage_lookup_scoped_by_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A level whose active stage is the last in its own chain has no next stage,
    even if another level still has unactivated stages."""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_level(
            DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})
        ) as level_a,
        inserted_level(
            DUMMY_LEVEL2.model_copy(update={"tournament_id": tournament_id})
        ) as level_b,
        # Level A's only stage is already the active one.
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level_a.id}
            )
        ),
        # Level B has two stages with one active.
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": tournament_id, "level_id": level_b.id}
            )
        ),
        inserted_stage(
            DUMMY_STAGE2.model_copy(
                update={
                    "tournament_id": tournament_id,
                    "level_id": level_b.id,
                    "is_active": False,
                }
            )
        ),
    ):
        # Advancing level A should fail — no next stage in that level.
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stages/activate",
            auth_context,
            json={"direction": "next", "level_id": level_a.id},
        )

        assert response == {"detail": "There is no next stage"}
