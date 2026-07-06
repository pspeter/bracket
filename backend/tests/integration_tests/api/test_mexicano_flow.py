"""Integration test: full Mexicano stage-item flow (issue #259).

Drives an even-count Mexicano stage item start to finish: create, resolve round 1 (builder
order), complete round 1 via match-set scores, assert round 2 is re-drawn from the standings
(1v2, 3v4, top pair in the first slot), assert an upstream score correction re-resolves the
unstarted round 2, and assert a pinned round survives a later correction. Also asserts odd
entrant counts are rejected at creation.
"""

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.handle_stage_activation import (
    _resolve_round_1_for_standings_resolved_stage_item,
)
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.rounds import sql_set_round_is_pinned
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import complete_match, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_stage,
    inserted_team,
)


def _match_by_first_slot(round_):  # type: ignore[no-untyped-def]
    """Return the round's two matches ordered by their first playing slot (match_a, match_b)."""
    return sorted(round_.matches, key=lambda m: m.input1_slot)


@pytest.mark.asyncio(loop_scope="session")
async def test_mexicano_full_even_count_flow(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
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
            stage_item_raw = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted.id,
                    type=StageType.MEXICANO,
                    team_count=4,
                    games_per_player=3,
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
            # games_per_player=3 pre-creates three placeholder rounds, each with two slot-matches.
            assert len(stage_item.rounds) == 3
            for round_ in stage_item.rounds:
                assert round_.lifecycle_state == RoundLifecycleState.PLACEHOLDER
                assert len(round_.matches) == 2

            input_to_team = {inp.id: inp.team_id for inp in stage_item.inputs}

            # Resolve round 1 (simulates stage activation): pairs strictly by builder order.
            await _resolve_round_1_for_standings_resolved_stage_item(tournament_id, stage_item)
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round1, round2, _round3 = sorted(stage_item.rounds, key=lambda r: r.id)
            assert round1.lifecycle_state == RoundLifecycleState.RESOLVED

            r1_a, r1_b = _match_by_first_slot(round1)
            assert (
                input_to_team[r1_a.stage_item_input1_id],
                input_to_team[r1_a.stage_item_input2_id],
            ) == (
                t1.id,
                t2.id,
            )
            assert (
                input_to_team[r1_b.stage_item_input1_id],
                input_to_team[r1_b.stage_item_input2_id],
            ) == (
                t3.id,
                t4.id,
            )

            # Complete round 1 with scores → standings by points scored: t1=21, t4=18, t3=15, t2=10.
            await complete_match(auth_context, r1_a.id, r1_a.match_sets[0].id, score1=21, score2=10)
            await complete_match(auth_context, r1_b.id, r1_b.match_sets[0].id, score1=15, score2=18)

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2.lifecycle_state == RoundLifecycleState.RESOLVED

            # Round 2 re-drawn from standings 1v2, 3v4: (t1,t4),(t3,t2); top pair in first slot.
            r2_a, r2_b = _match_by_first_slot(round2)
            assert (
                input_to_team[r2_a.stage_item_input1_id],
                input_to_team[r2_a.stage_item_input2_id],
            ) == (
                t1.id,
                t4.id,
            )
            assert (
                input_to_team[r2_b.stage_item_input1_id],
                input_to_team[r2_b.stage_item_input2_id],
            ) == (
                t3.id,
                t2.id,
            )

            # Correct a round-1 score (match stays completed) → standings flip to t2=25, t4=18,
            # t3=15, t1=5, and the unstarted non-pinned round 2 re-resolves to (t2,t4),(t3,t1).
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{r1_a.id}/sets/{r1_a.match_sets[0].id}/score-edit",
                auth_context,
                json={"stage_item_input1_score": 5, "stage_item_input2_score": 25},
            )
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            r2_a, r2_b = _match_by_first_slot(round2)
            assert (
                input_to_team[r2_a.stage_item_input1_id],
                input_to_team[r2_a.stage_item_input2_id],
            ) == (
                t2.id,
                t4.id,
            )
            assert (
                input_to_team[r2_b.stage_item_input1_id],
                input_to_team[r2_b.stage_item_input2_id],
            ) == (
                t3.id,
                t1.id,
            )

            # Pin round 2, then correct round 1 again → pinned round is left untouched.
            await sql_set_round_is_pinned(round2.id, True)
            pinned_before = [
                (m.stage_item_input1_id, m.stage_item_input2_id)
                for m in _match_by_first_slot(round2)
            ]
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{r1_a.id}/sets/{r1_a.match_sets[0].id}/score-edit",
                auth_context,
                json={"stage_item_input1_score": 30, "stage_item_input2_score": 1},
            )
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2.is_pinned is True
            pinned_after = [
                (m.stage_item_input1_id, m.stage_item_input2_id)
                for m in _match_by_first_slot(round2)
            ]
            assert pinned_after == pinned_before

            # Final standings reflect cumulative points scored across completed matches.
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            points_by_team = {inp.team_id: inp.points for inp in stage_item.inputs}
            # After the last correction: t1 scored 30 (r1), t2 scored 1, t3 scored 15, t4 scored 18.
            assert points_by_team[t1.id] == 30
            assert points_by_team[t2.id] == 1
            assert points_by_team[t3.id] == 15
            assert points_by_team[t4.id] == 18
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_mexicano_odd_team_count_rejected(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Creating a Mexicano stage item with an odd number of entrants is rejected."""
    tournament_id = auth_context.tournament.id

    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
    ) as stage_inserted:
        try:
            response = await send_tournament_request(
                HTTPMethod.POST,
                "stage_items",
                auth_context,
                json={
                    "stage_id": stage_inserted.id,
                    "type": "MEXICANO",
                    "team_count": 5,
                    "ranking_id": auth_context.ranking.id,
                    "games_per_player": 3,
                },
            )
            assert "detail" in response
            assert "even number of teams" in response["detail"].lower()
        finally:
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
