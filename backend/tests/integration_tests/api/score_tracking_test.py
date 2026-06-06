import pytest

from bracket.database import database
from bracket.models.db.match import Match
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.schema import matches, tournaments
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_COURT2,
    DUMMY_LEVEL1,
    DUMMY_MATCH1,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_request, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_court,
    inserted_level,
    inserted_match,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_authenticated_score_tracking_list_works_when_public_link_disabled(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team1_inserted,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team2_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input1_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input2_inserted,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court_inserted.id,
                }
            )
        ) as match_inserted,
    ):
        response = await send_tournament_request(HTTPMethod.GET, "score-tracking", auth_context, {})

        assert response["data"]["tournament_id"] == auth_context.tournament.id
        assert response["data"]["tournament_name"] == auth_context.tournament.name
        assert len(response["data"]["matches"]) == 1
        assert response["data"]["matches"][0]["id"] == match_inserted.id


@pytest.mark.asyncio(loop_scope="session")
async def test_authenticated_score_tracking_includes_levels_and_match_level(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_level(
            DUMMY_LEVEL1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as level,
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "level_id": level.id}
            )
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "level_id": level.id}
            )
        ) as team1_inserted,
        inserted_team(
            DUMMY_TEAM2.model_copy(
                update={"tournament_id": auth_context.tournament.id, "level_id": level.id}
            )
        ) as team2_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input1_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input2_inserted,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court_inserted.id,
                }
            )
        ) as match_inserted,
    ):
        response = await send_tournament_request(HTTPMethod.GET, "score-tracking", auth_context, {})

        assert response["data"]["levels"] == [{"id": level.id, "name": "Beginners", "position": 0}]
        assert response["data"]["matches"][0]["id"] == match_inserted.id
        assert response["data"]["matches"][0]["level_id"] == level.id


@pytest.mark.asyncio(loop_scope="session")
async def test_score_tracking_lists_only_matches_from_active_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as active_stage_inserted,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as inactive_stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": active_stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as active_stage_item_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": inactive_stage_inserted.id,
                    "ranking_id": auth_context.ranking.id,
                    "name": "Group B",
                }
            )
        ) as inactive_stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": active_stage_item_inserted.id})
        ) as active_round_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(
                update={"stage_item_id": inactive_stage_item_inserted.id, "name": "Round 2"}
            )
        ) as inactive_round_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team1_inserted,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team2_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=active_stage_item_inserted.id,
            )
        ) as active_stage_item_input1_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=active_stage_item_inserted.id,
            )
        ) as active_stage_item_input2_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=inactive_stage_item_inserted.id,
            )
        ) as inactive_stage_item_input1_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=inactive_stage_item_inserted.id,
            )
        ) as inactive_stage_item_input2_inserted,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as active_court_inserted,
        inserted_court(
            DUMMY_COURT2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as inactive_court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": active_round_inserted.id,
                    "stage_item_input1_id": active_stage_item_input1_inserted.id,
                    "stage_item_input2_id": active_stage_item_input2_inserted.id,
                    "court_id": active_court_inserted.id,
                }
            )
        ) as active_match_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": inactive_round_inserted.id,
                    "stage_item_input1_id": inactive_stage_item_input1_inserted.id,
                    "stage_item_input2_id": inactive_stage_item_input2_inserted.id,
                    "court_id": inactive_court_inserted.id,
                }
            )
        ) as inactive_match_inserted,
    ):
        await database.execute(
            query=tournaments.update()
            .where(tournaments.c.id == auth_context.tournament.id)
            .values(score_tracking_enabled=True, score_tracking_token="score-token"),
        )
        try:
            authenticated_response = await send_tournament_request(
                HTTPMethod.GET, "score-tracking", auth_context, {}
            )
            public_response = await send_request(HTTPMethod.GET, "score-tracking/score-token")

            assert authenticated_response["data"]["matches"] == public_response["data"]["matches"]
            assert [match["id"] for match in authenticated_response["data"]["matches"]] == [
                active_match_inserted.id
            ]
            assert inactive_match_inserted.id not in [
                match["id"] for match in authenticated_response["data"]["matches"]
            ]
        finally:
            await database.execute(
                query=tournaments.update()
                .where(tournaments.c.id == auth_context.tournament.id)
                .values(score_tracking_enabled=False, score_tracking_token=None),
            )


@pytest.mark.asyncio(loop_scope="session")
async def test_authenticated_score_tracking_update_works_when_public_link_disabled(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team1_inserted,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team2_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input1_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input2_inserted,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court_inserted.id,
                }
            )
        ) as match_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"score-tracking/matches/{match_inserted.id}",
            auth_context,
            json={
                "stage_item_input1_score": 7,
                "stage_item_input2_score": 5,
                "state": "IN_PROGRESS",
            },
        )

        assert response["data"]["id"] == match_inserted.id
        assert response["data"]["stage_item_input1_score"] == 7
        assert response["data"]["stage_item_input2_score"] == 5
        assert response["data"]["state"] == "IN_PROGRESS"

        updated_match = await fetch_one_parsed_certain(
            database,
            Match,
            query=matches.select().where(matches.c.id == match_inserted.id),
        )
        assert updated_match.stage_item_input1_score == 7
        assert updated_match.stage_item_input2_score == 5
        assert updated_match.state.name == "IN_PROGRESS"


@pytest.mark.asyncio(loop_scope="session")
async def test_score_tracking_filters_matches_by_court_id(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team1_inserted,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team2_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input1_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input2_inserted,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court1_inserted,
        inserted_court(
            DUMMY_COURT2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court2_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court1_inserted.id,
                }
            )
        ) as match_on_court1,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court2_inserted.id,
                }
            )
        ) as match_on_court2,
    ):
        await database.execute(
            query=tournaments.update()
            .where(tournaments.c.id == auth_context.tournament.id)
            .values(score_tracking_enabled=True, score_tracking_token="court-filter-token"),
        )
        try:
            authed_filtered = await send_tournament_request(
                HTTPMethod.GET,
                f"score-tracking?court_id={court1_inserted.id}",
                auth_context,
                {},
            )
            public_filtered = await send_request(
                HTTPMethod.GET,
                f"score-tracking/court-filter-token?court_id={court1_inserted.id}",
            )
            authed_unfiltered = await send_tournament_request(
                HTTPMethod.GET, "score-tracking", auth_context, {}
            )

            authed_filtered_ids = {m["id"] for m in authed_filtered["data"]["matches"]}
            public_filtered_ids = {m["id"] for m in public_filtered["data"]["matches"]}
            authed_unfiltered_ids = {m["id"] for m in authed_unfiltered["data"]["matches"]}

            assert authed_filtered_ids == {match_on_court1.id}
            assert public_filtered_ids == {match_on_court1.id}
            assert authed_unfiltered_ids == {match_on_court1.id, match_on_court2.id}
        finally:
            await database.execute(
                query=tournaments.update()
                .where(tournaments.c.id == auth_context.tournament.id)
                .values(score_tracking_enabled=False, score_tracking_token=None),
            )
