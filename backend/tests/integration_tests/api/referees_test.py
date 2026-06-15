import pytest

from bracket.database import database
from bracket.models.db.match import Match
from bracket.models.db.referee import RefereeInsertable
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.schema import matches, referees
from bracket.sql.matches import sql_get_match_with_details
from bracket.sql.referees import (
    sql_get_referee_by_id,
    sql_get_referee_by_team,
    sql_get_referees,
    sql_upsert_referee_by_name,
    sql_upsert_referee_by_team,
)
from bracket.sql.teams import sql_delete_team
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.dummy_records import (
    DUMMY_CLUB,
    DUMMY_COURT1,
    DUMMY_MATCH1,
    DUMMY_MOCK_TIME,
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
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_club,
    inserted_court,
    inserted_match,
    inserted_ranking,
    inserted_referee,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
    inserted_tournament,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_referee_upsert_is_idempotent_by_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})
    ) as team:
        first = await sql_upsert_referee_by_team(tournament_id, team.id)
        second = await sql_upsert_referee_by_team(tournament_id, team.id)

        assert first.id == second.id
        assert first.team_id == team.id
        assert first.name is None

        all_referees = await sql_get_referees(tournament_id)
        assert len(all_referees) == 1

        await assert_row_count_and_clear(referees, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_referee_check_constraint_is_mutually_exclusive(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})
    ) as team:
        # Both team_id and name set violates the "exactly one" check constraint.
        with pytest.raises(Exception):
            await database.execute(
                query=referees.insert().values(
                    tournament_id=tournament_id,
                    team_id=team.id,
                    name="Both set",
                    created=DUMMY_MOCK_TIME,
                )
            )

        # Neither set also violates it.
        with pytest.raises(Exception):
            await database.execute(
                query=referees.insert().values(
                    tournament_id=tournament_id,
                    team_id=None,
                    name=None,
                    created=DUMMY_MOCK_TIME,
                )
            )

        await assert_row_count_and_clear(referees, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_patch_match_referee_team_id_round_trips(
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
        inserted_team(
            DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})
        ) as referee_team,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1.id,
                tournament_id=tournament_id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as input1,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2.id,
                tournament_id=tournament_id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as input2,
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
        # Assign the referee.
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                {"round_id": round_inserted.id, "referee_team_id": referee_team.id},
            )
            == SUCCESS_RESPONSE
        )

        referee = await sql_get_referee_by_team(tournament_id, referee_team.id)
        assert referee is not None
        assert await sql_get_referee_by_id(tournament_id, referee.id) == referee

        match_with_details = await sql_get_match_with_details(tournament_id, match_inserted.id)
        assert match_with_details is not None
        assert match_with_details.referee_id == referee.id
        assert match_with_details.referee is not None
        assert match_with_details.referee.team_id == referee_team.id
        assert match_with_details.referee.name is None
        assert match_with_details.referee.team_name == referee_team.name

        # A subsequent edit that omits referee_team_id must keep the assignment.
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
        assert match_after_edit.referee_id == referee.id

        # Clearing it (null) unassigns.
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                {"round_id": round_inserted.id, "referee_team_id": None},
            )
            == SUCCESS_RESPONSE
        )
        match_cleared = await fetch_one_parsed_certain(
            database, Match, query=matches.select().where(matches.c.id == match_inserted.id)
        )
        assert match_cleared.referee_id is None

        await assert_row_count_and_clear(matches, 1)
        await assert_row_count_and_clear(referees, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_deleting_referee_team_cascades_and_nulls_match(
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
        inserted_team(
            DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})
        ) as referee_team,
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
        referee = await sql_upsert_referee_by_team(tournament_id, referee_team.id)
        await database.execute(
            query=matches.update()
            .where(matches.c.id == match_inserted.id)
            .values(referee_id=referee.id)
        )

        # Deleting the team cascades: its referee row is removed and the match's
        # referee_id is nulled.
        await sql_delete_team(tournament_id, referee_team.id)

        assert await sql_get_referee_by_team(tournament_id, referee_team.id) is None
        assert len(await sql_get_referees(tournament_id)) == 0

        match_after = await fetch_one_parsed_certain(
            database, Match, query=matches.select().where(matches.c.id == match_inserted.id)
        )
        assert match_after.referee_id is None

        await assert_row_count_and_clear(matches, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_insert_referee_fixture_with_name(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    # A free-text referee row (name set, team_id null) is allowed by the constraint;
    # this guards the schema even though slice 1 never writes one via the API.
    tournament_id = auth_context.tournament.id
    async with inserted_referee(
        RefereeInsertable(
            tournament_id=tournament_id,
            team_id=None,
            name="John Smith",
            created=DUMMY_MOCK_TIME,
        )
    ) as referee:
        assert referee.name == "John Smith"
        assert referee.team_id is None

        fetched = await sql_get_referee_by_id(tournament_id, referee.id)
        assert fetched is not None
        assert fetched.name == "John Smith"


@pytest.mark.asyncio(loop_scope="session")
async def test_referee_upsert_is_idempotent_by_name(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    first = await sql_upsert_referee_by_name(tournament_id, "Jane Doe")
    second = await sql_upsert_referee_by_name(tournament_id, "Jane Doe")

    assert first.id == second.id
    assert first.name == "Jane Doe"
    assert first.team_id is None

    all_referees = await sql_get_referees(tournament_id)
    assert len(all_referees) == 1

    await assert_row_count_and_clear(referees, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_referee_name_is_tournament_scoped(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_club(DUMMY_CLUB) as other_club,
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={"club_id": other_club.id, "dashboard_endpoint": "endpoint-other"}
            )
        ) as other_tournament,
        inserted_ranking(DUMMY_RANKING1.model_copy(update={"tournament_id": other_tournament.id})),
    ):
        ref1 = await sql_upsert_referee_by_name(tournament_id, "Shared Name")
        ref2 = await sql_upsert_referee_by_name(other_tournament.id, "Shared Name")

        assert ref1.id != ref2.id
        assert ref1.tournament_id == tournament_id
        assert ref2.tournament_id == other_tournament.id

        await assert_row_count_and_clear(referees, 2)


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
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament_id})) as team2,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=team1.id,
                tournament_id=tournament_id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as input1,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team2.id,
                tournament_id=tournament_id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as input2,
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
        assert match_with_details.referee is not None
        assert match_with_details.referee.name == "External Ref"
        assert match_with_details.referee.team_id is None
        assert match_with_details.referee.team_name is None

        # Calling again with the same name is idempotent (no duplicate row).
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
        all_referees = await sql_get_referees(tournament_id)
        assert len(all_referees) == 1

        # Clearing both fields unassigns.
        assert (
            await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{match_inserted.id}",
                auth_context,
                None,
                {"round_id": round_inserted.id, "referee_name": None, "referee_team_id": None},
            )
            == SUCCESS_RESPONSE
        )
        match_cleared = await fetch_one_parsed_certain(
            database, Match, query=matches.select().where(matches.c.id == match_inserted.id)
        )
        assert match_cleared.referee_id is None

        await assert_row_count_and_clear(matches, 1)
        await assert_row_count_and_clear(referees, 1)


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
        inserted_team(
            DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})
        ) as referee_team,
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
                "referee_team_id": referee_team.id,
                "referee_name": "Some Name",
            },
        )
        assert "detail" in response
        assert "success" not in response

        await assert_row_count_and_clear(matches, 1)
        await assert_row_count_and_clear(referees, 0)
