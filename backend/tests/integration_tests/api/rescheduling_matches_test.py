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
        key=lambda m: m.position_in_schedule,
    )
    court2_matches = sorted(
        (m for m in all_matches if m.court_id == court2_inserted.id),
        key=lambda m: m.position_in_schedule,
    )

    # Court 1 now holds all 3 stage-1 matches plus the stage-2 match in position order
    assert len(court1_matches) == 4
    for index, match in enumerate(court1_matches):
        assert match.position_in_schedule == index
        assert match.start_time == tournament.start_time + timedelta(minutes=15 * index)

    # Court 2 only has the remaining stage-2 match, starting at tournament start time
    # (no global stage barrier — cross-level interleaving is allowed)
    assert len(court2_matches) == 1
    assert court2_matches[0].position_in_schedule == 0
    assert court2_matches[0].start_time == tournament.start_time

    # The moved match landed at the user's requested position on court 1
    assert moved.court_id == court1_inserted.id
    assert moved.position_in_schedule == 2
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
                    "position_in_schedule": 0,
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
                    "position_in_schedule": 1,
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
                    "position_in_schedule": 0,
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
                    "position_in_schedule": 1,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as court2_second_match,
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
        await assert_row_count_and_clear(matches, 0)

    # The two matches traded court and position; start times follow the new slots
    assert match1.court_id == court2_inserted.id
    assert match1.position_in_schedule == 0
    assert match1.start_time == tournament.start_time
    assert match2.court_id == court1_inserted.id
    assert match2.position_in_schedule == 1
    assert match2.start_time == second_slot_start

    # The other matches stayed where they were
    assert untouched1.court_id == court1_inserted.id
    assert untouched1.position_in_schedule == 0
    assert untouched1.start_time == tournament.start_time
    assert untouched2.court_id == court2_inserted.id
    assert untouched2.position_in_schedule == 1
    assert untouched2.start_time == second_slot_start


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
                    "position_in_schedule": 0,
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
                    "position_in_schedule": 1,
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
                    "position_in_schedule": 2,
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

    assert first.position_in_schedule == 2
    assert first.start_time == tournament.start_time + timedelta(minutes=30)
    assert middle.position_in_schedule == 1
    assert middle.start_time == tournament.start_time + timedelta(minutes=15)
    assert last.position_in_schedule == 0
    assert last.start_time == tournament.start_time
    assert first.court_id == middle.court_id == last.court_id == court1_inserted.id


@pytest.mark.asyncio(loop_scope="session")
async def test_swap_with_unscheduled_match_fails(
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
                    "position_in_schedule": 0,
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
                    "court_id": None,
                    "start_time": None,
                    "position_in_schedule": None,
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as unscheduled_match,
    ):
        body = MatchSwapBody(match1_id=scheduled_match.id, match2_id=unscheduled_match.id)
        response = await send_tournament_request(
            HTTPMethod.POST,
            "matches/swap",
            auth_context,
            json=body.model_dump(mode="json"),
        )
        scheduled = await sql_get_match(scheduled_match.id)
        await assert_row_count_and_clear(matches, 0)

    assert response["detail"] == "Both matches must be scheduled to swap them"
    assert scheduled.court_id == court1_inserted.id
    assert scheduled.position_in_schedule == 0


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
        key=lambda m: m.position_in_schedule,
    )
    court2_matches = sorted(
        (m for m in all_matches if m.court_id == court2_inserted.id),
        key=lambda m: m.position_in_schedule,
    )

    # The unscheduled match is gone from any court
    assert unscheduled.court_id is None
    assert unscheduled.start_time is None
    assert unscheduled.position_in_schedule is None

    # Remaining court-1 matches keep their relative order and start sequentially
    assert len(court1_matches) == 3
    for index, match in enumerate(court1_matches):
        assert match.position_in_schedule == index
        assert match.start_time == tournament.start_time + timedelta(minutes=15 * index)

    # Court 2 only has the stage-2 match left, starting at tournament start time
    # (no global stage barrier — cross-level interleaving is allowed)
    assert len(court2_matches) == 1
    assert court2_matches[0].position_in_schedule == 0
    assert court2_matches[0].start_time == tournament.start_time
