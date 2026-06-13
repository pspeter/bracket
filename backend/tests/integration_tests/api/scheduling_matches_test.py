from datetime import timedelta

import pytest

from bracket.database import database
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.match import MatchState, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.stage_item import StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
)
from bracket.models.db.util import StageWithStageItems
from bracket.sql.matches import sql_reschedule_match_and_determine_duration
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
from bracket.utils.id_types import MatchId
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


ScheduledMatch = MatchWithDetails | MatchWithDetailsDefinitive


def _all_matches(stages: list[StageWithStageItems]) -> list[ScheduledMatch]:
    return [
        match
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
    ]


def _scheduled_matches(stages: list[StageWithStageItems]) -> list[ScheduledMatch]:
    return [
        match
        for match in _all_matches(stages)
        if match.court_id is not None and match.start_time is not None
    ]


def _count_matches_per_court(stages: list[StageWithStageItems]) -> dict[object, int]:
    counts: dict[object, int] = {}
    for match in _scheduled_matches(stages):
        counts[match.court_id] = counts.get(match.court_id, 0) + 1
    return counts


def _assert_no_new_match_overlaps_pins(
    stages: list[StageWithStageItems], pinned_match_ids: set[MatchId], default_break_minutes: int
) -> None:
    scheduled = _scheduled_matches(stages)
    pinned = [match for match in scheduled if match.id in pinned_match_ids]
    new_matches = [match for match in scheduled if match.id not in pinned_match_ids]
    for new_match in new_matches:
        assert new_match.start_time is not None
        for pinned_match in pinned:
            assert pinned_match.start_time is not None
            if new_match.court_id == pinned_match.court_id:
                assert new_match.start_time >= pinned_match.end_time + timedelta(
                    minutes=default_break_minutes
                )


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
    """Calling schedule_matches twice: the second call leaves already-scheduled matches alone."""
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
            match.id: (match.court_id, match.start_time)
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
        match.id: (match.court_id, match.start_time)
        for stage_obj in stages_after_second
        for stage_item in stage_obj.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.id in match_states_before
    }

    assert match_states_before == match_states_after


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_succeeds_with_conflicting_pinned_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Pre-existing pinned conflicts stay flagged; new placements avoid those slots."""
    tid = auth_context.tournament.id
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})) as court,
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
        stages_before = await get_full_tournament_details(tid)
        pinned1, pinned2 = _all_matches(stages_before)[:2]
        await sql_reschedule_match_and_determine_duration(
            court.id, auth_context.tournament.start_time, pinned1, auth_context.tournament
        )
        await sql_reschedule_match_and_determine_duration(
            court.id, auth_context.tournament.start_time, pinned2, auth_context.tournament
        )
        pinned_match_ids = {pinned1.id, pinned2.id}

        response = await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)
        stages_after = await get_full_tournament_details(tid)

        await sql_delete_stage_item_with_foreign_keys(si.id)

    assert response == SUCCESS_RESPONSE
    matches_after = {match.id: match for match in _scheduled_matches(stages_after)}
    assert matches_after[pinned1.id].court_id == court.id
    assert matches_after[pinned1.id].start_time == auth_context.tournament.start_time
    assert matches_after[pinned2.id].court_id == court.id
    assert matches_after[pinned2.id].start_time == auth_context.tournament.start_time
    assert any(matches_after[match_id].short_break_conflict for match_id in pinned_match_ids)
    _assert_no_new_match_overlaps_pins(
        stages_after, pinned_match_ids, auth_context.tournament.margin_minutes
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_cross_stage_matches_start_after_their_source_stage_item_finishes(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """The endpoint respects tentative inputs from previous stage items plus the default break."""
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
        si_c = await sql_create_stage_item_with_inputs(
            tid,
            StageItemWithInputsCreate(
                stage_id=stage_two.id,
                name="Group C",
                team_count=2,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyTentative(
                        slot=1, winner_from_stage_item_id=si_a.id, winner_position=1
                    ),
                    StageItemInputCreateBodyTentative(
                        slot=2, winner_from_stage_item_id=si_a.id, winner_position=2
                    ),
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
                    StageItemInputCreateBodyTentative(
                        slot=1, winner_from_stage_item_id=si_b.id, winner_position=1
                    ),
                    StageItemInputCreateBodyTentative(
                        slot=2, winner_from_stage_item_id=si_b.id, winner_position=2
                    ),
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

    source_end_times = {
        stage_item.id: max(
            match.end_time
            for round_ in stage_item.rounds
            for match in round_.matches
            if match.start_time is not None
        )
        for stage_item in s1.stage_items
    }

    for stage_item in s2.stage_items:
        for round_ in stage_item.rounds:
            for match in round_.matches:
                assert match.start_time is not None
                for input_ in (match.stage_item_input1, match.stage_item_input2):
                    assert input_ is not None
                    if input_.winner_from_stage_item_id is None:
                        continue
                    assert match.start_time >= source_end_times[
                        input_.winner_from_stage_item_id
                    ] + timedelta(minutes=auth_context.tournament.margin_minutes)


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


def _assert_courts_have_no_overlaps(
    stages: list[StageWithStageItems], default_break_minutes: int
) -> None:
    by_court: dict[object, list[ScheduledMatch]] = {}
    for match in _scheduled_matches(stages):
        by_court.setdefault(match.court_id, []).append(match)
    for court_matches in by_court.values():
        ordered = sorted(
            court_matches,
            key=lambda m: m.start_time,  # type: ignore[arg-type, return-value]
        )
        for previous, current in zip(ordered, ordered[1:], strict=False):
            assert current.start_time is not None
            assert current.start_time >= previous.end_time + timedelta(
                minutes=default_break_minutes
            )


@pytest.mark.asyncio(loop_scope="session")
async def test_reoptimize_keeps_started_matches_fixed_and_reflows_the_rest(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Re-optimize never moves an in-progress/completed match but re-flows not-started ones."""
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

        # Schedule everything first, then freeze the earliest match as in-progress and the
        # next one as completed, so re-optimize has both kinds of pin to flow around.
        await send_tournament_request(HTTPMethod.POST, "schedule_matches", auth_context)
        stages_before = await get_full_tournament_details(tid)
        scheduled_before = sorted(
            _scheduled_matches(stages_before),
            key=lambda m: (m.start_time, m.court_id),
        )
        in_progress, completed = scheduled_before[0], scheduled_before[1]
        await database.execute(
            "UPDATE matches SET state = :state WHERE id = :match_id",
            {"state": MatchState.IN_PROGRESS.value, "match_id": in_progress.id},
        )
        await database.execute(
            "UPDATE matches SET state = :state WHERE id = :match_id",
            {"state": MatchState.COMPLETED.value, "match_id": completed.id},
        )
        frozen = {
            in_progress.id: (in_progress.court_id, in_progress.start_time),
            completed.id: (completed.court_id, completed.start_time),
        }

        response = await send_tournament_request(
            HTTPMethod.POST, "reoptimize_matches", auth_context
        )
        stages_after = await get_full_tournament_details(tid)

        await sql_delete_stage_item_with_foreign_keys(si.id)

    assert response == SUCCESS_RESPONSE
    matches_after = {match.id: match for match in _scheduled_matches(stages_after)}
    # Started matches are untouched.
    for match_id, slot in frozen.items():
        assert (matches_after[match_id].court_id, matches_after[match_id].start_time) == slot
    # Every match is still scheduled — re-optimize re-flows, it does not drop matches.
    assert set(matches_after) == {match.id for match in _all_matches(stages_after)}
    # The re-flowed schedule is conflict-free on every court.
    _assert_courts_have_no_overlaps(stages_after, auth_context.tournament.margin_minutes)


