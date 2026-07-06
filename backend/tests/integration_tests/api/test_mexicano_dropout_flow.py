"""Integration test: mid-tournament dropouts in a Mexicano stage item (issue #261).

Drives an even-count (4-team) Mexicano stage item through a round, then deactivates the
lowest-standing team mid-tournament. Asserts:
- the deactivated team's completed-round points keep counting in the standings
- future round resolution excludes it, and the now-odd active field gets a rotating bye with
  round-average compensation once that round completes
- reactivating the team restores it to a later round's resolution
"""

from decimal import Decimal

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.handle_stage_activation import (
    _resolve_round_1_for_standings_resolved_stage_item,
)
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
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
    return sorted(round_.matches, key=lambda m: m.input1_slot)


async def _set_team_active(
    auth_context: AuthContext, team_id: int, name: str, active: bool
) -> None:
    await send_tournament_request(
        HTTPMethod.PUT,
        f"teams/{team_id}",
        auth_context,
        json={"name": name, "active": active, "player_ids": []},
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_mexicano_dropout_and_reactivation_flow(
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
            input_to_team = {inp.id: inp.team_id for inp in stage_item.inputs}

            # Resolve + complete round 1 by builder order: t1=21, t2=10, t3=15, t4=18.
            await _resolve_round_1_for_standings_resolved_stage_item(tournament_id, stage_item)
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round1, round2, round3 = sorted(stage_item.rounds, key=lambda r: r.id)
            r1_a, r1_b = _match_by_first_slot(round1)
            await complete_match(auth_context, r1_a.id, r1_a.match_sets[0].id, score1=21, score2=10)
            await complete_match(auth_context, r1_b.id, r1_b.match_sets[0].id, score1=15, score2=18)

            # Round 2 auto-resolves from standings (even field): (t1,t4),(t3,t2).
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2.lifecycle_state == RoundLifecycleState.RESOLVED

            # Deactivate t2 (the lowest-standing team). Its round-1 points must keep counting.
            await _set_team_active(auth_context, t2.id, t2.name, active=False)

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            points_by_team = {inp.team_id: inp.points for inp in stage_item.inputs}
            assert points_by_team[t2.id] == 10

            # Round 2 is unstarted and RESOLVED -> re-resolves excluding t2: an odd active field
            # of {t1, t3, t4} gets a rotating bye. All tied at zero prior byes, tiebreak by
            # ascending slot picks t1 to sit out; the rest (t3, t4) pair by standings (t4 leads).
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            r2_a, r2_b = _match_by_first_slot(round2)
            assert (r2_a.stage_item_input1_id, r2_a.stage_item_input2_id) != (None, None)
            assert (r2_b.stage_item_input1_id, r2_b.stage_item_input2_id) == (None, None)
            assert (
                input_to_team[r2_a.stage_item_input1_id],
                input_to_team[r2_a.stage_item_input2_id],
            ) == (t4.id, t3.id)

            # Complete the one real match of round 2. The empty sibling match must not block
            # the round from completing.
            await complete_match(auth_context, r2_a.id, r2_a.match_sets[0].id, score1=25, score2=5)

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            points_by_team = {inp.team_id: inp.points for inp in stage_item.inputs}
            # t1 sat out round 2: banks the round average of mean(25, 5) = 15, on top of its
            # round-1 total of 21.
            assert points_by_team[t1.id] == Decimal("21") + Decimal("15")
            assert points_by_team[t2.id] == Decimal("10")  # untouched: still inactive
            assert points_by_team[t3.id] == Decimal("15") + Decimal("5")
            assert points_by_team[t4.id] == Decimal("18") + Decimal("25")

            # Round 3 auto-resolves next: t1 now has one bye, t3/t4 have zero -> t3 (lower slot)
            # sits out this time, and the standings-leading pair (t4, t1) plays.
            round3 = sorted(stage_item.rounds, key=lambda r: r.id)[2]
            assert round3.lifecycle_state == RoundLifecycleState.RESOLVED
            r3_a, r3_b = _match_by_first_slot(round3)
            assert (r3_b.stage_item_input1_id, r3_b.stage_item_input2_id) == (None, None)
            assert (
                input_to_team[r3_a.stage_item_input1_id],
                input_to_team[r3_a.stage_item_input2_id],
            ) == (t4.id, t1.id)

            # Reactivate t2: round 3 is still unstarted, so it re-resolves with the field back to
            # even (4 active), restoring t2 to a real pairing with no bye needed.
            await _set_team_active(auth_context, t2.id, t2.name, active=True)

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round3 = sorted(stage_item.rounds, key=lambda r: r.id)[2]
            r3_a, r3_b = _match_by_first_slot(round3)
            playing_round3 = {
                input_to_team[r3_a.stage_item_input1_id],
                input_to_team[r3_a.stage_item_input2_id],
                input_to_team[r3_b.stage_item_input1_id],
                input_to_team[r3_b.stage_item_input2_id],
            }
            assert playing_round3 == {t1.id, t2.id, t3.id, t4.id}
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
