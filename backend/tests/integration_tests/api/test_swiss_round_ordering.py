"""Regression tests for two Swiss planning bugs that share a single root cause: the
`array_agg(...)` calls in ``get_full_tournament_details`` had no ``ORDER BY``, so Postgres
returned rounds and matches in physical heap order instead of id order.

After tuples are deleted and their heap slots reused (which autovacuum does routinely once a
tournament has been rescheduled / rebuilt a few times), that heap order diverges from id order:

1. The planning page renders rounds/matches in the order the API returns them, so they would
   suddenly flip into a scrambled (e.g. reversed) order on a background refetch.
2. ``_resolve_round_1_for_swiss_stage_item`` resolved whichever placeholder round happened to be
   first in that order rather than round 1, leaving the real round 1 a placeholder that shows TBD.
"""

import pytest
from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.scheduling.handle_stage_activation import (
    _resolve_round_1_for_swiss_stage_item,
)
from bracket.models.db.match import Match, MatchInsertable
from bracket.models.db.round import RoundInsertable, RoundLifecycleState
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.rounds import sql_create_round
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.db import insert_generic
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_stage,
    inserted_team,
)


async def _get_swiss_stage_item(tournament_id, stage_id):  # type: ignore[no-untyped-def]
    stages_in_tournament = await get_full_tournament_details(tournament_id)
    return next(
        si for stage in stages_in_tournament if stage.id == stage_id for si in stage.stage_items
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_rounds_and_matches_returned_in_id_order_after_heap_reuse(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """get_full_tournament_details must return rounds (and matches within a round) sorted by id,
    even after deleted heap slots have been reused so heap order no longer matches id order."""
    tournament_id = auth_context.tournament.id

    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id, "is_active": False})
    ) as stage_inserted:
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "stage_items",
                auth_context,
                json={
                    "type": StageType.SWISS.value,
                    "team_count": 4,
                    "stage_id": stage_inserted.id,
                    "games_per_player": 3,
                },
            )
            == SUCCESS_RESPONSE
        )

        try:
            stage_item = await _get_swiss_stage_item(tournament_id, stage_inserted.id)
            rounds_sorted = sorted(stage_item.rounds, key=lambda round_: round_.id)
            assert len(rounds_sorted) == 3

            # Scramble the heap order of rounds: drop the lowest-id round, free its slot with a
            # VACUUM, then create a fresh round that reuses that slot. The new round has the
            # highest id but an earlier physical position than the surviving rounds.
            first_round = rounds_sorted[0]
            await database.execute(matches.delete().where(matches.c.round_id == first_round.id))
            await database.execute(rounds.delete().where(rounds.c.id == first_round.id))
            await database.execute("VACUUM rounds")
            new_round_id = await sql_create_round(
                RoundInsertable(
                    created=datetime_utc.now(),
                    stage_item_id=stage_item.id,
                    name="Round 99",
                    lifecycle_state=RoundLifecycleState.PLACEHOLDER,
                    is_pinned=False,
                )
            )

            # Scramble the heap order of matches: delete every other match across the surviving
            # rounds, free those slots with a VACUUM, then reinsert fresh (higher-id) matches that
            # land in the freed slots. Their physical order now diverges from id order, so an
            # unordered array_agg returns them scrambled (e.g. {18,17,9,11}).
            target_rounds = [rounds_sorted[1].id, rounds_sorted[2].id, new_round_id]
            existing_match_ids = sorted(
                match.id for round_ in rounds_sorted[1:] for match in round_.matches
            )
            await database.execute(
                matches.delete().where(matches.c.id.in_(existing_match_ids[::2]))
            )
            await database.execute("VACUUM matches")
            for round_id in target_rounds:
                for _ in range(2):
                    await insert_generic(
                        database,
                        MatchInsertable(
                            created=datetime_utc.now(),
                            round_id=round_id,
                            duration_minutes=10,
                            stage_item_input1_score=0,
                            stage_item_input2_score=0,
                        ),
                        matches,
                        Match,
                    )

            stage_item = await _get_swiss_stage_item(tournament_id, stage_inserted.id)

            round_ids = [round_.id for round_ in stage_item.rounds]
            assert round_ids == sorted(round_ids), (
                f"Rounds were not returned in id order: {round_ids}"
            )
            for round_ in stage_item.rounds:
                match_ids = [match.id for match in round_.matches]
                assert match_ids == sorted(match_ids), (
                    f"Matches in round {round_.id} were not returned in id order: {match_ids}"
                )
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_inactive_stage_resolves_round_1_when_all_slots_filled(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Round 1 of a Swiss stage item resolves as soon as all of its slots are filled — it does
    not wait for the stage to be activated. So a resolved round 1 shows its real matchups instead
    of TBD even in a not-yet-activated stage."""
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id, "is_active": False})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "stage_items",
                auth_context,
                json={
                    "type": StageType.SWISS.value,
                    "team_count": 4,
                    "stage_id": stage_inserted.id,
                    "games_per_player": 3,
                },
            )
            == SUCCESS_RESPONSE
        )

        try:
            stage_item = await _get_swiss_stage_item(tournament_id, stage_inserted.id)
            inputs_sorted = sorted(stage_item.inputs, key=lambda input_: input_.slot)
            teams = [t1, t2, t3, t4]

            # While a slot is still empty, round 1 stays a placeholder.
            for input_, team in zip(inputs_sorted[:-1], teams[:-1]):
                assert (
                    await send_tournament_request(
                        HTTPMethod.PUT,
                        f"stage_items/{stage_item.id}/inputs/{input_.id}",
                        auth_context,
                        json={"team_id": team.id},
                    )
                    == SUCCESS_RESPONSE
                )

            stage_item = await _get_swiss_stage_item(tournament_id, stage_inserted.id)
            first_round = min(stage_item.rounds, key=lambda round_: round_.id)
            assert first_round.lifecycle_state == RoundLifecycleState.PLACEHOLDER

            # Filling the last slot resolves round 1 — even though the stage is still inactive.
            assert (
                await send_tournament_request(
                    HTTPMethod.PUT,
                    f"stage_items/{stage_item.id}/inputs/{inputs_sorted[-1].id}",
                    auth_context,
                    json={"team_id": teams[-1].id},
                )
                == SUCCESS_RESPONSE
            )

            stage_item = await _get_swiss_stage_item(tournament_id, stage_inserted.id)
            rounds_sorted = sorted(stage_item.rounds, key=lambda round_: round_.id)

            # The real round 1 (lowest id) is resolved with concrete inputs; later rounds wait.
            assert rounds_sorted[0].lifecycle_state == RoundLifecycleState.RESOLVED
            for match in rounds_sorted[0].matches:
                assert match.stage_item_input1_id is not None
                assert match.stage_item_input2_id is not None
            for round_ in rounds_sorted[1:]:
                assert round_.lifecycle_state == RoundLifecycleState.PLACEHOLDER
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_resolve_round_1_targets_lowest_id_round_regardless_of_order(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Resolving round 1 must resolve the lowest-id round (the real round 1), even when the
    stage item's rounds are handed over in a different order — as the non-deterministic SQL
    ordering used to do. Otherwise a later round gets resolved and round 1 stays a placeholder
    that displays TBD."""
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id, "is_active": False})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "stage_items",
                auth_context,
                json={
                    "type": StageType.SWISS.value,
                    "team_count": 4,
                    "stage_id": stage_inserted.id,
                    "games_per_player": 3,
                },
            )
            == SUCCESS_RESPONSE
        )

        try:
            stage_item = await _get_swiss_stage_item(tournament_id, stage_inserted.id)
            inputs_sorted = sorted(stage_item.inputs, key=lambda input_: input_.slot)

            # Assign every team directly in SQL so the route's auto-resolve does not fire: this
            # leaves every round a placeholder with concrete (Final) inputs, which is the state in
            # which round-1 resolution then has to pick the right round.
            for input_, team in zip(inputs_sorted, [t1, t2, t3, t4]):
                await database.execute(
                    stage_item_inputs.update()
                    .where(stage_item_inputs.c.id == input_.id)
                    .values(team_id=team.id)
                )

            stage_item = await _get_swiss_stage_item(tournament_id, stage_inserted.id)
            assert all(isinstance(input_, StageItemInputFinal) for input_ in stage_item.inputs)
            assert all(
                round_.lifecycle_state == RoundLifecycleState.PLACEHOLDER
                for round_ in stage_item.rounds
            )
            assert len(stage_item.rounds) >= 2

            # Mimic the scrambled order the buggy SQL returned: hand the rounds over reversed,
            # so the first placeholder in iteration order is NOT round 1.
            scrambled = stage_item.model_copy(update={"rounds": list(reversed(stage_item.rounds))})
            await _resolve_round_1_for_swiss_stage_item(tournament_id, scrambled)

            stage_item = await _get_swiss_stage_item(tournament_id, stage_inserted.id)
            rounds_sorted = sorted(stage_item.rounds, key=lambda round_: round_.id)

            # The real round 1 (lowest id) is the one that gets resolved, with concrete inputs.
            assert rounds_sorted[0].lifecycle_state == RoundLifecycleState.RESOLVED
            for match in rounds_sorted[0].matches:
                assert match.stage_item_input1_id is not None
                assert match.stage_item_input2_id is not None
            for round_ in rounds_sorted[1:]:
                assert round_.lifecycle_state == RoundLifecycleState.PLACEHOLDER
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
