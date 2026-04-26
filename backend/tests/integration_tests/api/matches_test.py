from decimal import Decimal

import pytest
from heliclockter import timedelta

from bracket.database import database
from bracket.models.db.match import Match, MatchState
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputInsertable,
)
from bracket.schema import matches
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_COURT2,
    DUMMY_MATCH1,
    DUMMY_PLAYER1,
    DUMMY_PLAYER2,
    DUMMY_PLAYER3,
    DUMMY_PLAYER4,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_court,
    inserted_match,
    inserted_player_in_team,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_match(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "ranking_id": auth_context.ranking.id,
                    "type": StageType.SWISS,
                }
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(
                update={"stage_item_id": stage_item_inserted.id, "is_draft": True}
            )
        ) as round_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team1_inserted,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court1_inserted,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team2_inserted,
    ):
        body = {
            "team1_id": team1_inserted.id,
            "team2_id": team2_inserted.id,
            "round_id": round_inserted.id,
            "court_id": court1_inserted.id,
        }
        response = await send_tournament_request(
            HTTPMethod.POST, "matches", auth_context, json=body
        )
        assert response["data"]["id"], response

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_match(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "ranking_id": auth_context.ranking.id,
                    "type": StageType.SWISS,
                }
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(
                update={"stage_item_id": stage_item_inserted.id, "is_draft": True}
            )
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
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court1_inserted.id,
                }
            )
        ) as match_inserted,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.DELETE, f"matches/{match_inserted.id}", auth_context, {}
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(matches, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_match(
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
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court1_inserted.id,
                }
            )
        ) as match_inserted,
    ):
        body = {
            "stage_item_input1_score": 42,
            "stage_item_input2_score": 24,
            "round_id": round_inserted.id,
            "court_id": None,
            "state": "IN_PROGRESS",
        }
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                body,
            )
            == SUCCESS_RESPONSE
        )
        updated_match = await fetch_one_parsed_certain(
            database,
            Match,
            query=matches.select().where(matches.c.id == match_inserted.id),
        )
        assert updated_match.stage_item_input1_score == body["stage_item_input1_score"]
        assert updated_match.stage_item_input2_score == body["stage_item_input2_score"]
        assert updated_match.court_id == body["court_id"]

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_match_fails_when_stage_has_not_started(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
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
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court1_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "completed_at": None,
                }
            )
        ) as match_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"matches/{match_inserted.id}",
            auth_context,
            None,
            {
                "stage_item_input1_score": 0,
                "stage_item_input2_score": 0,
                "round_id": round_inserted.id,
                "court_id": court1_inserted.id,
                "state": "IN_PROGRESS",
            },
        )
        updated_match = await fetch_one_parsed_certain(
            database,
            Match,
            query=matches.select().where(matches.c.id == match_inserted.id),
        )

        await assert_row_count_and_clear(matches, 1)

    assert response["detail"] == (
        'Cannot start this match because stage "Knockout Stage" has not started yet. '
        "Start that stage first."
    )
    assert updated_match.state.name == "NOT_STARTED"


