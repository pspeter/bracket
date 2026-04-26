import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
)
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_COURT2,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_court,
    inserted_stage,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_all_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_court(
            DUMMY_COURT1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_3,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_4,
    ):
        tournament_id = auth_context.tournament.id
        stage_item_1 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM1.name,
                team_count=DUMMY_STAGE_ITEM1.team_count,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(
                        slot=1,
                        team_id=team_inserted_1.id,
                    ),
                    StageItemInputCreateBodyFinal(
                        slot=2,
                        team_id=team_inserted_2.id,
                    ),
                    StageItemInputCreateBodyFinal(
                        slot=3,
                        team_id=team_inserted_3.id,
                    ),
                    StageItemInputCreateBodyFinal(
                        slot=4,
                        team_id=team_inserted_4.id,
                    ),
                ],
            ),
        )
        stage_item_2 = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM3.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM3.type,
                inputs=[
                    StageItemInputCreateBodyTentative(
                        slot=1,
                        winner_from_stage_item_id=stage_item_1.id,
                        winner_position=1,
                    ),
                    StageItemInputCreateBodyTentative(
                        slot=2,
                        winner_from_stage_item_id=stage_item_1.id,
                        winner_position=2,
                    ),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item_1, tournament_id)
        await build_matches_for_stage_item(stage_item_2, tournament_id)

        response = await send_tournament_request(
            HTTPMethod.POST,
            "schedule_matches",
            auth_context,
        )
        stages = await get_full_tournament_details(tournament_id)

        await sql_delete_stage_item_with_foreign_keys(stage_item_2.id)
        await sql_delete_stage_item_with_foreign_keys(stage_item_1.id)

    assert response == SUCCESS_RESPONSE

    stage_item = stages[0].stage_items[0]
    assert len(stage_item.rounds) == 3
    for round_ in stage_item.rounds:
        assert len(round_.matches) == 2


