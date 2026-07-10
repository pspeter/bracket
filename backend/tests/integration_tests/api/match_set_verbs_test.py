"""Integration tests for match set transition verbs (issue #235)."""

from collections.abc import AsyncIterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager

import pytest

from bracket.database import database
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.match import Match, MatchSetState, MatchState
from bracket.models.db.ranking import RankingMatchPointsBody
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputInsertable,
)
from bracket.models.db.util import StageItemWithRounds
from bracket.schema import rankings, tournaments
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
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
from bracket.utils.id_types import MatchId, StageItemId, TournamentId
from tests.integration_tests.api.shared import (
    complete_match,
    send_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
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
        await complete_match(auth_context, match_inserted.id, set_id)
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
async def test_match_detail_response_carries_draws_allowed_from_ranking(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        response = await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/start", auth_context
        )
        assert response["data"]["draws_allowed"] is True

    async with (
        _draws_disallowed_ranking(auth_context),
        _simple_match(auth_context) as match_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/start", auth_context
        )
        assert response["data"]["draws_allowed"] is False


@pytest.mark.asyncio(loop_scope="session")
async def test_end_rejected_at_equal_scores_when_draws_disallowed(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        _draws_disallowed_ranking(auth_context),
        _simple_match(auth_context) as match_inserted,
    ):
        set_id = match_inserted.match_sets[0].id
        await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/start", auth_context
        )
        await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/sets/{set_id}/score-edit",
            auth_context,
            json={"stage_item_input1_score": 10, "stage_item_input2_score": 10},
        )
        response = await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/end", auth_context
        )
        assert response == {"detail": "Cannot end: draws are not allowed for this ranking"}


@pytest.mark.asyncio(loop_scope="session")
async def test_editing_completed_set_to_equal_scores_rejected_when_draws_disallowed(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        _draws_disallowed_ranking(auth_context),
        _simple_match(auth_context) as match_inserted,
    ):
        set_id = match_inserted.match_sets[0].id
        await complete_match(auth_context, match_inserted.id, set_id, score1=21, score2=10)
        response = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/sets/{set_id}/score-edit",
            auth_context,
            json={"stage_item_input1_score": 15, "stage_item_input2_score": 15},
        )
        assert response == {"detail": "Cannot edit: draws are not allowed for this ranking"}


@pytest.mark.asyncio(loop_scope="session")
async def test_editing_in_progress_set_to_equal_scores_succeeds_when_draws_disallowed(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        _draws_disallowed_ranking(auth_context),
        _simple_match(auth_context) as match_inserted,
    ):
        set_id = match_inserted.match_sets[0].id
        await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/start", auth_context
        )
        response = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/sets/{set_id}/score-edit",
            auth_context,
            json={"stage_item_input1_score": 5, "stage_item_input2_score": 5},
        )
        assert response["data"]["match_sets"][0]["stage_item_input1_score"] == 5
        assert response["data"]["match_sets"][0]["stage_item_input2_score"] == 5
        assert response["data"]["match_sets"][0]["state"] == "IN_PROGRESS"


@pytest.mark.asyncio(loop_scope="session")
async def test_end_at_equal_scores_still_succeeds_when_draws_allowed(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        set_id = match_inserted.match_sets[0].id
        await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/start", auth_context
        )
        await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/sets/{set_id}/score-edit",
            auth_context,
            json={"stage_item_input1_score": 10, "stage_item_input2_score": 10},
        )
        response = await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/end", auth_context
        )
        assert response["data"]["state"] == "COMPLETED"
        assert response["data"]["match_sets"][0]["state"] == "COMPLETED"


@pytest.mark.asyncio(loop_scope="session")
async def test_editing_completed_set_to_equal_scores_still_succeeds_when_draws_allowed(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        set_id = match_inserted.match_sets[0].id
        await complete_match(auth_context, match_inserted.id, set_id, score1=21, score2=10)
        response = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{match_inserted.id}/sets/{set_id}/score-edit",
            auth_context,
            json={"stage_item_input1_score": 15, "stage_item_input2_score": 15},
        )
        assert response["data"]["match_sets"][0]["stage_item_input1_score"] == 15
        assert response["data"]["match_sets"][0]["stage_item_input2_score"] == 15


