import pytest

from bracket.database import database
from bracket.models.db.match import MatchInsertable
from bracket.models.db.round import RoundLifecycleState
from bracket.schema import stage_item_inputs
from bracket.utils.dummy_records import (
    DUMMY_MATCH1,
    DUMMY_MOCK_TIME,
    DUMMY_PLAYER1,
    DUMMY_PLAYER2,
    DUMMY_PLAYER3,
    DUMMY_PLAYER4,
    DUMMY_PLAYER5,
    DUMMY_RANKING1,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
    DUMMY_TOURNAMENT,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_auth_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_match,
    inserted_player,
    inserted_player_in_team,
    inserted_ranking,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_team,
    inserted_tournament,
)


def unscheduled_match(round_id: int) -> MatchInsertable:
    return DUMMY_MATCH1.model_copy(
        update={
            "round_id": round_id,
            "start_time": None,
            "court_id": None,
            "stage_item_input1_id": None,
            "stage_item_input2_id": None,
            "completed_at": None,
        }
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_tournament_issues_endpoint_counts_open_nav_issues(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "club_id": auth_context.club.id,
                    "dashboard_endpoint": "issues-test",
                    "min_team_size": 2,
                }
            )
        ) as tournament,
        inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": tournament.id})
        ) as ranking,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament.id})) as team_1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament.id})),
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament.id})),
        inserted_player(DUMMY_PLAYER1.model_copy(update={"tournament_id": tournament.id})),
        inserted_player(DUMMY_PLAYER2.model_copy(update={"tournament_id": tournament.id})),
        inserted_player_in_team(
            DUMMY_PLAYER3.model_copy(update={"tournament_id": tournament.id}), team_1.id
        ),
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament.id})) as stage,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(update={"stage_id": stage.id, "ranking_id": ranking.id})
        ) as stage_item,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item.id})
        ) as active_round,
        inserted_round(
            DUMMY_ROUND1.model_copy(
                update={
                    "stage_item_id": stage_item.id,
                    "name": "Draft round",
                    "lifecycle_state": RoundLifecycleState.PLACEHOLDER,
                }
            )
        ) as draft_round,
        inserted_match(unscheduled_match(active_round.id)),
        inserted_match(unscheduled_match(draft_round.id)),
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": active_round.id,
                    "court_id": None,
                    "stage_item_input1_id": None,
                    "stage_item_input2_id": None,
                    "completed_at": DUMMY_MOCK_TIME,
                }
            )
        ),
    ):
        await database.execute_many(
            query=stage_item_inputs.insert(),
            values=[
                {
                    "slot": 1,
                    "tournament_id": tournament.id,
                    "stage_item_id": stage_item.id,
                    "team_id": team_1.id,
                    "winner_from_stage_item_id": None,
                    "winner_position": None,
                },
                {
                    "slot": 2,
                    "tournament_id": tournament.id,
                    "stage_item_id": stage_item.id,
                    "team_id": None,
                    "winner_from_stage_item_id": None,
                    "winner_position": None,
                },
                {
                    "slot": 3,
                    "tournament_id": tournament.id,
                    "stage_item_id": stage_item.id,
                    "team_id": None,
                    "winner_from_stage_item_id": stage_item.id,
                    "winner_position": 1,
                },
                {
                    "slot": 4,
                    "tournament_id": tournament.id,
                    "stage_item_id": stage_item.id,
                    "team_id": None,
                    "winner_from_stage_item_id": None,
                    "winner_position": None,
                },
            ],
        )

        assert await send_auth_request(
            HTTPMethod.GET, f"tournaments/{tournament.id}/issues", auth_context
        ) == {
            "data": {
                "planning": [{"type": "unplanned_matches", "count": 2}],
                "players": [{"type": "players_without_team", "count": 2}],
                "stages": [
                    {"type": "empty_slots", "count": 2},
                    {"type": "unassigned_teams", "count": 2},
                ],
                "teams": [{"type": "teams_below_min_size", "count": 3}],
            }
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_tournament_issues_endpoint_omits_zero_count_entries(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_tournament(
        DUMMY_TOURNAMENT.model_copy(
            update={
                "club_id": auth_context.club.id,
                "dashboard_endpoint": "issues-empty-test",
            }
        )
    ) as tournament:
        assert await send_auth_request(
            HTTPMethod.GET, f"tournaments/{tournament.id}/issues", auth_context
        ) == {"data": {"planning": [], "players": [], "stages": [], "teams": []}}


@pytest.mark.asyncio(loop_scope="session")
async def test_tournament_issues_endpoint_counts_teams_strictly_below_min_size(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "club_id": auth_context.club.id,
                    "dashboard_endpoint": "issues-teams-test",
                    "min_team_size": 2,
                }
            )
        ) as tournament,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament.id})) as team_1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament.id})) as team_2,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament.id})),
        inserted_player_in_team(
            DUMMY_PLAYER1.model_copy(update={"tournament_id": tournament.id}), team_1.id
        ),
        inserted_player_in_team(
            DUMMY_PLAYER2.model_copy(update={"tournament_id": tournament.id}), team_2.id
        ),
        inserted_player_in_team(
            DUMMY_PLAYER3.model_copy(update={"tournament_id": tournament.id}), team_2.id
        ),
        inserted_player(DUMMY_PLAYER4.model_copy(update={"tournament_id": tournament.id})),
        inserted_player(DUMMY_PLAYER5.model_copy(update={"tournament_id": tournament.id})),
    ):
        assert await send_auth_request(
            HTTPMethod.GET, f"tournaments/{tournament.id}/issues", auth_context
        ) == {
            "data": {
                "planning": [],
                "players": [{"type": "players_without_team", "count": 2}],
                "stages": [{"type": "unassigned_teams", "count": 3}],
                "teams": [{"type": "teams_below_min_size", "count": 2}],
            }
        }
