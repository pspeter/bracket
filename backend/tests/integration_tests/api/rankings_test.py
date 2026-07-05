from decimal import Decimal
from unittest.mock import ANY

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.ranking import ScoringType
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
    StageItemInputFinal,
)
from bracket.sql.rankings import (
    get_all_rankings_in_tournament,
    sql_delete_ranking,
)
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_RANKING1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
)
from bracket.utils.http import HTTPMethod
from bracket.utils.id_types import RankingId, StageId, TeamId, TournamentId
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    complete_match,
    send_tournament_request,
)
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
    """PUT with even num_sets returns 422 for a SINGLE_ELIMINATION stage item."""
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
    """PUT with odd num_sets succeeds for a SINGLE_ELIMINATION stage item."""
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


async def _play_group_with_t1_win_and_draws(
    auth_context: AuthContext,
    tournament_id: TournamentId,
    t1_id: TeamId,
    t3_id: TeamId,
) -> None:
    """Play out a 3-team round robin (the tournament's first stage): team 1 beats team 3, and
    the other two matches end in draws. Under the default 1.0/0.5/0.0 match points this ranks
    team 1 first (1.5 points), team 2 second (1.0) and team 3 last (0.5).
    """
    [group_stage, _] = await get_full_tournament_details(tournament_id)
    real_matches = [
        match
        for round_ in group_stage.stage_items[0].rounds
        for match in round_.matches
        if match.stage_item_input1 is not None and match.stage_item_input2 is not None
    ]
    assert len(real_matches) == 3

    for match in real_matches:
        input1 = match.stage_item_input1
        input2 = match.stage_item_input2
        assert isinstance(input1, StageItemInputFinal)
        assert isinstance(input2, StageItemInputFinal)
        teams = {input1.team.id, input2.team.id}

        if teams == {t1_id, t3_id}:
            # Team 1 beats team 3 outright.
            score1, score2 = (21, 0) if input1.team.id == t1_id else (0, 21)
        else:
            # Team 1 vs team 2, and team 2 vs team 3, both end in a draw.
            score1, score2 = 10, 10

        for match_set in match.match_sets:
            await complete_match(auth_context, match.id, match_set.id, score1=score1, score2=score2)


async def _dependent_team_ids_by_slot(
    tournament_id: TournamentId, dependent_stage_id: StageId
) -> dict[int, TeamId | None]:
    """Return slot -> resolved team id for the single stage item in the dependent stage."""
    stages = await get_full_tournament_details(tournament_id)
    dependent_stage = next(s for s in stages if s.id == dependent_stage_id)
    return {input_.slot: input_.team_id for input_ in dependent_stage.stage_items[0].inputs}