@pytest.mark.asyncio(loop_scope="session")
async def test_update_endpoint_custom_duration_margin(
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
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": court1_inserted.id,
                    "custom_duration_minutes": 20,
                    "custom_margin_minutes": 10,
                }
            )
        ) as match_inserted,
    ):
        body = {
            "round_id": round_inserted.id,
            "custom_duration_minutes": 30,
            "custom_margin_minutes": 20,
        }
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                body,
            )
            == SUCCESS_RESPONSE
        )
        updated_match = await fetch_one_parsed_certain(
            database,
            Match,
            query=matches.select().where(matches.c.id == match_inserted.id),
        )
        assert updated_match.custom_duration_minutes == body["custom_duration_minutes"]
        assert updated_match.custom_margin_minutes == body["custom_margin_minutes"]

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_endpoint_custom_duration_margin_unscheduled_match(
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
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": stage_item_input1_inserted.id,
                    "stage_item_input2_id": stage_item_input2_inserted.id,
                    "court_id": None,
                    "start_time": None,
                    "position_in_schedule": None,
                }
            )
        ) as match_inserted,
    ):
        body = {
            "round_id": round_inserted.id,
            "custom_duration_minutes": 30,
            "custom_margin_minutes": 20,
        }
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                body,
            )
            == SUCCESS_RESPONSE
        )
        updated_match = await fetch_one_parsed_certain(
            database,
            Match,
            query=matches.select().where(matches.c.id == match_inserted.id),
        )
        assert updated_match.custom_duration_minutes == body["custom_duration_minutes"]
        assert updated_match.custom_margin_minutes == body["custom_margin_minutes"]
        assert updated_match.court_id is None
        assert updated_match.start_time is None
        assert updated_match.position_in_schedule is None

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_endpoint_custom_duration_margin_preserves_stage_boundaries_across_courts(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament = auth_context.tournament
    stage1_second_start = tournament.start_time + timedelta(minutes=15)
    stage2_start = tournament.start_time + timedelta(minutes=30)

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament.id})
        ) as stage1_inserted,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": tournament.id})
        ) as stage2_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage1_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage1_item_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage2_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage2_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage1_item_inserted.id})
        ) as stage1_round_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage2_item_inserted.id})
        ) as stage2_round_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament.id})) as team1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament.id})) as team2,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1.id,
                tournament_id=tournament.id,
                stage_item_id=stage1_item_inserted.id,
            )
        ) as stage1_input1,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2.id,
                tournament_id=tournament.id,
                stage_item_id=stage1_item_inserted.id,
            )
        ) as stage1_input2,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1.id,
                tournament_id=tournament.id,
                stage_item_id=stage2_item_inserted.id,
            )
        ) as stage2_input1,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2.id,
                tournament_id=tournament.id,
                stage_item_id=stage2_item_inserted.id,
            )
        ) as stage2_input2,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": tournament.id})
        ) as court1_inserted,
        inserted_court(
            DUMMY_COURT2.model_copy(update={"tournament_id": tournament.id})
        ) as court2_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": stage1_round_inserted.id,
                    "stage_item_input1_id": stage1_input1.id,
                    "stage_item_input2_id": stage1_input2.id,
                    "court_id": court1_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": tournament.start_time,
                    "position_in_schedule": 0,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as updated_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": stage1_round_inserted.id,
                    "stage_item_input1_id": stage1_input1.id,
                    "stage_item_input2_id": stage1_input2.id,
                    "court_id": court1_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": stage1_second_start,
                    "position_in_schedule": 1,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ),
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": stage1_round_inserted.id,
                    "stage_item_input1_id": stage1_input1.id,
                    "stage_item_input2_id": stage1_input2.id,
                    "court_id": court2_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": tournament.start_time,
                    "position_in_schedule": 0,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ),
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": stage2_round_inserted.id,
                    "stage_item_input1_id": stage2_input1.id,
                    "stage_item_input2_id": stage2_input2.id,
                    "court_id": court1_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": stage2_start,
                    "position_in_schedule": 2,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ),
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": stage2_round_inserted.id,
                    "stage_item_input1_id": stage2_input1.id,
                    "stage_item_input2_id": stage2_input2.id,
                    "court_id": court2_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": stage2_start,
                    "position_in_schedule": 1,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ),
    ):
        body = {
            "round_id": stage1_round_inserted.id,
            "custom_duration_minutes": 20,
            "custom_margin_minutes": 10,
        }
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{updated_match.id}",
                auth_context,
                None,
                body,
            )
            == SUCCESS_RESPONSE
        )
        stages = await get_full_tournament_details(tournament.id)
        await assert_row_count_and_clear(matches, 0)

    stage1 = next(stage for stage in stages if stage.id == stage1_inserted.id)
    stage2 = next(stage for stage in stages if stage.id == stage2_inserted.id)
    latest_stage1_end = max(
        match.end_time
        for stage_item in stage1.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.start_time is not None
    )
    stage2_start_times = [
        match.start_time
        for stage_item in stage2.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.start_time is not None
    ]

    assert stage2_start_times
    for start_time in stage2_start_times:
        assert start_time >= latest_stage1_end