def _count_matches_per_court(stages: list) -> dict:
    counts: dict = {}
    for stage in stages:
        for stage_item in stage.stage_items:
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    if match.court_id is not None:
                        counts[match.court_id] = counts.get(match.court_id, 0) + 1
    return counts


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_distributes_evenly_across_courts_round_robin(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """4 stage items (1 match each), 2 courts: old algo piles 3 on C2; new round-robin gives 2/2."""
    tid = auth_context.tournament.id
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
        inserted_court(DUMMY_COURT2.model_copy(update={"tournament_id": tid})),
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tid})) as t2,
    ):
        stage_items = []
        for slot_name in ["Group A", "Group B", "Group C", "Group D"]:
            si = await sql_create_stage_item_with_inputs(
                tid,
                StageItemWithInputsCreate(
                    stage_id=stage.id,
                    name=slot_name,
                    team_count=2,
                    type=DUMMY_STAGE_ITEM1.type,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(si, tid)
            stage_items.append(si)

        await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)
        stages = await get_full_tournament_details(tid)

        for si in stage_items:
            await sql_delete_stage_item_with_foreign_keys(si.id)

    counts = _count_matches_per_court(stages)
    assert len(counts) == 2, "matches should be spread across both courts"
    values = list(counts.values())
    assert max(values) - min(values) <= 1


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_does_not_move_already_scheduled_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Calling schedule_matches twice: the second call must leave already-scheduled matches alone."""
    tid = auth_context.tournament.id
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t4,
    ):
        si = await sql_create_stage_item_with_inputs(
            tid,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Group A",
                team_count=4,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                ],
            ),
        )
        await build_matches_for_stage_item(si, tid)

        # First schedule: sets all matches
        await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)
        stages_after_first = await get_full_tournament_details(tid)

        # Record state of every scheduled match
        match_states_before = {
            match.id: (match.court_id, match.start_time, match.position_in_schedule)
            for stage_obj in stages_after_first
            for stage_item in stage_obj.stage_items
            for round_ in stage_item.rounds
            for match in round_.matches
            if match.start_time is not None
        }

        # Second schedule: should be a no-op for already-scheduled matches
        await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)
        stages_after_second = await get_full_tournament_details(tid)

        await sql_delete_stage_item_with_foreign_keys(si.id)

    match_states_after = {
        match.id: (match.court_id, match.start_time, match.position_in_schedule)
        for stage_obj in stages_after_second
        for stage_item in stage_obj.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.id in match_states_before
    }

    assert match_states_before == match_states_after


@pytest.mark.asyncio(loop_scope="session")
async def test_stage2_matches_start_after_all_stage1_matches_finish(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Stage 1 has 7 matches (C1=4, C2=3 after rebalancing); stage 2 has matches on both courts.
    The lighter court (C2) must still wait for the heavier court (C1) to finish before stage 2."""
    tid = auth_context.tournament.id
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
        inserted_court(DUMMY_COURT2.model_copy(update={"tournament_id": tid})),
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage_one,
        inserted_stage(DUMMY_STAGE2.model_copy(update={"tournament_id": tid})) as stage_two,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t4,
    ):
        # Stage 1: 6 matches + 1 match = 7 total → rebalances to C1=4, C2=3
        si_a = await sql_create_stage_item_with_inputs(
            tid,
            StageItemWithInputsCreate(
                stage_id=stage_one.id,
                name="Group A",
                team_count=4,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                ],
            ),
        )
        si_b = await sql_create_stage_item_with_inputs(
            tid,
            StageItemWithInputsCreate(
                stage_id=stage_one.id,
                name="Group B",
                team_count=2,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                ],
            ),
        )
        # Stage 2: matches on both courts (one item per court via round-robin)
        si_c = await sql_create_stage_item_with_inputs(
            tid,
            StageItemWithInputsCreate(
                stage_id=stage_two.id,
                name="Group C",
                team_count=2,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                ],
            ),
        )
        si_d = await sql_create_stage_item_with_inputs(
            tid,
            StageItemWithInputsCreate(
                stage_id=stage_two.id,
                name="Group D",
                team_count=2,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                ],
            ),
        )
        for si in [si_a, si_b, si_c, si_d]:
            await build_matches_for_stage_item(si, tid)

        await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)
        stages = await get_full_tournament_details(tid)

        for si in [si_d, si_c, si_b, si_a]:
            await sql_delete_stage_item_with_foreign_keys(si.id)

    s1 = next(s for s in stages if s.id == stage_one.id)
    s2 = next(s for s in stages if s.id == stage_two.id)

    stage1_end_times = [
        match.end_time
        for stage_item in s1.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.start_time is not None
    ]
    stage2_start_times = [
        match.start_time
        for stage_item in s2.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.start_time is not None
    ]

    assert stage1_end_times, "stage 1 should have scheduled matches"
    assert stage2_start_times, "stage 2 should have scheduled matches"
    max_stage1_end = max(stage1_end_times)
    for start_time in stage2_start_times:
        assert start_time >= max_stage1_end


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_rebalances_uneven_stage_item_sizes(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """3 stage items (6 matches each), 2 courts: round-robin gives 12/6; rebalancing gives 9/9."""
    tid = auth_context.tournament.id
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
        inserted_court(DUMMY_COURT2.model_copy(update={"tournament_id": tid})),
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t4,
    ):
        stage_items = []
        for slot_name in ["Group A", "Group B", "Group C"]:
            si = await sql_create_stage_item_with_inputs(
                tid,
                StageItemWithInputsCreate(
                    stage_id=stage.id,
                    name=slot_name,
                    team_count=4,
                    type=DUMMY_STAGE_ITEM1.type,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                        StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                        StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(si, tid)
            stage_items.append(si)

        await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)
        stages = await get_full_tournament_details(tid)

        for si in stage_items:
            await sql_delete_stage_item_with_foreign_keys(si.id)

    counts = _count_matches_per_court(stages)
    assert len(counts) == 2, "matches should be spread across both courts"
    values = list(counts.values())
    assert max(values) - min(values) <= 1


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_single_court_handles_more_stage_items_than_courts(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """3 stage items, 1 court: round-robin wraps and all matches land on the single court."""
    tid = auth_context.tournament.id
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t2,
    ):
        stage_items = []
        for slot_name in ["Group A", "Group B", "Group C"]:
            si = await sql_create_stage_item_with_inputs(
                tid,
                StageItemWithInputsCreate(
                    stage_id=stage.id,
                    name=slot_name,
                    team_count=2,
                    type=DUMMY_STAGE_ITEM1.type,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(si, tid)
            stage_items.append(si)

        await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)
        stages = await get_full_tournament_details(tid)

        for si in stage_items:
            await sql_delete_stage_item_with_foreign_keys(si.id)

    counts = _count_matches_per_court(stages)
    assert len(counts) == 1, "all matches should be on the single court"
    assert sum(counts.values()) == 3, "all 3 matches must be scheduled"
