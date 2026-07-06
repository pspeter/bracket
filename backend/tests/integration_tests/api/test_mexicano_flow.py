"""Integration test: full Mexicano stage-item flow (issues #259, #260).

Drives an even-count Mexicano stage item start to finish: create, resolve round 1 (builder
order), complete round 1 via match-set scores, assert round 2 is re-drawn from the standings
(1v2, 3v4, top pair in the first slot), assert an upstream score correction re-resolves the
unstarted round 2, and assert a pinned round survives a later correction. Also drives an
odd-count Mexicano end to end: round count from the odd-count formula, bye rotation by
fewest-byes-so-far (not standings), and round-average bye compensation in the standings.
"""

from decimal import Decimal

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.handle_stage_activation import (
    _resolve_round_1_for_standings_resolved_stage_item,
)
from bracket.models.db.match import MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.rounds import sql_set_round_is_pinned
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from bracket.utils.id_types import StageItemInputId, TeamId
from bracket.utils.types import assert_some
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


async def _complete_round_matches_by_team_pair(
    auth_context: AuthContext,
    input_to_team: dict[StageItemInputId, TeamId | None],
    round_matches: list[MatchWithDetailsDefinitive | MatchWithDetails],
    scores_by_team_pair: dict[frozenset[TeamId], tuple[int, int]],
) -> None:
    """Complete every match of a round, looking up its score by the (unordered) team pair."""
    for match in round_matches:
        team1 = input_to_team[assert_some(match.stage_item_input1_id)]
        team2 = input_to_team[assert_some(match.stage_item_input2_id)]
        assert team1 is not None and team2 is not None
        score1, score2 = scores_by_team_pair[frozenset({team1, team2})]
        await complete_match(
            auth_context, match.id, match.match_sets[0].id, score1=score1, score2=score2
        )


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
async def test_mexicano_odd_team_count_end_to_end(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Odd-count Mexicano (issue #260): accepted at creation, schedules the Swiss odd-count round
    formula with a bye slot every round, rotates the bye by fewest-byes-so-far rather than
    standings, and compensates each bye with that round's average points scored."""
    tournament_id = auth_context.tournament.id

    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
        ) as stage_inserted,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t1,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t2,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t3,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t4,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as t5,
    ):
        try:
            # games_per_player=1, team_count=5 -> ceil(1*5/4) = 2 rounds.
            stage_item_raw = await sql_create_stage_item_with_inputs(
                tournament_id,
                StageItemWithInputsCreate(
                    stage_id=stage_inserted.id,
                    type=StageType.MEXICANO,
                    team_count=5,
                    games_per_player=1,
                    ranking_id=auth_context.ranking.id,
                    inputs=[
                        StageItemInputCreateBodyFinal(slot=1, team_id=t1.id),
                        StageItemInputCreateBodyFinal(slot=2, team_id=t2.id),
                        StageItemInputCreateBodyFinal(slot=3, team_id=t3.id),
                        StageItemInputCreateBodyFinal(slot=4, team_id=t4.id),
                        StageItemInputCreateBodyFinal(slot=5, team_id=t5.id),
                    ],
                ),
            )
            await build_matches_for_stage_item(stage_item_raw, tournament_id)

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            # Odd-count formula pre-creates 2 rounds, each with 2 playing matches + a bye slot.
            assert len(stage_item.rounds) == 2
            for round_ in stage_item.rounds:
                assert round_.lifecycle_state == RoundLifecycleState.PLACEHOLDER
                assert len(round_.matches) == 2
                assert all(m.referee_slot == 4 for m in round_.matches)

            input_to_team = {inp.id: inp.team_id for inp in stage_item.inputs}

            # Resolve round 1: with no history all bye-counts tie at zero, so the tiebreak (slot
            # ascending) sits slot 1 (t1) out; the rest pair by builder order (all zero points).
            await _resolve_round_1_for_standings_resolved_stage_item(tournament_id, stage_item)
            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            round1, round2 = sorted(stage_item.rounds, key=lambda r: r.id)
            assert round1.lifecycle_state == RoundLifecycleState.RESOLVED

            r1_a, r1_b = _match_by_first_slot(round1)
            assert input_to_team[r1_a.referee_stage_item_input_id] == t1.id
            assert (
                input_to_team[r1_a.stage_item_input1_id],
                input_to_team[r1_a.stage_item_input2_id],
            ) == (t2.id, t3.id)
            assert (
                input_to_team[r1_b.stage_item_input1_id],
                input_to_team[r1_b.stage_item_input2_id],
            ) == (t4.id, t5.id)

            # Complete round 1: t2 beats t3 21-9, t4 beats t5 15-18 (t5 wins).
            await complete_match(auth_context, r1_a.id, r1_a.match_sets[0].id, score1=21, score2=9)
            await complete_match(auth_context, r1_b.id, r1_b.match_sets[0].id, score1=15, score2=18)

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            points_by_team = {inp.team_id: inp.points for inp in stage_item.inputs}
            # Round-1 average of points scored = mean(21, 9, 15, 18) = 15.75, banked by t1's bye.
            assert points_by_team[t1.id] == Decimal("15.75")
            assert points_by_team[t2.id] == Decimal("21")
            assert points_by_team[t3.id] == Decimal("9")
            assert points_by_team[t4.id] == Decimal("15")
            assert points_by_team[t5.id] == Decimal("18")

            # Round 2 auto-resolves: t1 now has 1 bye, everyone else has 0 -> next bye ties among
            # {t2, t3, t4, t5} at 0 byes, tiebreak by ascending slot picks slot 2 (t2) -- even
            # though t2 is the current standings leader, proving the bye is not standings-driven.
            round2 = sorted(stage_item.rounds, key=lambda r: r.id)[1]
            assert round2.lifecycle_state == RoundLifecycleState.RESOLVED
            r2_a, r2_b = _match_by_first_slot(round2)
            assert input_to_team[r2_a.referee_stage_item_input_id] == t2.id
            playing_round2 = {
                input_to_team[r2_a.stage_item_input1_id],
                input_to_team[r2_a.stage_item_input2_id],
                input_to_team[r2_b.stage_item_input1_id],
                input_to_team[r2_b.stage_item_input2_id],
            }
            assert playing_round2 == {t1.id, t3.id, t4.id, t5.id}

            # Complete round 2 with scores designed to be identifiable in the final standings.
            await _complete_round_matches_by_team_pair(
                auth_context,
                input_to_team,
                [r2_a, r2_b],
                {
                    frozenset({t5.id, t1.id}): (25, 11),
                    frozenset({t4.id, t3.id}): (20, 8),
                },
            )

            stage_item = await get_stage_item(tournament_id, stage_item_raw.id)
            points_by_team = {inp.team_id: inp.points for inp in stage_item.inputs}
            # t1 played round 2 (lost 11-25 to t5): 15.75 (r1 bye) + 11 (r2 played) = 26.75
            assert points_by_team[t1.id] == Decimal("26.75")
            # t2 sat out round 2: banks round-2 average of mean(25, 11, 20, 8) = 16.
            # 21 (r1 played) + 16 (r2 bye) = 37
            assert points_by_team[t2.id] == Decimal("37")
            assert points_by_team[t3.id] == Decimal("9") + Decimal("8")  # 17
            assert points_by_team[t4.id] == Decimal("15") + Decimal("20")  # 35
            assert points_by_team[t5.id] == Decimal("18") + Decimal("25")  # 43

            # Standings order (highest points first) reflects the fractional compensation.
            ordered_teams = sorted(points_by_team.items(), key=lambda item: item[1], reverse=True)
            assert [team_id for team_id, _ in ordered_teams] == [t5.id, t2.id, t4.id, t1.id, t3.id]
        finally:
            await assert_row_count_and_clear(matches, 0)
            await assert_row_count_and_clear(rounds, 0)
            await assert_row_count_and_clear(stage_item_inputs, 0)
            await assert_row_count_and_clear(stage_items, 0)
            await assert_row_count_and_clear(stages, 0)
