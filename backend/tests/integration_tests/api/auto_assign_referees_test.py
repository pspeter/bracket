import pytest

from bracket.database import database
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItem, StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import tournaments
from bracket.sql.referees import sql_set_match_referee, sql_upsert_referee_by_team
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import DUMMY_COURT1, DUMMY_STAGE1, DUMMY_STAGE_ITEM1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from bracket.utils.id_types import StageId, TeamId, TournamentId
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_court, inserted_stage, inserted_team

_ENDPOINT = "matches/auto-assign-referees"


async def _setup_round_robin_3teams(
    tid: TournamentId, stage_id: StageId, t1_id: TeamId, t2_id: TeamId, t3_id: TeamId
) -> StageItem:
    """3-team round-robin: each team can ref the match it isn't playing in."""
    si = await sql_create_stage_item_with_inputs(
        tid,
        StageItemWithInputsCreate(
            stage_id=stage_id,
            name=DUMMY_STAGE_ITEM1.name,
            team_count=3,
            type=DUMMY_STAGE_ITEM1.type,
            inputs=[
                StageItemInputCreateBodyFinal(slot=1, team_id=t1_id),
                StageItemInputCreateBodyFinal(slot=2, team_id=t2_id),
                StageItemInputCreateBodyFinal(slot=3, team_id=t3_id),
            ],
        ),
    )
    await build_matches_for_stage_item(si, tid)
    return si


@pytest.mark.asyncio(loop_scope="session")
async def test_auto_assign_referees_fills_missing_only(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Endpoint fills referee slots on matches that have none, leaving schedule intact."""
    tid = auth_context.tournament.id

    await database.execute(
        query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=True)
    )
    try:
        async with (
            inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
            inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t2,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t3,
        ):
            si = await _setup_round_robin_3teams(tid, stage.id, t1.id, t2.id, t3.id)
            # Schedule matches so they have court_id / start_time
            await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)

            stages_before = await get_full_tournament_details(tid)
            scheduled_before = [
                (m.id, m.court_id, m.start_time)
                for s in stages_before
                for si_ in s.stage_items
                for r in si_.rounds
                for m in r.matches
                if m.court_id is not None and m.start_time is not None
            ]

            response = await send_tournament_request(HTTPMethod.POST, _ENDPOINT, auth_context)

            stages_after = await get_full_tournament_details(tid)
            await sql_delete_stage_item_with_foreign_keys(si.id)
    finally:
        await database.execute(
            query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=False)
        )

    assert response == SUCCESS_RESPONSE

    scheduled_after = [
        m
        for s in stages_after
        for si_ in s.stage_items
        for r in si_.rounds
        for m in r.matches
        if m.court_id is not None and m.start_time is not None
    ]

    # Every scheduled match now has a referee
    assert len(scheduled_after) > 0
    assert all(m.referee_id is not None for m in scheduled_after)

    # Court and start_time are unchanged (schedule was not moved)
    scheduled_after_map = {m.id: (m.court_id, m.start_time) for m in scheduled_after}
    for match_id, court_id, start_time in scheduled_before:
        assert scheduled_after_map[match_id] == (court_id, start_time)


@pytest.mark.asyncio(loop_scope="session")
async def test_auto_assign_referees_preserves_existing_assignment(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A match that already has a referee keeps the same referee after the call."""
    tid = auth_context.tournament.id

    await database.execute(
        query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=True)
    )
    try:
        async with (
            inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
            inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t2,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t3,
        ):
            si = await _setup_round_robin_3teams(tid, stage.id, t1.id, t2.id, t3.id)
            await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)

            stages_before = await get_full_tournament_details(tid)
            scheduled_before = [
                m
                for s in stages_before
                for si_ in s.stage_items
                for r in si_.rounds
                for m in r.matches
                if m.court_id is not None and m.start_time is not None
            ]
            assert len(scheduled_before) > 0

            # Pre-assign t3 as referee on the first match
            first_match = scheduled_before[0]
            pre_ref = await sql_upsert_referee_by_team(tid, t3.id)
            await sql_set_match_referee(first_match.id, pre_ref.id)

            response = await send_tournament_request(HTTPMethod.POST, _ENDPOINT, auth_context)

            stages_after = await get_full_tournament_details(tid)
            await sql_delete_stage_item_with_foreign_keys(si.id)
    finally:
        await database.execute(
            query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=False)
        )

    assert response == SUCCESS_RESPONSE

    after_map = {
        m.id: m.referee_id
        for s in stages_after
        for si_ in s.stage_items
        for r in si_.rounds
        for m in r.matches
    }
    # The pre-assigned match still has the same referee
    assert after_map[first_match.id] == pre_ref.id


@pytest.mark.asyncio(loop_scope="session")
async def test_auto_assign_referees_disabled_returns_409(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Returns 409 when referees_enabled is False for the tournament."""
    # auth_context.tournament has referees_enabled=False by default
    response = await send_tournament_request(HTTPMethod.POST, _ENDPOINT, auth_context)
    assert response == {"detail": "Referees are not enabled for this tournament"}


@pytest.mark.asyncio(loop_scope="session")
async def test_auto_assign_referees_requires_auth(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Unauthenticated request is rejected."""
    response = await send_request(
        HTTPMethod.POST,
        f"tournaments/{auth_context.tournament.id}/{_ENDPOINT}",
    )
    assert response == {"detail": "Not authenticated"}