@pytest.mark.asyncio(loop_scope="session")
async def test_reopen_clears_completed_at(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with _simple_match(auth_context) as match_inserted:
        set_id = match_inserted.match_sets[0].id
        await complete_match(auth_context, match_inserted.id, set_id)
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
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            semi = bracket.rounds[0].matches[0]
            semi_set_id = semi.match_sets[0].id
            winner_input_id = semi.stage_item_input1_id
            loser_input_id = semi.stage_item_input2_id
            assert winner_input_id is not None and loser_input_id is not None

            await complete_match(auth_context, semi.id, semi_set_id, score1=21, score2=0)

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
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
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
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
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            semi = bracket.rounds[0].matches[0]
            final = bracket.rounds[1].matches[0]
            semi_set_id = semi.match_sets[0].id

            await complete_match(auth_context, semi.id, semi_set_id)

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            assert bracket.rounds[1].matches[0].stage_item_input1_id is not None

            reset = await send_tournament_request(
                HTTPMethod.POST, f"matches/{semi.id}/reset", auth_context
            )
            assert reset["data"]["state"] == "NOT_STARTED"
            assert reset["data"]["completed_at"] is None
            assert reset["data"]["match_sets"][0]["stage_item_input1_score"] == 0

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
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
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            semi1 = bracket.rounds[0].matches[0]
            semi2 = bracket.rounds[0].matches[1]
            final = bracket.rounds[1].matches[0]

            await complete_match(auth_context, semi1.id, semi1.match_sets[0].id)
            await complete_match(auth_context, semi2.id, semi2.match_sets[0].id)
            await complete_match(auth_context, final.id, final.match_sets[0].id)

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            final = bracket.rounds[1].matches[0]
            assert final.state == MatchState.COMPLETED
            assert final.completed_at is not None

            # The final has started: resetting its feeder must be rejected, and nothing changes.
            rejected = await send_tournament_request(
                HTTPMethod.POST, f"matches/{semi1.id}/reset", auth_context
            )
            assert "reset the downstream" in rejected["detail"].lower()

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            semi1_unchanged = bracket.rounds[0].matches[0]
            final_unchanged = bracket.rounds[1].matches[0]
            assert semi1_unchanged.state == MatchState.COMPLETED
            assert final_unchanged.state == MatchState.COMPLETED
            assert final_unchanged.completed_at is not None
            assert final_unchanged.stage_item_input1_id is not None

            # Reset the downstream match first, then the feeder reset succeeds.
            await send_tournament_request(
                HTTPMethod.POST, f"matches/{final.id}/reset", auth_context
            )
            await send_tournament_request(
                HTTPMethod.POST, f"matches/{semi1.id}/reset", auth_context
            )

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
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
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
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


def _match_fed_by(round_matches: Sequence[Match], feeder_match_id: MatchId) -> Match:
    """Return the match in ``round_matches`` that takes its winner from ``feeder_match_id``."""
    return next(
        m
        for m in round_matches
        if feeder_match_id
        in (m.stage_item_input1_winner_from_match_id, m.stage_item_input2_winner_from_match_id)
    )


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
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            quarter_final = bracket.rounds[0].matches[0]
            semi = _match_fed_by(bracket.rounds[1].matches, quarter_final.id)
            championship = bracket.rounds[2].matches[0]

            feeder_ids = {
                semi.stage_item_input1_winner_from_match_id,
                semi.stage_item_input2_winner_from_match_id,
            }
            for feeder in bracket.rounds[0].matches:
                if feeder.id in feeder_ids:
                    await complete_match(auth_context, feeder.id, feeder.match_sets[0].id)
            await complete_match(auth_context, semi.id, semi.match_sets[0].id)

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            championship = bracket.rounds[2].matches[0]
            assert (
                championship.stage_item_input1_id is not None
                or championship.stage_item_input2_id is not None
            )

            # The semi (an immediate follower of the quarter-final) has started: rejected.
            rejected = await send_tournament_request(
                HTTPMethod.POST, f"matches/{quarter_final.id}/reset", auth_context
            )
            assert "reset the downstream" in rejected["detail"].lower()

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            quarter_final_unchanged = bracket.rounds[0].matches[0]
            semi_unchanged = _match_fed_by(bracket.rounds[1].matches, quarter_final.id)
            championship_unchanged = bracket.rounds[2].matches[0]
            assert quarter_final_unchanged.state == MatchState.COMPLETED
            assert semi_unchanged.state == MatchState.COMPLETED
            assert (
                championship_unchanged.stage_item_input1_id is not None
                or championship_unchanged.stage_item_input2_id is not None
            )

            # Reset deepest-first: the semi has no started follower (the championship hasn't
            # started), so it can be reset; that then unblocks resetting the quarter-final.
            await send_tournament_request(HTTPMethod.POST, f"matches/{semi.id}/reset", auth_context)
            await send_tournament_request(
                HTTPMethod.POST, f"matches/{quarter_final.id}/reset", auth_context
            )

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            semi_reset = _match_fed_by(bracket.rounds[1].matches, quarter_final.id)
            championship_reset = bracket.rounds[2].matches[0]
            assert semi_reset.state == MatchState.NOT_STARTED
            if semi_reset.stage_item_input1_winner_from_match_id == quarter_final.id:
                assert semi_reset.stage_item_input1_id is None
            else:
                assert semi_reset.stage_item_input2_id is None
            assert championship_reset.stage_item_input1_id is None
            assert championship_reset.stage_item_input2_id is None
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_score_edit_flip_winner_leaves_started_final_unchanged(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Flipping a completed semi's winner via score-edit must not touch an IN_PROGRESS final."""
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
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            semi1 = bracket.rounds[0].matches[0]
            semi2 = bracket.rounds[0].matches[1]

            semi1_set_id = semi1.match_sets[0].id
            winner_input_id = semi1.stage_item_input1_id
            loser_input_id = semi1.stage_item_input2_id
            assert winner_input_id is not None and loser_input_id is not None

            await complete_match(auth_context, semi1.id, semi1_set_id, score1=21, score2=0)
            await complete_match(auth_context, semi2.id, semi2.match_sets[0].id)

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            final = bracket.rounds[1].matches[0]
            assert final.stage_item_input1_id == winner_input_id

            # Start the final so it counts as "started" and must not be touched by the cascade.
            await send_tournament_request(
                HTTPMethod.POST, f"matches/{final.id}/start", auth_context
            )
            final_inputs_before = (final.stage_item_input1_id, final.stage_item_input2_id)

            flipped = await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{semi1.id}/sets/{semi1_set_id}/score-edit",
                auth_context,
                json={"stage_item_input1_score": 0, "stage_item_input2_score": 21},
            )
            assert flipped["data"]["state"] == "COMPLETED"

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            final_after = bracket.rounds[1].matches[0]
            assert final_after.state == MatchState.IN_PROGRESS
            assert (
                final_after.stage_item_input1_id,
                final_after.stage_item_input2_id,
            ) == final_inputs_before
            assert final_after.stage_item_input1_id == winner_input_id
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item.id)


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
        await complete_match(auth_context, match_inserted.id, set_id)
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


