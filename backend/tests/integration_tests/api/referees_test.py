from contextlib import AbstractAsyncContextManager

import pytest

from bracket.database import database
from bracket.models.db.match import Match
from bracket.models.db.stage_item_inputs import (
    StageItemInputEmpty,
    StageItemInputFinal,
    StageItemInputInsertable,
)
from bracket.schema import matches, stage_item_inputs
from bracket.sql.matches import sql_get_match_with_details
from bracket.sql.referees import sql_get_referee_names
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_LEVEL1,
    DUMMY_LEVEL2,
    DUMMY_MATCH1,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM2,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
)
from bracket.utils.http import HTTPMethod
from bracket.utils.id_types import StageItemId, TeamId, TournamentId
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_court,
    inserted_level,
    inserted_match,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


def _final_input(
    tournament_id: TournamentId, stage_item_id: StageItemId, slot: int, team_id: TeamId
) -> AbstractAsyncContextManager[StageItemInputFinal | StageItemInputEmpty]:
    return inserted_stage_item_input(
        StageItemInputInsertable(
            slot=slot,
            team_id=team_id,
            tournament_id=tournament_id,
            stage_item_id=stage_item_id,
        )
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_patch_match_referee_slot_round_trips(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament_id})) as team2,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})) as team3,
        _final_input(tournament_id, stage_item_inserted.id, 0, team1.id) as input1,
        _final_input(tournament_id, stage_item_inserted.id, 1, team2.id) as input2,
        _final_input(tournament_id, stage_item_inserted.id, 2, team3.id) as referee_input,
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": tournament_id})
        ) as court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": input1.id,
                    "stage_item_input2_id": input2.id,
                    "court_id": court_inserted.id,
                }
            )
        ) as match_inserted,
    ):
        # Assign a referee slot (team 3's input).
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                {"round_id": round_inserted.id, "referee_stage_item_input_id": referee_input.id},
            )
            == SUCCESS_RESPONSE
        )

        match_with_details = await sql_get_match_with_details(tournament_id, match_inserted.id)
        assert match_with_details is not None
        assert match_with_details.referee_stage_item_input_id == referee_input.id
        # The referee slot hydrates to the resolved team, just like a playing slot.
        assert isinstance(match_with_details.referee, StageItemInputFinal)
        assert match_with_details.referee.team_id == team3.id
        assert match_with_details.referee.team.name == team3.name
        assert match_with_details.referee_name is None

        # A subsequent edit that omits the referee fields must keep the assignment.
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                {"round_id": round_inserted.id, "custom_duration_minutes": 20},
            )
            == SUCCESS_RESPONSE
        )
        match_after_edit = await fetch_one_parsed_certain(
            database, Match, query=matches.select().where(matches.c.id == match_inserted.id)
        )
        assert match_after_edit.referee_stage_item_input_id == referee_input.id

        # Clearing it (null) unassigns.
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                {"round_id": round_inserted.id, "referee_stage_item_input_id": None},
            )
            == SUCCESS_RESPONSE
        )
        match_cleared = await fetch_one_parsed_certain(
            database, Match, query=matches.select().where(matches.c.id == match_inserted.id)
        )
        assert match_cleared.referee_stage_item_input_id is None

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_deleting_referee_input_nulls_match(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Deleting the referenced stage_item_input nulls the match's referee (ON DELETE SET NULL)."""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})) as team3,
        _final_input(tournament_id, stage_item_inserted.id, 2, team3.id) as referee_input,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": None,
                    "stage_item_input2_id": None,
                    "court_id": None,
                    "referee_stage_item_input_id": referee_input.id,
                }
            )
        ) as match_inserted,
    ):
        await database.execute(
            query=stage_item_inputs.delete().where(stage_item_inputs.c.id == referee_input.id)
        )

        match_after = await fetch_one_parsed_certain(
            database, Match, query=matches.select().where(matches.c.id == match_inserted.id)
        )
        assert match_after.referee_stage_item_input_id is None

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_patch_match_referee_name_round_trips(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
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
            DUMMY_COURT1.model_copy(update={"tournament_id": tournament_id})
        ) as court_inserted,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": None,
                    "stage_item_input2_id": None,
                    "court_id": court_inserted.id,
                }
            )
        ) as match_inserted,
    ):
        # Assign a free-text referee by name.
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                {"round_id": round_inserted.id, "referee_name": "External Ref"},
            )
            == SUCCESS_RESPONSE
        )

        match_with_details = await sql_get_match_with_details(tournament_id, match_inserted.id)
        assert match_with_details is not None
        assert match_with_details.referee_name == "External Ref"
        assert match_with_details.referee is None
        assert match_with_details.referee_stage_item_input_id is None

        # The names endpoint surfaces the distinct free-text names within the tournament.
        names = await sql_get_referee_names(tournament_id)
        assert names == ["External Ref"]
        names_response = await send_tournament_request(HTTPMethod.GET, "referees", auth_context)
        assert names_response == {"data": ["External Ref"]}

        # Clearing both fields unassigns.
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                {
                    "round_id": round_inserted.id,
                    "referee_name": None,
                    "referee_stage_item_input_id": None,
                },
            )
            == SUCCESS_RESPONSE
        )
        match_cleared = await fetch_one_parsed_certain(
            database, Match, query=matches.select().where(matches.c.id == match_inserted.id)
        )
        assert match_cleared.referee_name is None

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_patch_match_both_referee_fields_rejected(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})) as team3,
        _final_input(tournament_id, stage_item_inserted.id, 2, team3.id) as referee_input,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_inserted.id,
                    "stage_item_input1_id": None,
                    "stage_item_input2_id": None,
                    "court_id": None,
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
                "round_id": round_inserted.id,
                "referee_stage_item_input_id": referee_input.id,
                "referee_name": "Some Name",
            },
        )
        assert "detail" in response
        assert "success" not in response

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_patch_match_referee_slot_wrong_level_rejected(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A referee slot in a stage item at a different level than the match is rejected."""
    tournament_id = auth_context.tournament.id
    async with (
        inserted_level(DUMMY_LEVEL1.model_copy(update={"tournament_id": tournament_id})) as level1,
        inserted_level(DUMMY_LEVEL2.model_copy(update={"tournament_id": tournament_id})) as level2,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id, "level_id": level1.id})
        ) as stage_a,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id, "level_id": level2.id})
        ) as stage_b,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_a.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_a,
        inserted_stage_item(
            DUMMY_STAGE_ITEM2.model_copy(
                update={"stage_id": stage_b.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_b,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_a.id})
        ) as round_a,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})) as team3,
        _final_input(tournament_id, stage_item_b.id, 0, team3.id) as other_level_input,
        inserted_match(
            DUMMY_MATCH1.model_copy(
                update={
                    "round_id": round_a.id,
                    "stage_item_input1_id": None,
                    "stage_item_input2_id": None,
                    "court_id": None,
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
                "round_id": round_a.id,
                "referee_stage_item_input_id": other_level_input.id,
            },
        )
        assert "detail" in response
        assert "success" not in response

        match_after = await fetch_one_parsed_certain(
            database, Match, query=matches.select().where(matches.c.id == match_inserted.id)
        )
        assert match_after.referee_stage_item_input_id is None

        await assert_row_count_and_clear(matches, 1)
