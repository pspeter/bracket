import pytest

from bracket.models.db.match import MatchSetState
from bracket.models.db.ranking import RankingMatchPointsBody
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_MATCH1,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_court,
    inserted_match,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_per_set_update_sets_and_clears_completed_at(
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
        ) as input1,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as input2,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court_inserted.id,
                    "completed_at": None,
                }
            )
        ) as match_inserted,
    ):
        set_id = match_inserted.match_sets[0].id

        # Completing the only set derives a COMPLETED match and stamps completed_at.
        completed = await send_tournament_request(
            HTTPMethod.PUT,
            f"matches/{match_inserted.id}/sets/{set_id}",
            auth_context,
            json={
                "stage_item_input1_score": 21,
                "stage_item_input2_score": 10,
                "state": "COMPLETED",
            },
        )
        assert completed["data"]["state"] == "COMPLETED"
        assert completed["data"]["completed_at"] is not None

        # Reverting the set back to IN_PROGRESS clears completed_at again.
        reverted = await send_tournament_request(
            HTTPMethod.PUT,
            f"matches/{match_inserted.id}/sets/{set_id}",
            auth_context,
            json={
                "stage_item_input1_score": 21,
                "stage_item_input2_score": 10,
                "state": "IN_PROGRESS",
            },
        )
        assert reverted["data"]["state"] == "IN_PROGRESS"
        assert reverted["data"]["completed_at"] is None


@pytest.mark.asyncio(loop_scope="session")
async def test_num_sets_change_requires_force_when_active_and_resizes(
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
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "court_id": court_inserted.id,
                    "stage_item_input1_id": None,
                    "stage_item_input2_id": None,
                    "completed_at": None,
                }
            ),
            set_score1=21,
            set_score2=10,
            set_state=MatchSetState.COMPLETED,
        ) as match_inserted,
    ):
        ranking_id = auth_context.ranking.id
        body = RankingMatchPointsBody(num_sets=3).model_dump(mode="json")

        try:
            # A completed set blocks reducing/changing num_sets without force.
            blocked = await send_tournament_request(
                HTTPMethod.PUT, f"rankings/{ranking_id}", auth_context, json=body
            )
            assert "force=true" in blocked["detail"]

            # Forcing the change resizes existing matches up to the new set count.
            assert (
                await send_tournament_request(
                    HTTPMethod.PUT, f"rankings/{ranking_id}?force=true", auth_context, json=body
                )
                == SUCCESS_RESPONSE
            )

            # Re-fetching the match (via a no-op set update) shows 3 sets and num_sets=3.
            match_detail = await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}/sets/{match_inserted.match_sets[0].id}",
                auth_context,
                json={
                    "stage_item_input1_score": 21,
                    "stage_item_input2_score": 10,
                    "state": "COMPLETED",
                },
            )
            assert len(match_detail["data"]["match_sets"]) == 3
            assert match_detail["data"]["num_sets"] == 3
        finally:
            # auth_context (and its ranking) is session-scoped, so restore num_sets to its
            # default so later tests see an unmodified ranking.
            await send_tournament_request(
                HTTPMethod.PUT,
                f"rankings/{ranking_id}?force=true",
                auth_context,
                json=RankingMatchPointsBody(num_sets=1).model_dump(mode="json"),
            )