@pytest.mark.asyncio(loop_scope="session")
async def test_score_tracking_token_verb_on_unscheduled_match_returns_404(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        _simple_match(auth_context) as match_inserted,
        _score_tracking_token(auth_context.tournament.id, "unscheduled-token") as token,
    ):
        await send_tournament_request(
            HTTPMethod.POST, f"matches/{match_inserted.id}/unschedule", auth_context
        )
        response = await send_request(
            HTTPMethod.POST, f"score-tracking/{token}/matches/{match_inserted.id}/start"
        )
        assert response == {"detail": "Could not find scheduled match"}


@pytest.mark.asyncio(loop_scope="session")
async def test_legacy_set_state_endpoint_is_removed(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """The pre-verb ``PUT .../sets/{id}`` endpoint no longer exists on either auth path."""
    async with (
        _simple_match(auth_context) as match_inserted,
        _score_tracking_token(auth_context.tournament.id, "legacy-put-token") as token,
    ):
        set_id = match_inserted.match_sets[0].id
        body = {"stage_item_input1_score": 21, "stage_item_input2_score": 10, "state": "COMPLETED"}

        authenticated = await send_tournament_request(
            HTTPMethod.PUT, f"matches/{match_inserted.id}/sets/{set_id}", auth_context, json=body
        )
        assert authenticated == {"detail": "Not Found"}

        by_token = await send_request(
            HTTPMethod.PUT,
            f"score-tracking/{token}/matches/{match_inserted.id}/sets/{set_id}",
            json=body,
        )
        assert by_token == {"detail": "Not Found"}


@pytest.mark.asyncio(loop_scope="session")
async def test_score_edit_collapses_best_of_three_to_fewer_played_sets(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Correcting a flipped past-set score can collapse a best-of-3 to two decisive sets.

    The recorded history said the match went to a third set; the corrected set 1 means one
    side actually won the first two sets, so the organizer zeroes the trailing set (it was
    never really played) and the winner re-derives from sets won — without the match ever
    leaving COMPLETED.
    """
    tournament_id = auth_context.tournament.id
    async with (
        _best_of_three_ranking(auth_context),
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
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            semi = bracket.rounds[0].matches[0]
            assert len(semi.match_sets) == 3
            recorded_winner_input_id = semi.stage_item_input1_id
            actual_winner_input_id = semi.stage_item_input2_id
            assert recorded_winner_input_id is not None and actual_winner_input_id is not None

            # Recorded history: input1 wins sets 1 and 3, input2 wins set 2.
            for match_set, (score1, score2) in zip(
                semi.match_sets, [(21, 15), (18, 21), (21, 10)], strict=True
            ):
                await complete_match(
                    auth_context, semi.id, match_set.id, score1=score1, score2=score2
                )

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            final = bracket.rounds[1].matches[0]
            assert final.stage_item_input1_id == recorded_winner_input_id

            # Correction: set 1 was entered flipped — input2 actually won it, so input2 won
            # the first two sets and set 3 was never really played.
            await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{semi.id}/sets/{semi.match_sets[0].id}/score-edit",
                auth_context,
                json={"stage_item_input1_score": 15, "stage_item_input2_score": 21},
            )
            collapsed = await send_tournament_request(
                HTTPMethod.POST,
                f"matches/{semi.id}/sets/{semi.match_sets[2].id}/score-edit",
                auth_context,
                json={"stage_item_input1_score": 0, "stage_item_input2_score": 0},
            )
            assert collapsed["data"]["state"] == "COMPLETED"
            assert collapsed["data"]["completed_at"] is not None
            assert collapsed["data"]["match_sets"][2]["stage_item_input1_score"] == 0
            assert collapsed["data"]["match_sets"][2]["stage_item_input2_score"] == 0

            details = await get_full_tournament_details(tournament_id)
            bracket = next(si for s in details for si in s.stage_items if si.id == stage_item.id)
            final = bracket.rounds[1].matches[0]
            assert final.stage_item_input1_id == actual_winner_input_id
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_best_of_n_completes_match_at_set_majority(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """In a Bo3 with "play out all sets" off, winning two sets ends the match on the spot:
    no dead rubber is started, ``completed_at`` is stamped, and the winner advances into the
    elimination final through the ordinary reconciliation path."""
    tournament_id = auth_context.tournament.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=False),
        _four_team_elimination(auth_context) as stage_item_id,
    ):
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi = bracket.rounds[0].matches[0]
        winner_input_id = semi.stage_item_input1_id
        assert len(semi.match_sets) == 3

        first = await complete_match(
            auth_context, semi.id, semi.match_sets[0].id, score1=21, score2=15
        )
        assert first["data"]["state"] == "IN_PROGRESS"
        assert first["data"]["completed_at"] is None

        decided = await complete_match(
            auth_context, semi.id, semi.match_sets[1].id, score1=21, score2=10
        )
        assert decided["data"]["state"] == "COMPLETED"
        assert decided["data"]["completed_at"] is not None
        assert decided["data"]["play_all_sets"] is False
        assert decided["data"]["match_sets"][2]["state"] == "NOT_STARTED"

        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        final = bracket.rounds[1].matches[0]
        assert final.stage_item_input1_id == winner_input_id


@pytest.mark.asyncio(loop_scope="session")
async def test_best_of_n_start_rejected_on_decided_match(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=False),
        _four_team_elimination(auth_context) as stage_item_id,
    ):
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi = bracket.rounds[0].matches[0]
        await complete_match(auth_context, semi.id, semi.match_sets[0].id, score1=21, score2=15)
        await complete_match(auth_context, semi.id, semi.match_sets[1].id, score1=21, score2=10)

        response = await send_tournament_request(
            HTTPMethod.POST, f"matches/{semi.id}/start", auth_context
        )
        assert response == {"detail": "Cannot start: the match is already decided"}


@pytest.mark.asyncio(loop_scope="session")
async def test_best_of_n_reopen_regresses_early_ended_match(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Reopening the decisive set of an early-ended match puts it back in progress with the
    remaining set startable again."""
    tournament_id = auth_context.tournament.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=False),
        _four_team_elimination(auth_context) as stage_item_id,
    ):
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi = bracket.rounds[0].matches[0]
        await complete_match(auth_context, semi.id, semi.match_sets[0].id, score1=21, score2=15)
        await complete_match(auth_context, semi.id, semi.match_sets[1].id, score1=21, score2=10)

        reopened = await send_tournament_request(
            HTTPMethod.POST, f"matches/{semi.id}/reopen", auth_context
        )
        assert reopened["data"]["state"] == "IN_PROGRESS"
        assert reopened["data"]["completed_at"] is None
        assert reopened["data"]["match_sets"][1]["state"] == "IN_PROGRESS"

        # Flip the reopened set so the match stands 1-1 after ending it: the third set
        # must be startable again.
        await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{semi.id}/sets/{semi.match_sets[1].id}/score-edit",
            auth_context,
            json={"stage_item_input1_score": 10, "stage_item_input2_score": 21},
        )
        levelled = await send_tournament_request(
            HTTPMethod.POST, f"matches/{semi.id}/end", auth_context
        )
        assert levelled["data"]["state"] == "IN_PROGRESS"

        third_started = await send_tournament_request(
            HTTPMethod.POST, f"matches/{semi.id}/start", auth_context
        )
        assert third_started["data"]["match_sets"][2]["state"] == "IN_PROGRESS"


