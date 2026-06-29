"""Integration tests for match set transition verbs (issue #235)."""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import pytest

from bracket.database import database
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.handle_stage_activation import (
    _resolve_round_1_for_swiss_stage_item,
)
from bracket.models.db.match import MatchState
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputInsertable,
)
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages, tournaments
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_COURT1,
    DUMMY_MATCH1,
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
    DUMMY_TEAM4,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import send_request, send_tournament_request
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


@pytest.mark.asyncio(loop_scope="session")
async def test_start_puts_first_set_in_progress(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        set_id = match_inserted.match_sets[0].id
        response = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/start",
            auth_context,
        )
        assert response["data"]["state"] == "IN_PROGRESS"
        assert response["data"]["match_sets"][0]["state"] == "IN_PROGRESS"
        assert response["data"]["match_sets"][0]["id"] == set_id


@pytest.mark.asyncio(loop_scope="session")
async def test_start_rejected_when_set_already_in_progress(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/start", auth_context
        )
        response = await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/start", auth_context
        )
        assert response == {"detail": "Cannot start: a set is already in progress"}


@pytest.mark.asyncio(loop_scope="session")
async def test_start_rejected_when_all_sets_completed(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        set_id = match_inserted.match_sets[0].id
        await _complete_match(auth_context, match_inserted.id, set_id)
        response = await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/start", auth_context
        )
        assert response == {"detail": "Cannot start: all sets are already completed"}


@pytest.mark.asyncio(loop_scope="session")
async def test_end_without_start_is_rejected(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        response = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/end",
            auth_context,
        )
        assert response == {"detail": "Cannot end: no set is in progress"}


@pytest.mark.asyncio(loop_scope="session")
async def test_reopen_rejected_when_no_sets_completed(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        response = await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/reopen", auth_context
        )
        assert response == {"detail": "Cannot reopen: no completed sets"}


@pytest.mark.asyncio(loop_scope="session")
async def test_score_edit_and_end_complete_match(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        set_id = match_inserted.match_sets[0].id
        await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/start",
            auth_context,
        )
        await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/sets/{set_id}/score-edit",
            auth_context,
            json={"stage_item_input1_score": 21, "stage_item_input2_score": 10},
        )
        completed = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/end",
            auth_context,
        )
        assert completed["data"]["state"] == "COMPLETED"
        assert completed["data"]["completed_at"] is not None
        assert completed["data"]["match_sets"][0]["state"] == "COMPLETED"


@pytest.mark.asyncio(loop_scope="session")
async def test_reopen_clears_completed_at(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        set_id = match_inserted.match_sets[0].id
        await _complete_match(auth_context, match_inserted.id, set_id)
        reopened = await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/reopen", auth_context
        )
        assert reopened["data"]["state"] == "IN_PROGRESS"
        assert reopened["data"]["completed_at"] is None
        assert reopened["data"]["match_sets"][0]["state"] == "IN_PROGRESS"


