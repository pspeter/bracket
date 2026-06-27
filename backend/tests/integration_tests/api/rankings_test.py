from decimal import Decimal
from unittest.mock import ANY

import pytest

from bracket.models.db.ranking import ScoringType
from bracket.sql.rankings import (
    get_all_rankings_in_tournament,
    sql_delete_ranking,
)
from bracket.utils.dummy_records import (
    DUMMY_RANKING1,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_ranking,
    inserted_stage,
    inserted_stage_item,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_rankings_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        result = await send_tournament_request(HTTPMethod.GET, "rankings", auth_context, {})
        assert result == {
            "data": [
                {
                    "created": ANY,
                    "id": auth_context.ranking.id,
                    "position": 0,
                    "name": "",
                    "scoring_type": "MATCH_POINTS",
                    "num_sets": 1,
                    "max_points": 21,
                    "last_set_max_points": None,
                    "two_point_advantage": True,
                    "match_points": {
                        "win_points": "1.0",
                        "draw_points": "0.5",
                        "loss_points": "0.0",
                    },
                    "set_points_with_bonus": None,
                    "tournament_id": auth_context.tournament.id,
                    "level_id": None,
                    "side_switch_every_n_points": None,
                }
            ],
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_create_ranking_match_points(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(
        HTTPMethod.POST,
        "rankings",
        auth_context,
        json={"scoring_type": "MATCH_POINTS"},
    )
    assert response.get("success") is True, response

    tournament_id = auth_context.tournament.id
    for ranking in await get_all_rankings_in_tournament(tournament_id):
        if ranking.position != 0:
            await sql_delete_ranking(tournament_id, ranking.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_ranking_set_points(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(
        HTTPMethod.POST,
        "rankings",
        auth_context,
        json={"scoring_type": "SET_POINTS", "position": 1},
    )
    assert response.get("success") is True, response

    tournament_id = auth_context.tournament.id
    rankings_list = await get_all_rankings_in_tournament(tournament_id)
    set_points_ranking = next(
        (r for r in rankings_list if r.scoring_type == ScoringType.SET_POINTS), None
    )
    assert set_points_ranking is not None
    assert set_points_ranking.match_points is None
    await sql_delete_ranking(tournament_id, set_points_ranking.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_ranking_set_points_with_match_bonus(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(
        HTTPMethod.POST,
        "rankings",
        auth_context,
        json={"scoring_type": "SET_POINTS_WITH_MATCH_BONUS", "match_bonus_points": "2.0"},
    )
    assert response.get("success") is True, response

    tournament_id = auth_context.tournament.id
    rankings_list = await get_all_rankings_in_tournament(tournament_id)
    bonus_ranking = next(
        (r for r in rankings_list if r.scoring_type == ScoringType.SET_POINTS_WITH_MATCH_BONUS),
        None,
    )
    assert bonus_ranking is not None
    assert bonus_ranking.set_points_with_bonus is not None
    assert bonus_ranking.set_points_with_bonus.match_bonus_points == Decimal("2.0")
    await sql_delete_ranking(tournament_id, bonus_ranking.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_ranking(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as ranking_inserted:
            assert (
                await send_tournament_request(
                    HTTPMethod.DELETE, f"rankings/{ranking_inserted.id}", auth_context
                )
                == SUCCESS_RESPONSE
            )


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_match_points(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {
        "scoring_type": "MATCH_POINTS",
        "win_points": "7.5",
        "draw_points": "2.5",
        "loss_points": "6.0",
        "position": 42,
    }
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as ranking_inserted:
            response = await send_tournament_request(
                HTTPMethod.PUT, f"rankings/{ranking_inserted.id}", auth_context, json=body
            )
            assert response["success"] is True
            updated_rankings = await get_all_rankings_in_tournament(auth_context.tournament.id)
            updated = next(r for r in updated_rankings if r.id == ranking_inserted.id)
            assert updated.match_points is not None
            assert updated.match_points.win_points == Decimal("7.5")


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_changes_scoring_type(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """PUT with a different scoring_type removes old subtype row and inserts new one."""
    body = {
        "scoring_type": "SET_POINTS",
        "position": 0,
    }
    async with inserted_ranking(
        DUMMY_RANKING1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as ranking_inserted:
        response = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_inserted.id}", auth_context, json=body
        )
        assert response["success"] is True
        updated_rankings = await get_all_rankings_in_tournament(auth_context.tournament.id)
        updated = next(r for r in updated_rankings if r.id == ranking_inserted.id)
        assert updated.scoring_type == ScoringType.SET_POINTS
        assert updated.match_points is None


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_preserves_position_when_omitted(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A PUT without `position` keeps the existing position instead of resetting it to 0."""
    base_body = {
        "scoring_type": "MATCH_POINTS",
        "win_points": "1.0",
        "draw_points": "0.5",
        "loss_points": "0.0",
    }
    async with inserted_ranking(
        DUMMY_RANKING1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as ranking_inserted:
        # First set an explicit non-zero position
        await send_tournament_request(
            HTTPMethod.PUT,
            f"rankings/{ranking_inserted.id}",
            auth_context,
            json={**base_body, "position": 7},
        )
        # Now update again without sending a position
        response = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_inserted.id}", auth_context, json=base_body
        )
        assert response["success"] is True
        updated_rankings = await get_all_rankings_in_tournament(auth_context.tournament.id)
        updated = next(r for r in updated_rankings if r.id == ranking_inserted.id)
        assert updated.position == 7


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_name(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {
        "scoring_type": "MATCH_POINTS",
        "win_points": "1.0",
        "draw_points": "0.5",
        "loss_points": "0.0",
        "position": 0,
        "name": "Fair play ranking",
    }
    async with inserted_ranking(
        DUMMY_RANKING1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as ranking_inserted:
        response = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_inserted.id}", auth_context, json=body
        )
        assert response["success"] is True
        updated_rankings = await get_all_rankings_in_tournament(auth_context.tournament.id)
        updated = next(r for r in updated_rankings if r.id == ranking_inserted.id)
        assert updated.name == "Fair play ranking"


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_preserves_name_when_omitted(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A PUT without `name` keeps the existing name instead of clearing it."""
    base_body = {
        "scoring_type": "MATCH_POINTS",
        "win_points": "1.0",
        "draw_points": "0.5",
        "loss_points": "0.0",
    }
    async with inserted_ranking(
        DUMMY_RANKING1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as ranking_inserted:
        await send_tournament_request(
            HTTPMethod.PUT,
            f"rankings/{ranking_inserted.id}",
            auth_context,
            json={**base_body, "name": "Keep me"},
        )
        response = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_inserted.id}", auth_context, json=base_body
        )
        assert response["success"] is True
        updated_rankings = await get_all_rankings_in_tournament(auth_context.tournament.id)
        updated = next(r for r in updated_rankings if r.id == ranking_inserted.id)
        assert updated.name == "Keep me"


@pytest.mark.asyncio(loop_scope="session")
async def test_create_ranking_with_name(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(
        HTTPMethod.POST,
        "rankings",
        auth_context,
        json={"scoring_type": "MATCH_POINTS", "name": "Secondary ranking"},
    )
    assert response.get("success") is True, response

    tournament_id = auth_context.tournament.id
    rankings_list = await get_all_rankings_in_tournament(tournament_id)
    named_ranking = next((r for r in rankings_list if r.name == "Secondary ranking"), None)
    assert named_ranking is not None
    await sql_delete_ranking(tournament_id, named_ranking.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_side_switch(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {
        "scoring_type": "MATCH_POINTS",
        "win_points": "1.0",
        "draw_points": "0.5",
        "loss_points": "0.0",
        "position": 0,
        "side_switch_every_n_points": 7,
    }
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as ranking_inserted:
            response = await send_tournament_request(
                HTTPMethod.PUT, f"rankings/{ranking_inserted.id}", auth_context, json=body
            )
            assert response["success"] is True
            updated_rankings = await get_all_rankings_in_tournament(auth_context.tournament.id)
            updated = next(r for r in updated_rankings if r.id == ranking_inserted.id)
            assert updated.side_switch_every_n_points == 7


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_even_sets_single_elimination_returns_422(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """PUT with even num_sets returns 422 when the ranking is used by a SINGLE_ELIMINATION stage item."""
    body = {"scoring_type": "MATCH_POINTS", "num_sets": 2}
    tournament_id = auth_context.tournament.id
    async with inserted_ranking(
        DUMMY_RANKING1.model_copy(update={"tournament_id": tournament_id})
    ) as test_ranking:
        async with inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage:
            async with inserted_stage_item(
                DUMMY_STAGE_ITEM3.model_copy(
                    update={"stage_id": stage.id, "ranking_id": test_ranking.id}
                )
            ):
                response = await send_tournament_request(
                    HTTPMethod.PUT,
                    f"rankings/{test_ranking.id}",
                    auth_context,
                    json=body,
                )
                assert "detail" in response
                assert "Even number of sets" in response["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_odd_sets_single_elimination_succeeds(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """PUT with odd num_sets succeeds even when the ranking is used by a SINGLE_ELIMINATION stage item."""
    body = {"scoring_type": "MATCH_POINTS", "num_sets": 3}
    tournament_id = auth_context.tournament.id
    async with inserted_ranking(
        DUMMY_RANKING1.model_copy(update={"tournament_id": tournament_id})
    ) as test_ranking:
        async with inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage:
            async with inserted_stage_item(
                DUMMY_STAGE_ITEM3.model_copy(
                    update={"stage_id": stage.id, "ranking_id": test_ranking.id}
                )
            ):
                response = await send_tournament_request(
                    HTTPMethod.PUT,
                    f"rankings/{test_ranking.id}",
                    auth_context,
                    json=body,
                )
                assert response.get("success") is True, response


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_even_sets_round_robin_succeeds(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """PUT with even num_sets is allowed when all associated stage items are ROUND_ROBIN."""
    body = {"scoring_type": "MATCH_POINTS", "num_sets": 2}
    tournament_id = auth_context.tournament.id
    async with inserted_ranking(
        DUMMY_RANKING1.model_copy(update={"tournament_id": tournament_id})
    ) as test_ranking:
        async with inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage:
            async with inserted_stage_item(
                DUMMY_STAGE_ITEM1.model_copy(
                    update={"stage_id": stage.id, "ranking_id": test_ranking.id}
                )
            ):
                response = await send_tournament_request(
                    HTTPMethod.PUT,
                    f"rankings/{test_ranking.id}",
                    auth_context,
                    json=body,
                )
                assert response.get("success") is True, response