@pytest.mark.asyncio(loop_scope="session")
async def test_upcoming_matches_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(
                update={
                    "is_active": True,
                    "tournament_id": auth_context.tournament.id,
                }
            )
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "type": StageType.SWISS,
                    "ranking_id": auth_context.ranking.id,
                }
            )
        ) as stage_item_inserted,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
        inserted_round(
            DUMMY_ROUND1.model_copy(
                update={
                    "is_draft": True,
                    "stage_item_id": stage_item_inserted.id,
                }
            )
        ),
        inserted_team(
            DUMMY_TEAM1.model_copy(
                update={"tournament_id": auth_context.tournament.id, "elo_score": Decimal("1150.0")}
            )
        ) as team1_inserted,
        inserted_team(
            DUMMY_TEAM2.model_copy(
                update={"tournament_id": auth_context.tournament.id, "elo_score": Decimal("1350.0")}
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
        inserted_player_in_team(
            DUMMY_PLAYER1.model_copy(
                update={"elo_score": Decimal("1100.0"), "tournament_id": auth_context.tournament.id}
            ),
            team1_inserted.id,
        ),
        inserted_player_in_team(
            DUMMY_PLAYER2.model_copy(
                update={"elo_score": Decimal("1300.0"), "tournament_id": auth_context.tournament.id}
            ),
            team2_inserted.id,
        ),
        inserted_player_in_team(
            DUMMY_PLAYER3.model_copy(
                update={"elo_score": Decimal("1200.0"), "tournament_id": auth_context.tournament.id}
            ),
            team1_inserted.id,
        ),
        inserted_player_in_team(
            DUMMY_PLAYER4.model_copy(
                update={"elo_score": Decimal("1400.0"), "tournament_id": auth_context.tournament.id}
            ),
            team2_inserted.id,
        ),
    ):
        json_response = await send_tournament_request(
            HTTPMethod.GET,
            f"stage_items/{stage_item_inserted.id}/upcoming_matches",
            auth_context,
            {},
        )
        # print(json_response["data"][0]["stage_item_input1"]["team"])
        # 1 / 0
        assert json_response == {
            "data": [
                {
                    "stage_item_input1": {
                        "team_id": team1_inserted.id,
                        "winner_from_stage_item_id": None,
                        "winner_position": None,
                        "points": "0",
                        "wins": 0,
                        "draws": 0,
                        "losses": 0,
                        "id": stage_item_input1_inserted.id,
                        "slot": 0,
                        "tournament_id": auth_context.tournament.id,
                        "stage_item_id": stage_item_inserted.id,
                        "team": {
                            "created": "2022-01-11T04:32:11Z",
                            "name": team1_inserted.name,
                            "tournament_id": auth_context.tournament.id,
                            "active": True,
                            "elo_score": "1150",
                            "swiss_score": "0",
                            "wins": 0,
                            "draws": 0,
                            "losses": 0,
                            "logo_path": None,
                            "id": team1_inserted.id,
                        },
                    },
                    "stage_item_input2": {
                        "team_id": team2_inserted.id,
                        "winner_from_stage_item_id": None,
                        "winner_position": None,
                        "points": "0",
                        "wins": 0,
                        "draws": 0,
                        "losses": 0,
                        "id": stage_item_input2_inserted.id,
                        "slot": 1,
                        "tournament_id": auth_context.tournament.id,
                        "stage_item_id": stage_item_inserted.id,
                        "team": {
                            "created": "2022-01-11T04:32:11Z",
                            "name": team2_inserted.name,
                            "tournament_id": auth_context.tournament.id,
                            "active": True,
                            "elo_score": "1350",
                            "swiss_score": "0",
                            "wins": 0,
                            "draws": 0,
                            "losses": 0,
                            "logo_path": None,
                            "id": team2_inserted.id,
                        },
                    },
                    "elo_diff": "0",
                    "swiss_diff": "0",
                    "times_played_sum": 0,
                    "is_recommended": True,
                    "player_behind_schedule_count": 0,
                }
            ]
        }
