import pytest
from heliclockter import timedelta

from bracket.models.db.match import MatchRescheduleBody, MatchState
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
            old_position=1,
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
    assert match.position_in_schedule == 0


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
    assert match.position_in_schedule is None


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
    assert match.position_in_schedule == DUMMY_MATCH1.position_in_schedule


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
                    "position_in_schedule": None,
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
    assert match.position_in_schedule == 0
    assert match.start_time is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_reschedule_match_preserves_stage_boundaries_across_courts(
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
async def test_unschedule_match_preserves_stage_boundaries_across_courts(
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
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{unscheduled_match.id}/unschedule",
                auth_context,
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
