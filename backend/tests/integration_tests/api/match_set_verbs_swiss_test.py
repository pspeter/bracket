"""Integration tests for the Swiss downstream cascade of match transition verbs (issue #235)."""

from collections.abc import Sequence

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
from bracket.sql.rounds import sql_set_round_is_pinned
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from bracket.utils.id_types import StageId, StageItemId, TeamId, TournamentId
from tests.integration_tests.api.match_set_verbs_test import _complete_match
from tests.integration_tests.api.shared import send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_stage,
    inserted_team,
)


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
                (m.stage_item_input1_id, m.stage_item_input2_id) for m in round2_resolved.matches
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


async def _build_swiss_stage_item_with_completed_round1(
    tournament_id: TournamentId,
    auth_context: AuthContext,
    stage_id: StageId,
    t1: TeamId,
    t2: TeamId,
    t3: TeamId,
    t4: TeamId,
) -> tuple[StageItemId, Sequence[Match]]:
    """Build a 4-team, 2-round Swiss stage; resolve and complete round 1.

    Returns (stage_item_id, round1_matches) with round 2 auto-resolved (RESOLVED).
    """
    stage_item_raw = await sql_create_stage_item_with_inputs(
        tournament_id,
        StageItemWithInputsCreate(
            stage_id=stage_id,
            type=StageType.SWISS,
            team_count=4,
            games_per_player=2,
            ranking_id=auth_context.ranking.id,
            inputs=[
                StageItemInputCreateBodyFinal(slot=1, team_id=t1),
                StageItemInputCreateBodyFinal(slot=2, team_id=t2),
                StageItemInputCreateBodyFinal(slot=3, team_id=t3),
                StageItemInputCreateBodyFinal(slot=4, team_id=t4),
            ],
        ),
    )
    await build_matches_for_stage_item(stage_item_raw, tournament_id)
    stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
    await _resolve_round_1_for_swiss_stage_item(tournament_id, stage_item)

    round1 = sorted(stage_item.rounds, key=lambda r: r.id)[0]
    for i, match in enumerate(round1.matches):
        set_id = match.match_sets[0].id
        await _complete_match(auth_context, match.id, set_id, score1=21, score2=i)

    return stage_item_raw.id, round1.matches


@pytest.mark.asyncio(loop_scope="session")
async def test_reset_rejected_when_swiss_round2_has_started(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Resetting a round-1 Swiss match is rejected once a round-2 match has started."""
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
        try:
            stage_item_id, round1_matches = await _build_swiss_stage_item_with_completed_round1(
                tournament_id, auth_context, stage_inserted.id, t1.id, t2.id, t3.id, t4.id
            )

            stage_item = await get_stage_item(tournament_id, stage_item_id)
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2.lifecycle_state == RoundLifecycleState.RESOLVED

            round2_match = round2.matches[0]
            started = await send_tournament_request(
                HTTPMethod.POST, f"matches/{round2_match.id}/start", auth_context
            )
            assert started["data"]["state"] == "IN_PROGRESS"

            stage_item = await get_stage_item(tournament_id, stage_item_id)
            round2_before = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            r2_before = [
                (m.stage_item_input1_id, m.stage_item_input2_id) for m in round2_before.matches
            ]

            reset_match = round1_matches[0]
            rejected = await send_tournament_request(
                HTTPMethod.POST, f"matches/{reset_match.id}/reset", auth_context
            )
            assert "reset the downstream" in rejected["detail"].lower()

            stage_item = await get_stage_item(tournament_id, stage_item_id)
            round1_after = sorted(stage_item.rounds, key=lambda r: r.id)[0]
            round2_after = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round1_after.matches[0].state == MatchState.COMPLETED
            assert round2_after.lifecycle_state == RoundLifecycleState.RESOLVED
            r2_after = [
                (m.stage_item_input1_id, m.stage_item_input2_id) for m in round2_after.matches
            ]
            assert r2_after == r2_before
            started_match_after = next(m for m in round2_after.matches if m.id == round2_match.id)
            assert started_match_after.state == MatchState.IN_PROGRESS
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_reopen_leaves_started_swiss_round2_untouched(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Reopening a completed round-1 Swiss match must not unwire a started round 2."""
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
        try:
            stage_item_id, round1_matches = await _build_swiss_stage_item_with_completed_round1(
                tournament_id, auth_context, stage_inserted.id, t1.id, t2.id, t3.id, t4.id
            )

            stage_item = await get_stage_item(tournament_id, stage_item_id)
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2.lifecycle_state == RoundLifecycleState.RESOLVED

            round2_match = round2.matches[0]
            started = await send_tournament_request(
                HTTPMethod.POST, f"matches/{round2_match.id}/start", auth_context
            )
            assert started["data"]["state"] == "IN_PROGRESS"

            stage_item = await get_stage_item(tournament_id, stage_item_id)
            round2_before = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            r2_before = [
                (m.stage_item_input1_id, m.stage_item_input2_id) for m in round2_before.matches
            ]

            reopen_match = round1_matches[0]
            reopened = await send_tournament_request(
                HTTPMethod.POST, f"matches/{reopen_match.id}/reopen", auth_context
            )
            assert reopened["data"]["state"] == "IN_PROGRESS"

            stage_item = await get_stage_item(tournament_id, stage_item_id)
            round2_after = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2_after.lifecycle_state == RoundLifecycleState.RESOLVED
            r2_after = [
                (m.stage_item_input1_id, m.stage_item_input2_id) for m in round2_after.matches
            ]
            assert r2_after == r2_before
            started_match_after = next(m for m in round2_after.matches if m.id == round2_match.id)
            assert started_match_after.state == MatchState.IN_PROGRESS
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_reset_does_not_unwire_pinned_swiss_round2(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A pinned RESOLVED round is not unwired when its predecessor becomes incomplete."""
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
        try:
            stage_item_id, round1_matches = await _build_swiss_stage_item_with_completed_round1(
                tournament_id, auth_context, stage_inserted.id, t1.id, t2.id, t3.id, t4.id
            )

            stage_item = await get_stage_item(tournament_id, stage_item_id)
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2.lifecycle_state == RoundLifecycleState.RESOLVED

            await sql_set_round_is_pinned(round2.id, True)

            r2_before = [(m.stage_item_input1_id, m.stage_item_input2_id) for m in round2.matches]

            reset_match = round1_matches[0]
            reset_response = await send_tournament_request(
                HTTPMethod.POST, f"matches/{reset_match.id}/reset", auth_context
            )
            assert reset_response["data"]["state"] == "NOT_STARTED"

            stage_item = await get_stage_item(tournament_id, stage_item_id)
            round2_after = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2_after.lifecycle_state == RoundLifecycleState.RESOLVED
            assert round2_after.is_pinned is True
            r2_after = [
                (m.stage_item_input1_id, m.stage_item_input2_id) for m in round2_after.matches
            ]
            assert r2_after == r2_before
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
