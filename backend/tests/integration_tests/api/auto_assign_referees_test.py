import pytest

from bracket.database import database
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItem, StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
)
from bracket.schema import stage_item_inputs, teams, tournaments
from bracket.sql.referees import sql_set_match_referee_slot
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
)
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
    assert all(m.referee_stage_item_input_id is not None for m in scheduled_after)

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

            # Pre-assign t3's slot as referee on the first match
            first_match = scheduled_before[0]
            t3_slot_id = await database.fetch_val(
                query=stage_item_inputs.select().where(stage_item_inputs.c.team_id == t3.id),
                column="id",
            )
            await sql_set_match_referee_slot(first_match.id, t3_slot_id)

            response = await send_tournament_request(HTTPMethod.POST, _ENDPOINT, auth_context)

            stages_after = await get_full_tournament_details(tid)
            await sql_delete_stage_item_with_foreign_keys(si.id)
    finally:
        await database.execute(
            query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=False)
        )

    assert response == SUCCESS_RESPONSE

    after_map = {
        m.id: m.referee_stage_item_input_id
        for s in stages_after
        for si_ in s.stage_items
        for r in si_.rounds
        for m in r.matches
    }
    # The pre-assigned match still has the same referee slot
    assert after_map[first_match.id] == t3_slot_id


@pytest.mark.asyncio(loop_scope="session")
async def test_auto_assign_referees_assigns_placeholder_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Matches whose opponents are still placeholders also get a referee slot (#125).

    A later stage's matches reference the previous stage's results via tentative inputs. The
    referee is now a slot, so the optimizer assigns one regardless of whether the opponents
    are known yet — both the concrete first-stage matches and the placeholder matches get one.

    Crucially, each referee slot comes from the match's *own stage*: a later stage's slot (e.g.
    "1st of the group stage") must never referee an earlier match, since that participant is
    unknown until the earlier stage is played.
    """
    tid = auth_context.tournament.id

    await database.execute(
        query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=True)
    )
    try:
        async with (
            inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
            inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage_one,
            inserted_stage(DUMMY_STAGE2.model_copy(update={"tournament_id": tid})) as stage_two,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t2,
            inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t3,
        ):
            si_first = await _setup_round_robin_3teams(tid, stage_one.id, t1.id, t2.id, t3.id)
            # Second-stage item whose opponents are all placeholders from the first stage. It has
            # three slots so that, in each of its matches, a slot from its own stage is free to
            # referee (the only eligible candidates after the same-stage restriction).
            si_placeholder = await sql_create_stage_item_with_inputs(
                tid,
                StageItemWithInputsCreate(
                    stage_id=stage_two.id,
                    name="Finals",
                    team_count=3,
                    type=DUMMY_STAGE_ITEM1.type,
                    inputs=[
                        StageItemInputCreateBodyTentative(
                            slot=1, winner_from_stage_item_id=si_first.id, winner_position=1
                        ),
                        StageItemInputCreateBodyTentative(
                            slot=2, winner_from_stage_item_id=si_first.id, winner_position=2
                        ),
                        StageItemInputCreateBodyTentative(
                            slot=3, winner_from_stage_item_id=si_first.id, winner_position=3
                        ),
                    ],
                ),
            )
            await build_matches_for_stage_item(si_placeholder, tid)
            await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)

            response = await send_tournament_request(HTTPMethod.POST, _ENDPOINT, auth_context)

            stages_after = await get_full_tournament_details(tid)
            await sql_delete_stage_item_with_foreign_keys(si_placeholder.id)
            await sql_delete_stage_item_with_foreign_keys(si_first.id)
    finally:
        await database.execute(
            query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=False)
        )

    assert response == SUCCESS_RESPONSE

    first_stage_matches = [
        m
        for s in stages_after
        if s.id == stage_one.id
        for si_ in s.stage_items
        for r in si_.rounds
        for m in r.matches
        if m.court_id is not None and m.start_time is not None
    ]
    placeholder_matches = [
        m
        for s in stages_after
        if s.id == stage_two.id
        for si_ in s.stage_items
        for r in si_.rounds
        for m in r.matches
    ]

    # The stage-item input slots that belong to each stage.
    slots_by_stage = {
        s.id: {inp.id for si_ in s.stage_items for inp in si_.inputs} for s in stages_after
    }

    # First-stage (concrete) matches get referees, all from the first stage's own slots.
    assert len(first_stage_matches) > 0
    assert all(m.referee_stage_item_input_id is not None for m in first_stage_matches)
    assert all(
        m.referee_stage_item_input_id in slots_by_stage[stage_one.id] for m in first_stage_matches
    )

    # Placeholder matches now also get a referee slot (no more deferral), and that slot comes
    # from the placeholder stage itself — never a slot from a different stage.
    assert len(placeholder_matches) > 0
    assert all(m.referee_stage_item_input_id is not None for m in placeholder_matches)
    assert all(
        m.referee_stage_item_input_id in slots_by_stage[stage_two.id] for m in placeholder_matches
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_auto_assign_referees_excludes_inactive_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """An inactive team is never picked as referee, even when it's the only same-stage
    candidate for a match (issue #282): that match is left unassigned rather than handed to it.
    """
    tid = auth_context.tournament.id

    # Schedule with referees disabled so "schedule_matches" itself assigns none (it would
    # otherwise assign referees too, before this test gets a chance to deactivate t3), then
    # enable referees and deactivate t3 so only the standalone auto-assign endpoint is exercised.
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t3,
    ):
        si = await _setup_round_robin_3teams(tid, stage.id, t1.id, t2.id, t3.id)
        await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)

        await database.execute(query=teams.update().where(teams.c.id == t3.id).values(active=False))
        await database.execute(
            query=tournaments.update().where(tournaments.c.id == tid).values(referees_enabled=True)
        )
        try:
            t3_slot_id = await database.fetch_val(
                query=stage_item_inputs.select().where(stage_item_inputs.c.team_id == t3.id),
                column="id",
            )

            response = await send_tournament_request(HTTPMethod.POST, _ENDPOINT, auth_context)

            stages_after = await get_full_tournament_details(tid)
            await sql_delete_stage_item_with_foreign_keys(si.id)
        finally:
            await database.execute(
                query=tournaments.update()
                .where(tournaments.c.id == tid)
                .values(referees_enabled=False)
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
    assert len(scheduled_after) == 3

    # t3's slot is never assigned as referee anywhere.
    assert all(m.referee_stage_item_input_id != t3_slot_id for m in scheduled_after)

    # The T1-vs-T2 match's only same-stage candidate is t3 (inactive), so it's left unassigned;
    # the other two matches each have an active third team available and get one.
    t1_vs_t2 = next(
        m
        for m in scheduled_after
        if {m.stage_item_input1.team_id, m.stage_item_input2.team_id} == {t1.id, t2.id}  # type: ignore[union-attr]
    )
    others = [m for m in scheduled_after if m.id != t1_vs_t2.id]
    assert t1_vs_t2.referee_stage_item_input_id is None
    assert len(others) == 2
    assert all(m.referee_stage_item_input_id is not None for m in others)


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