@pytest.mark.asyncio(loop_scope="session")
async def test_best_of_n_score_edit_undecides_early_ended_match(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Editing a set score so the majority evaporates regresses the early-ended match to
    in-progress via derivation; no set rows are deleted."""
    tournament_id = auth_context.tournament.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=False),
        _four_team_elimination(auth_context) as stage_item_id,
    ):
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi = bracket.rounds[0].matches[0]
        await complete_match(auth_context, semi.id, semi.match_sets[0].id, score1=21, score2=15)
        await complete_match(auth_context, semi.id, semi.match_sets[1].id, score1=21, score2=10)

        undecided = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{semi.id}/sets/{semi.match_sets[1].id}/score-edit",
            auth_context,
            json={"stage_item_input1_score": 10, "stage_item_input2_score": 10},
        )
        assert undecided["data"]["state"] == "IN_PROGRESS"
        assert undecided["data"]["completed_at"] is None
        assert len(undecided["data"]["match_sets"]) == 3
        assert undecided["data"]["match_sets"][2]["state"] == "NOT_STARTED"


@pytest.mark.asyncio(loop_scope="session")
async def test_best_of_n_surplus_completed_sets_keep_counting(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A history-rewriting edit that makes the match "really" decided after two sets leaves the
    surplus third set recorded and counting toward set statistics; the winner is unaffected."""
    tournament_id = auth_context.tournament.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=False),
        _four_team_elimination(auth_context) as stage_item_id,
    ):
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi = bracket.rounds[0].matches[0]
        winner_input_id = semi.stage_item_input1_id

        # A full three-setter: input1 wins sets 1 and 3, input2 wins set 2.
        await complete_match(auth_context, semi.id, semi.match_sets[0].id, score1=21, score2=15)
        await complete_match(auth_context, semi.id, semi.match_sets[1].id, score1=10, score2=21)
        await complete_match(auth_context, semi.id, semi.match_sets[2].id, score1=21, score2=10)

        # Correction: input1 actually won set 2 as well, so the match was decided after two
        # sets and set 3 is surplus history.
        edited = await send_tournament_request(
            HTTPMethod.POST,
            f"matches/{semi.id}/sets/{semi.match_sets[1].id}/score-edit",
            auth_context,
            json={"stage_item_input1_score": 21, "stage_item_input2_score": 19},
        )
        assert edited["data"]["state"] == "COMPLETED"
        assert edited["data"]["completed_at"] is not None
        assert len(edited["data"]["match_sets"]) == 3
        assert all(s["state"] == "COMPLETED" for s in edited["data"]["match_sets"])

        # The surplus set still counts toward set statistics: the winner is 3-0 up in sets.
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        winner_input = next(i for i in bracket.inputs if i.id == winner_input_id)
        assert winner_input.set_difference == 3

        final = bracket.rounds[1].matches[0]
        assert final.stage_item_input1_id == winner_input_id


