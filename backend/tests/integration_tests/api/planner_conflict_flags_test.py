from typing import cast

import pytest
from heliclockter import timedelta

from bracket.models.db.match import MatchRescheduleBody, MatchState, MatchSwapBody
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.schema import matches
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_COURT2,
    DUMMY_MATCH1,
    DUMMY_ROUND1,
    DUMMY_ROUND3,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
    DUMMY_TEAM4,
)
from bracket.utils.http import HTTPMethod
from bracket.utils.types import JsonDict
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


def _match_from_stages_response(response: JsonDict, match_id: int) -> JsonDict:
    for stage in response["data"]:
        for stage_item in stage["stage_items"]:
            for round_ in stage_item["rounds"]:
                for match in round_["matches"]:
                    if match["id"] == match_id:
                        return cast("JsonDict", match)
    raise AssertionError(f"Could not find match {match_id}")


@pytest.mark.asyncio(loop_scope="session")
async def test_precedence_flag_appears_and_clears_through_api(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament = auth_context.tournament
    later_start = tournament.start_time + timedelta(minutes=30)

    async with (
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament.id})) as stage,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item.id})
        ) as semi_round,
        inserted_round(
            DUMMY_ROUND3.model_copy(update={"stage_item_id": stage_item.id})
        ) as final_round,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament.id})) as team1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament.id})) as team2,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament.id})) as team3,
        inserted_team(DUMMY_TEAM4.model_copy(update={"tournament_id": tournament.id})) as team4,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team1.id,
                tournament_id=tournament.id,
                stage_item_id=stage_item.id,
            )
        ) as input1,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=2,
                team_id=team2.id,
                tournament_id=tournament.id,
                stage_item_id=stage_item.id,
            )
        ) as input2,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=3,
                team_id=team3.id,
                tournament_id=tournament.id,
                stage_item_id=stage_item.id,
            )
        ) as input3,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=4,
                team_id=team4.id,
                tournament_id=tournament.id,
                stage_item_id=stage_item.id,
            )
        ) as input4,
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tournament.id})) as court1,
        inserted_court(DUMMY_COURT2.model_copy(update={"tournament_id": tournament.id})) as court2,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": semi_round.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court1.id,
                    "start_time": tournament.start_time,
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as semi1,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": semi_round.id,
                    "stage_item_input1_id": input3.id,
                    "stage_item_input2_id": input4.id,
                    "court_id": court1.id,
                    "start_time": tournament.start_time + timedelta(minutes=15),
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as semi2,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": final_round.id,
                    "stage_item_input1_id": None,
                    "stage_item_input2_id": None,
                    "stage_item_input1_winner_from_match_id": semi1.id,
                    "stage_item_input2_winner_from_match_id": semi2.id,
                    "court_id": court2.id,
                    "start_time": tournament.start_time + timedelta(minutes=5),
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as final,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": final_round.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input4.id,
                    "court_id": court2.id,
                    "start_time": later_start,
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as later_match,
    ):
        body = MatchRescheduleBody(
            old_court_id=court2.id,
            old_position=0,
            new_court_id=court2.id,
            new_position=0,
        )
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{final.id}/reschedule",
                auth_context,
                json=body.model_dump(mode="json", exclude_none=False),
            )
            == SUCCESS_RESPONSE
        )
        response = await send_tournament_request(HTTPMethod.GET, "stages", auth_context)
        assert _match_from_stages_response(response, final.id)["precedence_conflict"] is True

        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "matches/swap",
                auth_context,
                json=MatchSwapBody(match1_id=final.id, match2_id=later_match.id).model_dump(
                    mode="json"
                ),
            )
            == SUCCESS_RESPONSE
        )
        response = await send_tournament_request(HTTPMethod.GET, "stages", auth_context)
        assert _match_from_stages_response(response, final.id)["precedence_conflict"] is False

        await assert_row_count_and_clear(matches, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_short_break_flag_appears_and_clears_through_api(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament = auth_context.tournament

    async with (
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament.id})) as stage,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item,
        inserted_round(DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item.id})) as round_,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament.id})) as team1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament.id})) as team2,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team1.id,
                tournament_id=tournament.id,
                stage_item_id=stage_item.id,
            )
        ) as input1,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=2,
                team_id=team2.id,
                tournament_id=tournament.id,
                stage_item_id=stage_item.id,
            )
        ) as input2,
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tournament.id})) as court,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court.id,
                    "start_time": tournament.start_time,
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as first_match,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court.id,
                    "start_time": tournament.start_time + timedelta(minutes=12),
                    "state": MatchState.NOT_STARTED,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                    "completed_at": None,
                }
            )
        ) as second_match,
    ):
        body = MatchRescheduleBody(
            old_court_id=court.id,
            old_position=1,
            new_court_id=court.id,
            new_position=1,
        )
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{second_match.id}/reschedule",
                auth_context,
                json=body.model_dump(mode="json", exclude_none=False),
            )
            == SUCCESS_RESPONSE
        )
        response = await send_tournament_request(HTTPMethod.GET, "stages", auth_context)
        assert (
            _match_from_stages_response(response, second_match.id)["short_break_conflict"] is True
        )

        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{first_match.id}",
                auth_context,
                json={"round_id": round_.id, "custom_duration_minutes": 7},
            )
            == SUCCESS_RESPONSE
        )
        response = await send_tournament_request(HTTPMethod.GET, "stages", auth_context)
        assert (
            _match_from_stages_response(response, second_match.id)["short_break_conflict"] is False
        )

        await assert_row_count_and_clear(matches, 0)