async def _flip_standings_via_ranking_edit(
    auth_context: AuthContext, ranking_id: RankingId
) -> None:
    """Edit the ranking so draws are worth more than the gap between a win and a draw.

    After ``_play_group_with_t1_win_and_draws``: team 1 -> 1.0 (win) + 2.0 (draw) = 3.0, team 2
    -> 2.0 + 2.0 = 4.0, team 3 -> 0.0 + 2.0 = 2.0. Team 2 overtakes team 1 purely from the
    ranking edit -- no match result changed.
    """
    body = {
        "scoring_type": "MATCH_POINTS",
        "win_points": "1.0",
        "draw_points": "2.0",
        "loss_points": "0.0",
    }
    response = await send_tournament_request(
        HTTPMethod.PUT, f"rankings/{ranking_id}", auth_context, json=body
    )
    assert response.get("success") is True, response


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_reflows_dependent_stage_item_inputs(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A ranking edit that flips a completed stage item's final order must re-resolve any
    "winner of <stage item>" input elsewhere in the tournament, exactly like completing a match
    does. Before the fix, the ranking PUT route only recalculated the ranking and (for single
    elimination) the elimination tree, so a dependent stage item's input kept pointing at the
    stale winner.
    """
    tournament_id = auth_context.tournament.id

    async with (
        inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": tournament_id, "position": 5})
        ) as test_ranking,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted_1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted_2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        stage_item_1 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name="Group",
                team_count=3,
                type=StageType.ROUND_ROBIN,
                ranking_id=test_ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                ],
            ),
        )
        # Slot 2 references a fixed, unrelated team (t4) rather than "winner position 2 of
        # stage item 1", so this test isolates single-input propagation. The full two-sibling
        # swap case is covered by test_update_ranking_swaps_teams_between_dependent_inputs.
        stage_item_2 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_2.id,
                name=DUMMY_STAGE_ITEM3.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM3.type,
                inputs=[
                    StageItemInputCreateBodyTentative(
                        slot=1, winner_from_stage_item_id=stage_item_1.id, winner_position=1
                    ),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t4.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item_1, tournament_id)
        await build_matches_for_stage_item(stage_item_2, tournament_id)

        try:
            await _play_group_with_t1_win_and_draws(auth_context, tournament_id, t1.id, t3.id)

            # Team 1 is the winner, so the dependent stage item's first input must already be
            # resolved to team 1.
            teams_by_slot = await _dependent_team_ids_by_slot(tournament_id, stage_inserted_2.id)
            assert teams_by_slot == {1: t1.id, 2: t4.id}

            await _flip_standings_via_ranking_edit(auth_context, test_ranking.id)

            # The dependent stage item's first input must now be re-resolved to team 2: this is
            # the propagation that didn't happen before the ranking route was switched to the
            # shared reconciliation cascade.
            teams_by_slot = await _dependent_team_ids_by_slot(tournament_id, stage_inserted_2.id)
            assert teams_by_slot == {1: t2.id, 2: t4.id}
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
            await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking_swaps_teams_between_dependent_inputs(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A ranking edit that swaps positions 1 and 2 of the source stage item must swap the teams
    of the two dependent sibling inputs tracking those positions, without violating the unique
    (stage_item_id, team_id) constraint. resolve_dependent_inputs_for_completed_stage_item used
    to update each input's team_id one row at a time, which crashed with a UniqueViolationError
    on exactly this full-swap case; it now clears every changing row before writing the final
    assignments.
    """
    tournament_id = auth_context.tournament.id

    async with (
        inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": tournament_id, "position": 5})
        ) as test_ranking,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted_1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted_2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
    ):
        stage_item_1 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name="Group",
                team_count=3,
                type=StageType.ROUND_ROBIN,
                ranking_id=test_ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                ],
            ),
        )
        # Both dependent inputs track positions in the same source stage item, so a standings
        # flip between positions 1 and 2 forces a full swap of teams between sibling rows.
        stage_item_2 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_2.id,
                name=DUMMY_STAGE_ITEM3.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM3.type,
                inputs=[
                    StageItemInputCreateBodyTentative(
                        slot=1, winner_from_stage_item_id=stage_item_1.id, winner_position=1
                    ),
                    StageItemInputCreateBodyTentative(
                        slot=2, winner_from_stage_item_id=stage_item_1.id, winner_position=2
                    ),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item_1, tournament_id)
        await build_matches_for_stage_item(stage_item_2, tournament_id)

        try:
            await _play_group_with_t1_win_and_draws(auth_context, tournament_id, t1.id, t3.id)

            teams_by_slot = await _dependent_team_ids_by_slot(tournament_id, stage_inserted_2.id)
            assert teams_by_slot == {1: t1.id, 2: t2.id}

            # The ranking edit swaps positions 1 and 2, so both dependent inputs must trade
            # teams -- previously a UniqueViolationError.
            await _flip_standings_via_ranking_edit(auth_context, test_ranking.id)

            teams_by_slot = await _dependent_team_ids_by_slot(tournament_id, stage_inserted_2.id)
            assert teams_by_slot == {1: t2.id, 2: t1.id}
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
            await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)