@pytest.mark.asyncio(loop_scope="session")
async def test_score_edit_flips_elimination_winner_without_pointer_change(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM4.model_copy(update={"tournament_id": tournament_id})) as t4,
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage,
    ):
        stage_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Elimination",
                team_count=4,
                type=StageType.SINGLE_ELIMINATION,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item, tournament_id)

        try:
            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            semi = bracket.rounds[0].matches[0]
            semi_set_id = semi.match_sets[0].id
            winner_input_id = semi.stage_item_input1_id
            loser_input_id = semi.stage_item_input2_id
            assert winner_input_id is not None and loser_input_id is not None

            await _complete_match(
                auth_context, semi.id, semi_set_id, score1=21, score2=0
            )

            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            final = bracket.rounds[1].matches[0]
            assert final.stage_item_input1_id == winner_input_id

            flipped = await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{semi.id}/sets/{semi_set_id}/score-edit",
                auth_context,
                json={"stage_item_input1_score": 0, "stage_item_input2_score": 21},
            )
            assert flipped["data"]["state"] == "COMPLETED"
            assert flipped["data"]["match_sets"][0]["state"] == "COMPLETED"

            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            final = bracket.rounds[1].matches[0]
            assert final.stage_item_input1_id == loser_input_id
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_reset_unwires_elimination_bracket(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM4.model_copy(update={"tournament_id": tournament_id})) as t4,
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage,
    ):
        stage_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Elimination",
                team_count=4,
                type=StageType.SINGLE_ELIMINATION,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item, tournament_id)

        try:
            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            semi = bracket.rounds[0].matches[0]
            final = bracket.rounds[1].matches[0]
            semi_set_id = semi.match_sets[0].id

            await _complete_match(auth_context, semi.id, semi_set_id)

            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            assert bracket.rounds[1].matches[0].stage_item_input1_id is not None

            reset = await send_tournament_request(
                HTTPMethod.POST, f"matches/{semi.id}/reset", auth_context
            )
            assert reset["data"]["state"] == "NOT_STARTED"
            assert reset["data"]["completed_at"] is None
            assert reset["data"]["match_sets"][0]["stage_item_input1_score"] == 0

            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            final_reset = bracket.rounds[1].matches[0]
            assert final_reset.stage_item_input1_id is None
            assert final_reset.id == final.id
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_reset_clears_completed_elimination_follower(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM4.model_copy(update={"tournament_id": tournament_id})) as t4,
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage,
    ):
        stage_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Elimination",
                team_count=4,
                type=StageType.SINGLE_ELIMINATION,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item, tournament_id)

        try:
            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            semi1 = bracket.rounds[0].matches[0]
            semi2 = bracket.rounds[0].matches[1]
            final = bracket.rounds[1].matches[0]

            await _complete_match(auth_context, semi1.id, semi1.match_sets[0].id)
            await _complete_match(auth_context, semi2.id, semi2.match_sets[0].id)
            await _complete_match(auth_context, final.id, final.match_sets[0].id)

            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            final = bracket.rounds[1].matches[0]
            assert final.state == MatchState.COMPLETED
            assert final.completed_at is not None

            await send_tournament_request(
                HTTPMethod.POST, f"matches/{semi1.id}/reset", auth_context
            )

            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            final_reset = bracket.rounds[1].matches[0]
            assert final_reset.state == MatchState.NOT_STARTED
            assert final_reset.completed_at is None
            assert final_reset.stage_item_input1_id is None
            assert final_reset.match_sets[0].stage_item_input1_score == 0
            assert final_reset.match_sets[0].stage_item_input2_score == 0
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_start_rejected_when_opponents_are_unresolved(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM2.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM3.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM4.model_copy(update={"tournament_id": tournament_id})) as t4,
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage,
    ):
        stage_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Elimination",
                team_count=4,
                type=StageType.SINGLE_ELIMINATION,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item, tournament_id)

        try:
            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            final = bracket.rounds[1].matches[0]
            assert final.stage_item_input1_id is None

            response = await send_tournament_request(
                HTTPMethod.POST, f"matches/{final.id}/start", auth_context
            )
            assert response == {
                "detail": "Cannot start this match because its opponents are not determined yet."
            }
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_reset_unwires_deep_elimination_bracket(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage,
        AsyncExitStack() as stack,
    ):
        teams = [
            await stack.enter_async_context(
                inserted_team(
                    DUMMY_TEAM1.model_copy(
                        update={"tournament_id": tournament_id, "name": f"Team {i + 1}"}
                    )
                )
            )
            for i in range(8)
        ]
        stage_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Elimination",
                team_count=8,
                type=StageType.SINGLE_ELIMINATION,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=i + 1, team_id=team.id)
                    for i, team in enumerate(teams)
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item, tournament_id)

        try:
            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            quarter_final = bracket.rounds[0].matches[0]
            semi = next(
                m
                for r in bracket.rounds[1].matches
                for m in [r]
                if m.stage_item_input1_winner_from_match_id == quarter_final.id
                or m.stage_item_input2_winner_from_match_id == quarter_final.id
            )
            championship = bracket.rounds[2].matches[0]

            feeder_ids = {
                semi.stage_item_input1_winner_from_match_id,
                semi.stage_item_input2_winner_from_match_id,
            }
            for feeder in bracket.rounds[0].matches:
                if feeder.id in feeder_ids:
                    await _complete_match(
                        auth_context, feeder.id, feeder.match_sets[0].id
                    )
            await _complete_match(auth_context, semi.id, semi.match_sets[0].id)

            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            championship = bracket.rounds[2].matches[0]
            assert (
                championship.stage_item_input1_id is not None
                or championship.stage_item_input2_id is not None
            )

            await send_tournament_request(
                HTTPMethod.POST, f"matches/{quarter_final.id}/reset", auth_context
            )

            details = await get_full_tournament_details(tournament_id)
            bracket = next(
                si for s in details for si in s.stage_items if si.id == stage_item.id
            )
            semi_reset = next(
                m
                for r in bracket.rounds[1].matches
                for m in [r]
                if m.stage_item_input1_winner_from_match_id == quarter_final.id
                or m.stage_item_input2_winner_from_match_id == quarter_final.id
            )
            championship_reset = bracket.rounds[2].matches[0]
            if semi_reset.stage_item_input1_winner_from_match_id == quarter_final.id:
                assert semi_reset.stage_item_input1_id is None
            else:
                assert semi_reset.stage_item_input2_id is None
            assert championship_reset.stage_item_input1_id is None
            assert championship_reset.stage_item_input2_id is None
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_reset_unwires_swiss_round2_after_round1_match_reset(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Resetting a round-1 Swiss match re-runs downstream pairing for round 2."""
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        stage_item_raw = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted.id,
                type=StageType.SWISS,
                team_count=4,
                games_per_player=2,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                ],
            ),
        )
        await build_matches_for_stage_item(stage_item_raw, tournament_id)
        stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
        await _resolve_round_1_for_swiss_stage_item(tournament_id, stage_item)

        round1 = sorted(stage_item.rounds, key=lambda r: r.id)[0]
        round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]

        try:
            for i, match in enumerate(round1.matches):
                set_id = match.match_sets[0].id
                await _complete_match(
                    auth_context,
                    match.id,
                    set_id,
                    score1=21,
                    score2=i,
                )

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2_resolved = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2_resolved.lifecycle_state == RoundLifecycleState.RESOLVED
            r2_before = [
                (m.stage_item_input1_id, m.stage_item_input2_id)
                for m in round2_resolved.matches
            ]
            assert all(i1 is not None and i2 is not None for i1, i2 in r2_before)

            reset_match = round1.matches[0]
            reset_response = await send_tournament_request(
                HTTPMethod.POST, f"matches/{reset_match.id}/reset", auth_context
            )
            assert reset_response["data"]["state"] == "NOT_STARTED"

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2_after_reset = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2_after_reset.lifecycle_state == RoundLifecycleState.PLACEHOLDER
            assert all(
                m.stage_item_input1_id is None and m.stage_item_input2_id is None
                for m in round2_after_reset.matches
            )
            assert round2.id == round2_after_reset.id
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_score_tracking_token_verbs_start_and_end(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        _simple_match(auth_context) as match_inserted,
        _score_tracking_token(auth_context.tournament.id, "verb-token") as token,
    ):
        set_id = match_inserted.match_sets[0].id
        started = await send_request(
            HTTPMethod.POST, f"score-tracking/{token}/matches/{match_inserted.id}/start"
        )
        assert started["data"]["state"] == "IN_PROGRESS"

        await send_request(
            HTTPMethod.POST,
            f"score-tracking/{token}/matches/{match_inserted.id}/sets/{set_id}/score-edit",
            json={"stage_item_input1_score": 21, "stage_item_input2_score": 15},
        )
        completed = await send_request(
            HTTPMethod.POST, f"score-tracking/{token}/matches/{match_inserted.id}/end"
        )
        assert completed["data"]["state"] == "COMPLETED"
        assert completed["data"]["completed_at"] is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_score_tracking_token_reopen_works(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        _simple_match(auth_context) as match_inserted,
        _score_tracking_token(auth_context.tournament.id, "reopen-token") as token,
    ):
        set_id = match_inserted.match_sets[0].id
        await _complete_match(auth_context, match_inserted.id, set_id)
        reopened = await send_request(
            HTTPMethod.POST, f"score-tracking/{token}/matches/{match_inserted.id}/reopen"
        )
        assert reopened["data"]["state"] == "IN_PROGRESS"
        assert reopened["data"]["completed_at"] is None


@pytest.mark.asyncio(loop_scope="session")
async def test_reset_is_not_exposed_on_score_tracking_token_route(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        _simple_match(auth_context) as match_inserted,
        _score_tracking_token(auth_context.tournament.id, "no-reset-token") as token,
    ):
        response = await send_request(
            HTTPMethod.POST, f"score-tracking/{token}/matches/{match_inserted.id}/reset"
        )
        assert response == {"detail": "Not Found"}


async def _complete_match(
    auth_context: AuthContext,
    match_id: int,
    set_id: int,
    *,
    score1: int = 21,
    score2: int = 0,
) -> None:
    await send_tournament_request(HTTPMethod.POST, f"matches/{match_id}/start", auth_context)
    await send_tournament_request(
        HTTPMethod.POST,
        f"matches/{match_id}/sets/{set_id}/score-edit",
        auth_context,
        json={"stage_item_input1_score": score1, "stage_item_input2_score": score2},
    )
    await send_tournament_request(HTTPMethod.POST, f"matches/{match_id}/end", auth_context)


@asynccontextmanager
async def _score_tracking_token(tournament_id: int, token: str) -> AsyncIterator[str]:
    await database.execute(
        query=tournaments.update()
        .where(tournaments.c.id == tournament_id)
        .values(score_tracking_enabled=True, score_tracking_token=token),
    )
    try:
        yield token
    finally:
        await database.execute(
            query=tournaments.update()
            .where(tournaments.c.id == tournament_id)
            .values(score_tracking_enabled=False, score_tracking_token=None),
        )


@asynccontextmanager
async def _simple_match(auth_context: AuthContext) -> AsyncIterator:
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
        yield match_inserted
