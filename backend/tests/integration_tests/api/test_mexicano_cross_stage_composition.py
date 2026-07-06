"""Integration test: a Mexicano stage item feeding a later stage item (issue #261).

Mirrors ``test_stage_item_completion_resolution.py``'s "winner of stage item" pattern, but with a
Mexicano source: a single-elimination final's inputs are tentative references to the Mexicano's
final ranking positions (by cumulative points scored), and must resolve to concrete teams as soon
as the Mexicano stage item completes -- and re-resolve if a later score correction reorders the
final standings.
"""

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.handle_stage_activation import (
    _resolve_round_1_for_standings_resolved_stage_item,
)
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
    StageItemInputFinal,
)
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_STAGE2, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from bracket.utils.types import assert_some
from tests.integration_tests.api.shared import complete_match, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_stage, inserted_team


def _match_by_first_slot(round_):  # type: ignore[no-untyped-def]
    return sorted(round_.matches, key=lambda m: m.input1_slot)


@pytest.mark.asyncio(loop_scope="session")
async def test_mexicano_final_standings_resolve_into_next_stage_item(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted_1,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted_2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
    ):
        mexicano_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                type=StageType.MEXICANO,
                team_count=4,
                games_per_player=1,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                    StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                    StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                    StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                ],
            ),
        )
        final_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_2.id,
                type=StageType.SINGLE_ELIMINATION,
                team_count=2,
                inputs=[
                    StageItemInputCreateBodyTentative(
                        slot=1, winner_from_stage_item_id=mexicano_item.id, winner_position=1
                    ),
                    StageItemInputCreateBodyTentative(
                        slot=2, winner_from_stage_item_id=mexicano_item.id, winner_position=2
                    ),
                ],
            ),
        )
        await build_matches_for_stage_item(mexicano_item, tournament_id)
        await build_matches_for_stage_item(final_item, tournament_id)

        try:
            stage_item = await get_stage_item(tournament_id, mexicano_item.id)
            # games_per_player=1 with an even (4-team) field -> a single round, no bye.
            assert len(stage_item.rounds) == 1
            input_to_team = {inp.id: inp.team_id for inp in stage_item.inputs}

            await _resolve_round_1_for_standings_resolved_stage_item(tournament_id, stage_item)
            stage_item = await get_stage_item(tournament_id, mexicano_item.id)
            [round1] = stage_item.rounds
            r1_a, r1_b = _match_by_first_slot(round1)

            # Builder-order pairing: (t1, t2) and (t3, t4).
            assert {
                input_to_team[r1_a.stage_item_input1_id],
                input_to_team[r1_a.stage_item_input2_id],
            } == {
                t1.id,
                t2.id,
            }

            # t4 wins big (points scored 30 vs 5), t2 wins narrowly (20 vs 18):
            # final standings by points scored -> t4=30, t2=20, t3=18, t1=5.
            scores_by_pair = {
                frozenset({t1.id, t2.id}): (5, 20),
                frozenset({t3.id, t4.id}): (18, 30),
            }
            for match in (r1_a, r1_b):
                team1 = assert_some(input_to_team[match.stage_item_input1_id])
                team2 = assert_some(input_to_team[match.stage_item_input2_id])
                score1, score2 = scores_by_pair[frozenset({team1, team2})]
                await complete_match(
                    auth_context, match.id, match.match_sets[0].id, score1=score1, score2=score2
                )

            # The Mexicano stage item is now fully complete -> the final's tentative inputs
            # resolve to the top 2 by points scored: t4 (winner_position=1), t2 (position=2).
            stages = await get_full_tournament_details(tournament_id)
            next_stage = next(s for s in stages if s.id == stage_inserted_2.id)
            final_inputs = sorted(next_stage.stage_items[0].inputs, key=lambda i: i.slot)
            assert len(final_inputs) == 2
            for input_ in final_inputs:
                assert isinstance(input_, StageItemInputFinal)
            assert final_inputs[0].team_id == t4.id
            assert final_inputs[1].team_id == t2.id

            # A late correction on the (t1, t2) match flips it: t1 now scores 25, t2 scores 5.
            # New final standings: t4=30, t1=25, t3=18, t2=5 -> position 1 stays t4, but position 2
            # flips from t2 to t1. Reconciliation must re-resolve the (already-resolved) final.
            correction_match = (
                r1_a
                if {
                    input_to_team[r1_a.stage_item_input1_id],
                    input_to_team[r1_a.stage_item_input2_id],
                }
                == {t1.id, t2.id}
                else r1_b
            )
            score1, score2 = (
                (25, 5)
                if input_to_team[correction_match.stage_item_input1_id] == t1.id
                else (5, 25)
            )
            correction_set_id = correction_match.match_sets[0].id
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{correction_match.id}/sets/{correction_set_id}/score-edit",
                auth_context,
                json={"stage_item_input1_score": score1, "stage_item_input2_score": score2},
            )

            stages = await get_full_tournament_details(tournament_id)
            next_stage = next(s for s in stages if s.id == stage_inserted_2.id)
            final_inputs = sorted(next_stage.stage_items[0].inputs, key=lambda i: i.slot)
            assert final_inputs[0].team_id == t4.id
            assert final_inputs[1].team_id == t1.id
        finally:
            await sql_delete_stage_item_with_foreign_keys(final_item.id)
            await sql_delete_stage_item_with_foreign_keys(mexicano_item.id)