@pytest.mark.asyncio(loop_scope="session")
async def test_play_all_sets_on_still_requires_every_set(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """With "play out all sets" on (the pre-existing behaviour), a 2-0 lead in a Bo3 does not
    complete the match; the third set must be played."""
    tournament_id = auth_context.tournament.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=True),
        _four_team_elimination(auth_context) as stage_item_id,
    ):
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi = bracket.rounds[0].matches[0]
        await complete_match(auth_context, semi.id, semi.match_sets[0].id, score1=21, score2=15)
        two_up = await complete_match(
            auth_context, semi.id, semi.match_sets[1].id, score1=21, score2=10
        )
        assert two_up["data"]["state"] == "IN_PROGRESS"
        assert two_up["data"]["completed_at"] is None
        assert two_up["data"]["play_all_sets"] is True

        third = await complete_match(
            auth_context, semi.id, semi.match_sets[2].id, score1=21, score2=10
        )
        assert third["data"]["state"] == "COMPLETED"


@pytest.mark.asyncio(loop_scope="session")
async def test_ranking_play_all_sets_change_requires_force_when_active(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Flipping `play_all_sets` off on a ranking with an early-decided-but-not-completed Bo3
    match (2-0, third set unplayed and IN_PROGRESS under play-all-sets) is refused with a 409
    unless forced, exactly like the existing `num_sets` gate. Forcing it through completes the
    match on the spot: `completed_at` is stamped and the winner advances into the elimination
    final -- the reconciliation path (#270) picking up where the per-match best-of-n
    auto-completion path (#267) leaves off."""
    tournament_id = auth_context.tournament.id
    ranking_id = auth_context.ranking.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=True),
        _four_team_elimination(auth_context) as stage_item_id,
    ):
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi = bracket.rounds[0].matches[0]
        winner_input_id = semi.stage_item_input1_id
        assert len(semi.match_sets) == 3

        await complete_match(auth_context, semi.id, semi.match_sets[0].id, score1=21, score2=15)
        two_up = await complete_match(
            auth_context, semi.id, semi.match_sets[1].id, score1=21, score2=10
        )
        assert two_up["data"]["state"] == "IN_PROGRESS"
        assert two_up["data"]["completed_at"] is None

        body = RankingMatchPointsBody(num_sets=3, play_all_sets=False).model_dump(mode="json")

        blocked = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_id}", auth_context, json=body
        )
        assert "force=true" in blocked["detail"]

        # Unaffected by the gate: the match is untouched by a rejected request.
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        assert bracket.rounds[0].matches[0].state == MatchState.IN_PROGRESS

        forced = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_id}?force=true", auth_context, json=body
        )
        assert forced["success"] is True

        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi_after = bracket.rounds[0].matches[0]
        assert semi_after.state == MatchState.COMPLETED
        assert semi_after.completed_at is not None
        assert semi_after.match_sets[2].state == MatchSetState.NOT_STARTED

        final = bracket.rounds[1].matches[0]
        assert final.stage_item_input1_id == winner_input_id