@pytest.mark.parametrize("endpoint", ["schedule_matches", "reoptimize_matches"])
@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_endpoints_accept_custom_weights_body(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext, endpoint: str
) -> None:
    """Both scheduling endpoints take an optional objective-weights body and validate it.

    A valid weights body schedules the matches as usual; a body with a negative weight is
    rejected by validation rather than silently ignored.
    """
    tid = auth_context.tournament.id
    async with (
        inserted_court(DUMMY_COURT1.model_copy(update={"tournament_id": tid})),
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tid})) as stage,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tid})) as t1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tid})) as t2,
    ):
        si = await sql_create_stage_item_with_inputs(
            tid,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Group A",
                team_count=2,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                ],
            ),
        )
        await build_matches_for_stage_item(si, tid)

        valid_weights = {
            "makespan": 200,
            "team_rest": 5,
            "group_sync": 2,
            "court_locality": 1,
            "comfortable_rest_minutes": 45,
        }
        valid_response = await send_tournament_request(
            HTTPMethod.POST, endpoint, auth_context, json=valid_weights
        )
        invalid_response = await send_tournament_request(
            HTTPMethod.POST, endpoint, auth_context, json={"makespan": -1}
        )
        stages = await get_full_tournament_details(tid)

        await sql_delete_stage_item_with_foreign_keys(si.id)

    assert valid_response == SUCCESS_RESPONSE
    assert len(_scheduled_matches(stages)) > 0
    assert "detail" in invalid_response
