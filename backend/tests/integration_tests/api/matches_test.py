import pytest
from heliclockter import timedelta

from bracket.database import database
from bracket.models.db.match import Match, MatchState
from bracket.models.db.round import RoundLifecycleState
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
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from bracket.utils.types import JsonDict, assert_some
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_court,
    inserted_match,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_match_is_blocked(
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
                update={
                    "stage_item_id": stage_item_inserted.id,
                    "lifecycle_state": RoundLifecycleState.ACTIVE,
                }
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
        assert response["detail"] == "Matches cannot be created individually", response

        # No match should have been created.
        await assert_row_count_and_clear(matches, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_match_is_blocked(
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
                update={
                    "stage_item_id": stage_item_inserted.id,
                    "lifecycle_state": RoundLifecycleState.ACTIVE,
                }
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
                    "state": MatchState.NOT_STARTED,
                    "completed_at": None,
                }
            )
        ) as match_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.DELETE, f"matches/{match_inserted.id}", auth_context, {}
        )
        assert response["detail"] == "Matches cannot be deleted individually", response

        # The match must still exist; deletion is blocked.
        await assert_row_count_and_clear(matches, 1)


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
async def test_update_match_back_to_not_started_resets_score(
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
                    "stage_item_input1_score": 1,
                    "stage_item_input2_score": 0,
                    "state": MatchState.IN_PROGRESS,
                    "completed_at": None,
                }
            )
        ) as match_inserted,
    ):
        # Moving an in-progress match back to "not started" is allowed as long as the score
        # is reset to 0–0 at the same time (the match modal does exactly this).
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                {
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "round_id": round_inserted.id,
                    "court_id": court1_inserted.id,
                    "state": "NOT_STARTED",
                },
            )
            == SUCCESS_RESPONSE
        )
        updated_match = await fetch_one_parsed_certain(
            database,
            Match,
            query=matches.select().where(matches.c.id == match_inserted.id),
        )
        assert updated_match.state is MatchState.NOT_STARTED
        assert updated_match.stage_item_input1_score == 0
        assert updated_match.stage_item_input2_score == 0

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_match_cannot_set_nonzero_score_while_not_started(
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
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
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
                "stage_item_input1_score": 1,
                "stage_item_input2_score": 0,
                "round_id": round_inserted.id,
                "court_id": court1_inserted.id,
                "state": "NOT_STARTED",
            },
        )
        updated_match = await fetch_one_parsed_certain(
            database,
            Match,
            query=matches.select().where(matches.c.id == match_inserted.id),
        )

        await assert_row_count_and_clear(matches, 1)

    assert response["detail"] == (
        "Scores can only be set while the match is in progress or being completed; "
        "moving a match to another state requires resetting its score to 0–0"
    )
    assert updated_match.state is MatchState.NOT_STARTED
    assert updated_match.stage_item_input1_score == 0
    assert updated_match.stage_item_input2_score == 0


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
async def test_update_endpoint_custom_duration(
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
                }
            )
        ) as match_inserted,
    ):
        body = {
            "round_id": round_inserted.id,
            "custom_duration_minutes": 30,
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

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_endpoint_custom_duration_unscheduled_match(
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
                }
            )
        ) as match_inserted,
    ):
        body = {
            "round_id": round_inserted.id,
            "custom_duration_minutes": 30,
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
        assert updated_match.court_id is None
        assert updated_match.start_time is None

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_endpoint_custom_duration_shifts_only_its_court(
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

    all_matches = [
        match
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.start_time is not None
    ]
    court1_matches = sorted(
        (m for m in all_matches if m.court_id == court1_inserted.id),
        key=lambda m: assert_some(m.start_time),
    )
    court2_matches = sorted(
        (m for m in all_matches if m.court_id == court2_inserted.id),
        key=lambda m: assert_some(m.start_time),
    )

    # Court 1 keeps its 3 matches in start-time order; the updated match now
    # occupies 20 minutes, with the tournament default break after it.
    assert len(court1_matches) == 3
    assert court1_matches[0].id == updated_match.id
    assert court1_matches[0].start_time == tournament.start_time
    assert court1_matches[1].start_time == tournament.start_time + timedelta(minutes=25)
    assert court1_matches[2].start_time == tournament.start_time + timedelta(minutes=40)

    # Court 2 is not touched at all: the re-pack is scoped to the updated match's
    # court, so its matches keep the start times they were inserted with.
    assert len(court2_matches) == 2
    assert court2_matches[0].start_time == tournament.start_time
    assert court2_matches[1].start_time == stage2_start


@pytest.mark.asyncio(loop_scope="session")
async def test_update_endpoint_custom_duration_updates_conflicts(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament = auth_context.tournament
    court2_match_start = tournament.start_time + timedelta(minutes=15)

    async def conflict_flags_by_match_id() -> dict[int, tuple[bool, bool]]:
        return {
            match.id: (match.stage_item_input1_conflict, match.stage_item_input2_conflict)
            for stage in await get_full_tournament_details(tournament.id)
            for stage_item in stage.stage_items
            for round_ in stage_item.rounds
            for match in round_.matches
        }

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament.id})) as team1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament.id})) as team2,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1.id,
                tournament_id=tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as input1,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2.id,
                tournament_id=tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as input2,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": tournament.id})
        ) as court1_inserted,
        inserted_court(
            DUMMY_COURT2.model_copy(update={"tournament_id": tournament.id})
        ) as court2_inserted,
        # The same two teams play on different courts with a default break gap:
        # court 1 at T+0..T+10, court 2 at T+15..T+25, so no conflict initially.
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court1_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": tournament.start_time,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as court1_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court2_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": court2_match_start,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as court2_match,
    ):
        # Growing the first match to 20 minutes makes it span T+0..T+20,
        # overlapping the other court's match: the persisted conflict flags must
        # be set as part of the update, not left for the next scheduling action.
        body: JsonDict = {
            "round_id": round_inserted.id,
            "custom_duration_minutes": 20,
        }
        assert (
            await send_tournament_request(
                HTTPMethod.PUT, f"matches/{court1_match.id}", auth_context, None, body
            )
            == SUCCESS_RESPONSE
        )
        flags = await conflict_flags_by_match_id()
        assert flags[court1_match.id] == (True, True)
        assert flags[court2_match.id] == (True, True)

        # Reverting to the default duration removes the overlap, which
        # must clear the flags again.
        body = {
            "round_id": round_inserted.id,
            "custom_duration_minutes": None,
        }
        assert (
            await send_tournament_request(
                HTTPMethod.PUT, f"matches/{court1_match.id}", auth_context, None, body
            )
            == SUCCESS_RESPONSE
        )
        flags = await conflict_flags_by_match_id()
        assert flags[court1_match.id] == (False, False)
        assert flags[court2_match.id] == (False, False)

        await assert_row_count_and_clear(matches, 0)