@pytest.mark.asyncio(loop_scope="session")
async def test_ranking_play_all_sets_change_needs_no_force_without_active_sets(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A ranking with no started sets never needs `force=true`, mirroring `num_sets`."""
    ranking_id = auth_context.ranking.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=True),
        _four_team_elimination(auth_context),
    ):
        body = RankingMatchPointsBody(num_sets=3, play_all_sets=False).model_dump(mode="json")
        response = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_id}", auth_context, json=body
        )
        assert response["success"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_ranking_play_all_sets_change_on_regresses_early_ended_match(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Flipping `play_all_sets` back on for a ranking with a best-of-n-decided match (2-0,
    third set never played) regresses that match to in-progress: `completed_at` is cleared and
    the previously-blocked third set becomes startable again."""
    tournament_id = auth_context.tournament.id
    ranking_id = auth_context.ranking.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=False),
        _four_team_elimination(auth_context) as stage_item_id,
    ):
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi = bracket.rounds[0].matches[0]

        await complete_match(auth_context, semi.id, semi.match_sets[0].id, score1=21, score2=15)
        decided = await complete_match(
            auth_context, semi.id, semi.match_sets[1].id, score1=21, score2=10
        )
        assert decided["data"]["state"] == "COMPLETED"
        assert decided["data"]["completed_at"] is not None

        body = RankingMatchPointsBody(num_sets=3, play_all_sets=True).model_dump(mode="json")

        blocked = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_id}", auth_context, json=body
        )
        assert "force=true" in blocked["detail"]

        forced = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_id}?force=true", auth_context, json=body
        )
        assert forced["success"] is True

        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi_after = bracket.rounds[0].matches[0]
        assert semi_after.state == MatchState.IN_PROGRESS
        assert semi_after.completed_at is None

        third_started = await send_tournament_request(
            HTTPMethod.POST, f"matches/{semi.id}/start", auth_context
        )
        assert third_started["data"]["match_sets"][2]["state"] == "IN_PROGRESS"


