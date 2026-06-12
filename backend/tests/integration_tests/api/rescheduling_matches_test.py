import pytest
from heliclockter import timedelta

from bracket.models.db.match import MatchRescheduleBody, MatchState, MatchSwapBody
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.schema import matches
from bracket.sql.matches import sql_get_match
from bracket.sql.stages import get_full_tournament_details
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
from bracket.utils.types import assert_some
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
async def test_reschedule_match(
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
                slot=0,
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
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as match_inserted,
    ):
        body = MatchRescheduleBody(
            old_court_id=court1_inserted.id,
            old_position=0,
            new_court_id=court2_inserted.id,
            new_position=2,
        )
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{match_inserted.id}/reschedule",
                auth_context,
                json=body.model_dump(),
            )
            == SUCCESS_RESPONSE
        )
        match = await sql_get_match(match_inserted.id)
        await assert_row_count_and_clear(matches, 0)

    assert match.court_id == body.new_court_id
    assert match.start_time == auth_context.tournament.start_time


@pytest.mark.asyncio(loop_scope="session")
async def test_reschedule_match_stale_position_returns_conflict(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    A reschedule whose old court/position no longer matches (someone else moved the
    match in between) is rejected with 409 and leaves the schedule untouched.
    """
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
                slot=0,
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
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as match_inserted,
    ):
        # The only match on the court is at derived position 0; claim it was at position 1.
        body = MatchRescheduleBody(
            old_court_id=court1_inserted.id,
            old_position=1,
            new_court_id=court2_inserted.id,
            new_position=0,
        )
        response = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/reschedule",
            auth_context,
            json=body.model_dump(),
        )
        match = await sql_get_match(match_inserted.id)
        await assert_row_count_and_clear(matches, 0)

    assert response["detail"] == (
        "The schedule changed since this device last refreshed: "
        "the match is no longer at the given court and position"
    )
    assert match.court_id == court1_inserted.id
    assert match.start_time == DUMMY_MATCH1.start_time


@pytest.mark.asyncio(loop_scope="session")
async def test_unschedule_match(
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
                slot=0,
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
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as match_inserted,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{match_inserted.id}/unschedule",
                auth_context,
            )
            == SUCCESS_RESPONSE
        )
        match = await sql_get_match(match_inserted.id)
        await assert_row_count_and_clear(matches, 0)

    assert match.court_id is None
    assert match.start_time is None


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("state", "expected_detail"),
    [
        (
            MatchState.IN_PROGRESS,
            "Cannot move a in progress match back to Unscheduled. "
            "Only not started matches can be unscheduled.",
        ),
        (
            MatchState.COMPLETED,
            "Cannot move a completed match back to Unscheduled. "
            "Only not started matches can be unscheduled.",
        ),
    ],
)
async def test_unschedule_started_match_fails(
    startup_and_shutdown_uvicorn_server: None,
    auth_context: AuthContext,
    state: MatchState,
    expected_detail: str,
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
                slot=0,
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
                    "state": state,
                    "completed_at": DUMMY_MATCH1.completed_at
                    if state is MatchState.COMPLETED
                    else None,
                }
            )
        ) as match_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/unschedule",
            auth_context,
        )
        match = await sql_get_match(match_inserted.id)
        await assert_row_count_and_clear(matches, 0)

    assert response["detail"] == expected_detail
    assert match.court_id == court1_inserted.id
    assert match.start_time == DUMMY_MATCH1.start_time


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_match_from_unscheduled(
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
                slot=0,
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
                    "court_id": None,
                    "start_time": None,
                }
            )
        ) as match_inserted,
    ):
        body = MatchRescheduleBody(
            old_court_id=None,
            old_position=None,
            new_court_id=court1_inserted.id,
            new_position=0,
        )
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{match_inserted.id}/reschedule",
                auth_context,
                json=body.model_dump(mode="json", exclude_none=False),
            )
            == SUCCESS_RESPONSE
        )
        match = await sql_get_match(match_inserted.id)
        await assert_row_count_and_clear(matches, 0)

    assert match.court_id == court1_inserted.id
    assert match.start_time is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_insert_match_uses_existing_gaps_before_shifting_later_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament = auth_context.tournament
    second_start = tournament.start_time + timedelta(minutes=25)
    third_start = tournament.start_time + timedelta(minutes=60)

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
        ) as court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court_inserted.id,
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
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": second_start,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as second_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": third_start,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as third_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": None,
                    "start_time": None,
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as inserted,
    ):
        body = MatchRescheduleBody(
            old_court_id=None,
            old_position=None,
            new_court_id=court_inserted.id,
            new_position=1,
        )
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{inserted.id}/reschedule",
                auth_context,
                json=body.model_dump(mode="json", exclude_none=False),
            )
            == SUCCESS_RESPONSE
        )
        inserted_match_row = await sql_get_match(inserted.id)
        second_match_row = await sql_get_match(second_match.id)
        third_match_row = await sql_get_match(third_match.id)
        await assert_row_count_and_clear(matches, 0)

    assert inserted_match_row.start_time == tournament.start_time + timedelta(minutes=15)
    assert second_match_row.start_time == tournament.start_time + timedelta(minutes=30)
    assert third_match_row.start_time == third_start


@pytest.mark.asyncio(loop_scope="session")
async def test_reschedule_match_honours_positions_across_courts(
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
        ),
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
        ) as moved_match,
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
        body = MatchRescheduleBody(
            old_court_id=court2_inserted.id,
            old_position=0,
            new_court_id=court1_inserted.id,
            new_position=2,
        )
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{moved_match.id}/reschedule",
                auth_context,
                json=body.model_dump(mode="json", exclude_none=False),
            )
            == SUCCESS_RESPONSE
        )
        stages = await get_full_tournament_details(tournament.id)
        moved = await sql_get_match(moved_match.id)
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

    # Court 1 now holds all 3 stage-1 matches plus the stage-2 match in start-time order.
    assert len(court1_matches) == 4
    for index, match in enumerate(court1_matches):
        assert match.start_time == tournament.start_time + timedelta(minutes=15 * index)

    # Court 2 only has the remaining stage-2 match; moving the earlier match away
    # leaves its old time behind as a gap.
    assert len(court2_matches) == 1
    assert court2_matches[0].start_time == stage2_start

    # The moved match landed at the user's requested position on court 1
    assert moved.court_id == court1_inserted.id
    assert moved.start_time == tournament.start_time + timedelta(minutes=30)


@pytest.mark.asyncio(loop_scope="session")
async def test_swap_matches_across_courts(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament = auth_context.tournament
    second_slot_start = tournament.start_time + timedelta(minutes=15)

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
        ) as court1_first_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court1_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": second_slot_start,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as swapped_match1,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court2_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": tournament.start_time,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as swapped_match2,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court2_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": second_slot_start,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as court2_second_match,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": tournament.id, "name": "Court 3"})
        ) as court3_inserted,
        # Deliberately gappy packing on an uninvolved court: a swap elsewhere must
        # not re-pack it (position stays 3, start time stays offset).
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court3_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": tournament.start_time + timedelta(minutes=45),
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as court3_match,
    ):
        body = MatchSwapBody(match1_id=swapped_match1.id, match2_id=swapped_match2.id)
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "matches/swap",
                auth_context,
                json=body.model_dump(mode="json"),
            )
            == SUCCESS_RESPONSE
        )
        match1 = await sql_get_match(swapped_match1.id)
        match2 = await sql_get_match(swapped_match2.id)
        untouched1 = await sql_get_match(court1_first_match.id)
        untouched2 = await sql_get_match(court2_second_match.id)
        uninvolved_court_match = await sql_get_match(court3_match.id)
        await assert_row_count_and_clear(matches, 0)

    # The two matches traded court/start-time slots.
    assert match1.court_id == court2_inserted.id
    assert match1.start_time == tournament.start_time
    assert match2.court_id == court1_inserted.id
    assert match2.start_time == second_slot_start

    # The other matches stayed where they were
    assert untouched1.court_id == court1_inserted.id
    assert untouched1.start_time == tournament.start_time
    assert untouched2.court_id == court2_inserted.id
    assert untouched2.start_time == second_slot_start

    # The uninvolved court was not re-packed at all
    assert uninvolved_court_match.court_id == court3_inserted.id
    assert uninvolved_court_match.start_time == tournament.start_time + timedelta(minutes=45)


@pytest.mark.asyncio(loop_scope="session")
async def test_swap_matches_same_court(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament = auth_context.tournament

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
        ) as first_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court1_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": tournament.start_time + timedelta(minutes=15),
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as middle_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court1_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": tournament.start_time + timedelta(minutes=30),
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as last_match,
    ):
        body = MatchSwapBody(match1_id=first_match.id, match2_id=last_match.id)
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "matches/swap",
                auth_context,
                json=body.model_dump(mode="json"),
            )
            == SUCCESS_RESPONSE
        )
        first = await sql_get_match(first_match.id)
        middle = await sql_get_match(middle_match.id)
        last = await sql_get_match(last_match.id)
        await assert_row_count_and_clear(matches, 0)

    assert first.start_time == tournament.start_time + timedelta(minutes=30)
    assert middle.start_time == tournament.start_time + timedelta(minutes=15)
    assert last.start_time == tournament.start_time
    assert first.court_id == middle.court_id == last.court_id == court1_inserted.id


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("tray_match_first", [False, True])
async def test_swap_scheduled_with_unscheduled_match(
    startup_and_shutdown_uvicorn_server: None,
    auth_context: AuthContext,
    tray_match_first: bool,
) -> None:
    tournament = auth_context.tournament

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
        ) as scheduled_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court1_inserted.id,
                    "state": MatchState.NOT_STARTED,
                    "start_time": tournament.start_time + timedelta(minutes=15),
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as second_scheduled_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": None,
                    "start_time": None,
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as tray_match,
    ):
        body = (
            MatchSwapBody(match1_id=tray_match.id, match2_id=scheduled_match.id)
            if tray_match_first
            else MatchSwapBody(match1_id=scheduled_match.id, match2_id=tray_match.id)
        )
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "matches/swap",
                auth_context,
                json=body.model_dump(mode="json"),
            )
            == SUCCESS_RESPONSE
        )
        displaced = await sql_get_match(scheduled_match.id)
        incoming = await sql_get_match(tray_match.id)
        untouched = await sql_get_match(second_scheduled_match.id)
        await assert_row_count_and_clear(matches, 0)

    # The tray match took over the scheduled match's exact slot
    assert incoming.court_id == court1_inserted.id
    assert incoming.start_time == tournament.start_time

    # The displaced match went back to the tray
    assert displaced.court_id is None
    assert displaced.start_time is None

    # The rest of the court kept its packing
    assert untouched.court_id == court1_inserted.id
    assert untouched.start_time == tournament.start_time + timedelta(minutes=15)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("state", "expected_detail"),
    [
        (
            MatchState.IN_PROGRESS,
            "Cannot move a in progress match back to Unscheduled. "
            "Only not started matches can be unscheduled.",
        ),
        (
            MatchState.COMPLETED,
            "Cannot move a completed match back to Unscheduled. "
            "Only not started matches can be unscheduled.",
        ),
    ],
)
async def test_swap_started_match_with_unscheduled_fails(
    startup_and_shutdown_uvicorn_server: None,
    auth_context: AuthContext,
    state: MatchState,
    expected_detail: str,
) -> None:
    tournament = auth_context.tournament

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
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court1_inserted.id,
                    "state": state,
                    "start_time": tournament.start_time,
                    "completed_at": DUMMY_MATCH1.completed_at
                    if state is MatchState.COMPLETED
                    else None,
                }
            )
        ) as scheduled_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": None,
                    "start_time": None,
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as tray_match,
    ):
        body = MatchSwapBody(match1_id=scheduled_match.id, match2_id=tray_match.id)
        response = await send_tournament_request(
            HTTPMethod.POST,
            "matches/swap",
            auth_context,
            json=body.model_dump(mode="json"),
        )
        scheduled = await sql_get_match(scheduled_match.id)
        unscheduled = await sql_get_match(tray_match.id)
        await assert_row_count_and_clear(matches, 0)

    assert response["detail"] == expected_detail
    assert scheduled.court_id == court1_inserted.id
    assert unscheduled.court_id is None
    assert unscheduled.start_time is None


@pytest.mark.asyncio(loop_scope="session")
async def test_swap_two_unscheduled_matches_fails(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament = auth_context.tournament

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
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": None,
                    "start_time": None,
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as tray_match1,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": None,
                    "start_time": None,
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as tray_match2,
    ):
        body = MatchSwapBody(match1_id=tray_match1.id, match2_id=tray_match2.id)
        response = await send_tournament_request(
            HTTPMethod.POST,
            "matches/swap",
            auth_context,
            json=body.model_dump(mode="json"),
        )
        await assert_row_count_and_clear(matches, 0)

    assert response["detail"] == "At least one of the matches must be scheduled to swap them"


@pytest.mark.asyncio(loop_scope="session")
async def test_unschedule_match_reorders_remaining_positions(
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
        ),
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
        ) as unscheduled_match,
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
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{unscheduled_match.id}/unschedule",
                auth_context,
            )
            == SUCCESS_RESPONSE
        )
        stages = await get_full_tournament_details(tournament.id)
        unscheduled = await sql_get_match(unscheduled_match.id)
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

    # The unscheduled match is gone from any court
    assert unscheduled.court_id is None
    assert unscheduled.start_time is None

    # Remaining court-1 matches keep their relative order and start sequentially
    assert len(court1_matches) == 3
    for index, match in enumerate(court1_matches):
        assert match.start_time == tournament.start_time + timedelta(minutes=15 * index)

    # Court 2 only has the stage-2 match left; the removed match's time stays as a gap.
    assert len(court2_matches) == 1
    assert court2_matches[0].start_time == stage2_start
