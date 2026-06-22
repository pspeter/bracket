"""Integration tests for Swiss score-correction re-resolution (issue #154)."""

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.handle_stage_activation import (
    _resolve_round_1_for_swiss_stage_item,
)
from bracket.models.db.match import Match, MatchState
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_stage,
    inserted_team,
)


async def _build_swiss_stage(tournament_id, ranking_id, stage_inserted, t1, t2, t3, t4):
    """Create a 4-team Swiss stage item with 2 games per player."""
    stage_item_raw = await sql_create_stage_item_with_inputs(
        tournament_id,
        StageItemWithInputsCreate(
            stage_id=stage_inserted.id,
            type=StageType.SWISS,
            team_count=4,
            games_per_player=2,
            ranking_id=ranking_id,
            inputs=[
                StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
            ],
        ),
    )
    await build_matches_for_stage_item(stage_item_raw, tournament_id)
    return stage_item_raw


async def _complete_match(match: Match, round_id, auth_context: AuthContext) -> None:
    """Drive a match through IN_PROGRESS → COMPLETED with 0-0 scores."""
    resp = await send_tournament_request(
        HTTPMethod.PUT,
        f"matches/{match.id}",
        auth_context,
        json={
            "round_id": round_id,
            "state": MatchState.IN_PROGRESS.value,
            "stage_item_input1_score": 0,
            "stage_item_input2_score": 0,
        },
    )
    assert resp == SUCCESS_RESPONSE
    resp = await send_tournament_request(
        HTTPMethod.PUT,
        f"matches/{match.id}",
        auth_context,
        json={
            "round_id": round_id,
            "state": MatchState.COMPLETED.value,
            "stage_item_input1_score": 0,
            "stage_item_input2_score": 0,
        },
    )
    assert resp == SUCCESS_RESPONSE


async def _correct_match_score(
    match: Match, round_id, auth_context: AuthContext, score1: int, score2: int
) -> None:
    """Re-open a completed match, change the score, and re-complete it."""
    resp = await send_tournament_request(
        HTTPMethod.PUT,
        f"matches/{match.id}",
        auth_context,
        json={
            "round_id": round_id,
            "state": MatchState.IN_PROGRESS.value,
            "stage_item_input1_score": score1,
            "stage_item_input2_score": score2,
        },
    )
    assert resp == SUCCESS_RESPONSE
    resp = await send_tournament_request(
        HTTPMethod.PUT,
        f"matches/{match.id}",
        auth_context,
        json={
            "round_id": round_id,
            "state": MatchState.COMPLETED.value,
            "stage_item_input1_score": score1,
            "stage_item_input2_score": score2,
        },
    )
    assert resp == SUCCESS_RESPONSE


@pytest.mark.asyncio(loop_scope="session")
async def test_score_correction_re_resolves_not_started_round2(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Correcting a round-1 score re-resolves round 2 when it has not started (AC #2)."""
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id, "is_active": True})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        stage_item_raw = await _build_swiss_stage(
            tournament_id, auth_context.ranking.id, stage_inserted, t1, t2, t3, t4
        )
        stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
        assert len(stage_item.rounds) == 2

        await _resolve_round_1_for_swiss_stage_item(tournament_id, stage_item)

        stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
        round1 = sorted(stage_item.rounds, key=lambda r: r.id)[0]

        try:
            # Complete all round-1 matches with equal scores → auto-resolves round 2
            for match in round1.matches:
                await _complete_match(match, round1.id, auth_context)

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2.lifecycle_state == RoundLifecycleState.RESOLVED
            for match in round2.matches:
                assert match.stage_item_input1_id is not None
                assert match.stage_item_input2_id is not None

            # Correct round-1 first match score (creates an ELO imbalance)
            round1 = sorted(stage_item.rounds, key=lambda r: r.id)[0]
            await _correct_match_score(round1.matches[0], round1.id, auth_context, 5, 0)

            # Round 2 must still be RESOLVED with teams assigned after re-resolution
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2_after = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2_after.lifecycle_state == RoundLifecycleState.RESOLVED
            for match in round2_after.matches:
                assert match.stage_item_input1_id is not None, (
                    "re-resolution must preserve team assignments"
                )
                assert match.stage_item_input2_id is not None, (
                    "re-resolution must preserve team assignments"
                )

        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_score_correction_freezes_round2_when_in_progress(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Correcting a round-1 score leaves round 2 untouched when it is already in progress."""
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id, "is_active": True})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        stage_item_raw = await _build_swiss_stage(
            tournament_id, auth_context.ranking.id, stage_inserted, t1, t2, t3, t4
        )
        stage_item = await get_stage_item(tournament_id, stage_item_raw.id)

        await _resolve_round_1_for_swiss_stage_item(tournament_id, stage_item)

        stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
        round1 = sorted(stage_item.rounds, key=lambda r: r.id)[0]

        try:
            # Complete all round-1 matches → auto-resolves round 2
            for match in round1.matches:
                await _complete_match(match, round1.id, auth_context)

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2.lifecycle_state == RoundLifecycleState.RESOLVED

            # Start a round-2 match → makes round 2 "in progress" (locked per AC)
            r2_match = round2.matches[0]
            original_input1 = r2_match.stage_item_input1_id
            original_input2 = r2_match.stage_item_input2_id
            resp = await send_tournament_request(
                HTTPMethod.PUT,
                f"matches/{r2_match.id}",
                auth_context,
                json={
                    "round_id": round2.id,
                    "state": MatchState.IN_PROGRESS.value,
                    "stage_item_input1_score": 0,
                    "stage_item_input2_score": 0,
                },
            )
            assert resp == SUCCESS_RESPONSE

            # Correct round-1 first match score
            round1 = sorted(stage_item.rounds, key=lambda r: r.id)[0]
            await _correct_match_score(round1.matches[0], round1.id, auth_context, 5, 0)

            # Round 2 must remain unchanged: same teams, still in progress
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2_after = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            r2_match_after = next(m for m in round2_after.matches if m.id == r2_match.id)
            assert r2_match_after.stage_item_input1_id == original_input1, (
                "locked round must not be re-paired after score correction"
            )
            assert r2_match_after.stage_item_input2_id == original_input2, (
                "locked round must not be re-paired after score correction"
            )
            assert r2_match_after.state == MatchState.IN_PROGRESS

        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