@pytest.mark.asyncio(loop_scope="session")
async def test_ranking_draws_allowed_change_never_gated(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """`draws_allowed` has no derived-state impact, so it is never gated behind `force`, even
    on a ranking with active sets."""
    tournament_id = auth_context.tournament.id
    ranking_id = auth_context.ranking.id
    async with (
        _best_of_three_ranking(auth_context, play_all_sets=True),
        _four_team_elimination(auth_context) as stage_item_id,
    ):
        bracket = await _get_stage_item_details(tournament_id, stage_item_id)
        semi = bracket.rounds[0].matches[0]
        await complete_match(auth_context, semi.id, semi.match_sets[0].id, score1=21, score2=15)

        body = RankingMatchPointsBody(
            num_sets=3, play_all_sets=True, draws_allowed=False
        ).model_dump(mode="json")
        response = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{ranking_id}", auth_context, json=body
        )
        assert response["success"] is True


@asynccontextmanager
async def _best_of_three_ranking(
    auth_context: AuthContext, *, play_all_sets: bool = True
) -> AsyncIterator[None]:
    """Temporarily configure the session-scoped ranking as best-of-3."""
    ranking_id = auth_context.ranking.id
    await database.execute(
        query=rankings.update()
        .where(rankings.c.id == ranking_id)
        .values(num_sets=3, play_all_sets=play_all_sets),
    )
    try:
        yield
    finally:
        await database.execute(
            query=rankings.update()
            .where(rankings.c.id == ranking_id)
            .values(num_sets=1, play_all_sets=True),
        )


@asynccontextmanager
async def _draws_disallowed_ranking(auth_context: AuthContext) -> AsyncIterator[None]:
    """Temporarily configure the session-scoped ranking to disallow draws."""
    ranking_id = auth_context.ranking.id
    await database.execute(
        query=rankings.update().where(rankings.c.id == ranking_id).values(draws_allowed=False),
    )
    try:
        yield
    finally:
        await database.execute(
            query=rankings.update().where(rankings.c.id == ranking_id).values(draws_allowed=True),
        )


@asynccontextmanager
async def _four_team_elimination(auth_context: AuthContext) -> AsyncIterator[StageItemId]:
    """A 4-team single elimination stage item (two semis feeding a final), built and torn down."""
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
            yield stage_item.id
        finally:
            await sql_delete_stage_item_with_foreign_keys(stage_item.id)


async def _get_stage_item_details(
    tournament_id: TournamentId, stage_item_id: StageItemId
) -> StageItemWithRounds:
    details = await get_full_tournament_details(tournament_id)
    return next(si for s in details for si in s.stage_items if si.id == stage_item_id)


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
async def _simple_match(auth_context: AuthContext) -> AsyncIterator[Match]:
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
