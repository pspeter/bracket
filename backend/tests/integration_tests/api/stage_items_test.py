import pytest

from bracket.database import database
from bracket.models.db.match import MatchState
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.schema import matches, rounds, stage_item_inputs, stage_items, stages
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import (
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_stage,
    inserted_stage_item,
    inserted_team,
)


async def create_stage_item_via_api(
    auth_context: AuthContext, stage_id: int, stage_type: StageType, team_count: int
) -> int:
    assert (
        await send_tournament_request(
            HTTPMethod.POST,
            "stage_items",
            auth_context,
            json={"type": stage_type.value, "team_count": team_count, "stage_id": stage_id},
        )
        == SUCCESS_RESPONSE
    )
    stages_in_tournament = await get_full_tournament_details(auth_context.tournament.id)
    return next(
        stage_item.id
        for stage in stages_in_tournament
        if stage.id == stage_id
        for stage_item in stage.stage_items
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage_item(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
    ):
        assert team_inserted_1.id and team_inserted_2.id
        inputs = [
            StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id).model_dump(),
            StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id).model_dump(),
        ]
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "stage_items",
                auth_context,
                json={
                    "type": StageType.SINGLE_ELIMINATION.value,
                    "team_count": 2,
                    "stage_id": stage_inserted_1.id,
                    "inputs": inputs,
                },
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(matches, 1)
        await assert_row_count_and_clear(rounds, 1)
        await assert_row_count_and_clear(stage_items, 1)
        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_stage_item(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted_1.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.DELETE, f"stage_items/{stage_item_inserted.id}", auth_context, {}
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(stages, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Optimus", "ranking_id": auth_context.ranking.id, "team_count": 4}
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.PUT, f"stage_items/{stage_item_inserted.id}", auth_context, json=body
            )
            == SUCCESS_RESPONSE
        )

        assert auth_context.tournament.id
        updated_stage_item = await get_stage_item(
            auth_context.tournament.id, stage_item_inserted.id
        )
        assert updated_stage_item.name == body["name"]


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_fails_when_not_enough_slots_are_empty(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
        inserted_team(
            DUMMY_TEAM3.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_3,
    ):
        stage_item_id = await create_stage_item_via_api(
            auth_context, stage_inserted.id, StageType.ROUND_ROBIN, 4
        )
        stage_item = await get_stage_item(auth_context.tournament.id, stage_item_id)
        inputs = sorted(stage_item.inputs, key=lambda input_: input_.slot)

        await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_id}/inputs/{inputs[0].id}",
            auth_context,
            json={"team_id": team_inserted_1.id},
        )
        await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_id}/inputs/{inputs[1].id}",
            auth_context,
            json={"team_id": team_inserted_2.id},
        )
        await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_id}/inputs/{inputs[2].id}",
            auth_context,
            json={"team_id": team_inserted_3.id},
        )

        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_id}",
            auth_context,
            json={"name": "Group Stage", "ranking_id": auth_context.ranking.id, "team_count": 2},
        )

        assert response == {"detail": "Cannot reduce player count until 2 slot(s) are empty"}
        await assert_row_count_and_clear(matches, 6)
        await assert_row_count_and_clear(rounds, 3)
        await assert_row_count_and_clear(stage_item_inputs, 4)
        await assert_row_count_and_clear(stage_items, 1)
        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_reduces_only_empty_slots_and_keeps_filled_slots(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
    ):
        stage_item_id = await create_stage_item_via_api(
            auth_context, stage_inserted.id, StageType.ROUND_ROBIN, 4
        )
        stage_item = await get_stage_item(auth_context.tournament.id, stage_item_id)
        inputs = sorted(stage_item.inputs, key=lambda input_: input_.slot)

        await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_id}/inputs/{inputs[0].id}",
            auth_context,
            json={"team_id": team_inserted_1.id},
        )
        await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_id}/inputs/{inputs[3].id}",
            auth_context,
            json={"team_id": team_inserted_2.id},
        )

        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_id}",
            auth_context,
            json={"name": "Group Stage", "ranking_id": auth_context.ranking.id, "team_count": 2},
        )

        assert response == SUCCESS_RESPONSE

        updated_stage_item = await get_stage_item(auth_context.tournament.id, stage_item_id)
        updated_inputs = sorted(updated_stage_item.inputs, key=lambda input_: input_.slot)
        assert updated_stage_item.team_count == 2
        assert [input_.slot for input_ in updated_inputs] == [1, 2]
        assert [input_.team_id for input_ in updated_inputs] == [
            team_inserted_1.id,
            team_inserted_2.id,
        ]
        assert sum(len(round_.matches) for round_ in updated_stage_item.rounds) == 1

        await assert_row_count_and_clear(matches, 1)
        await assert_row_count_and_clear(rounds, 3)
        await assert_row_count_and_clear(stage_item_inputs, 2)
        await assert_row_count_and_clear(stage_items, 1)
        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("state", [MatchState.IN_PROGRESS, MatchState.COMPLETED])
async def test_update_stage_item_fails_when_removed_empty_slot_is_in_started_match(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext, state: MatchState
) -> None:
    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as stage_inserted:
        stage_item_id = await create_stage_item_via_api(
            auth_context, stage_inserted.id, StageType.ROUND_ROBIN, 4
        )
        stage_item = await get_stage_item(auth_context.tournament.id, stage_item_id)
        input_slot_4 = next(input_ for input_ in stage_item.inputs if input_.slot == 4)
        blocking_match = next(
            match
            for round_ in stage_item.rounds
            for match in round_.matches
            if input_slot_4.id in {match.stage_item_input1_id, match.stage_item_input2_id}
        )

        await database.execute(
            query=matches.update()
            .where(matches.c.id == blocking_match.id)
            .values(
                state=state.value,
                completed_at=blocking_match.completed_at if state is MatchState.COMPLETED else None,
            )
        )

        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_id}",
            auth_context,
            json={"name": "Group Stage", "ranking_id": auth_context.ranking.id, "team_count": 3},
        )

        assert response == {
            "detail": (
                "Cannot reduce player count because slot 4 is used by matches that are already "
                "in progress or completed"
            )
        }
        await assert_row_count_and_clear(matches, 6)
        await assert_row_count_and_clear(rounds, 3)
        await assert_row_count_and_clear(stage_item_inputs, 4)
        await assert_row_count_and_clear(stage_items, 1)
        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_single_elimination_stage_item_fails_after_games_started(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_stage(
        DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as stage_inserted:
        stage_item_id = await create_stage_item_via_api(
            auth_context, stage_inserted.id, StageType.SINGLE_ELIMINATION, 4
        )
        stage_item = await get_stage_item(auth_context.tournament.id, stage_item_id)
        blocking_match = stage_item.rounds[0].matches[0]

        await database.execute(
            query=matches.update()
            .where(matches.c.id == blocking_match.id)
            .values(state=MatchState.IN_PROGRESS.value)
        )

        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_id}",
            auth_context,
            json={"name": "Bracket", "ranking_id": auth_context.ranking.id, "team_count": 2},
        )

        assert response == {
            "detail": (
                "Cannot change player count for a single-elimination stage item "
                "after games have started"
            )
        }
        await assert_row_count_and_clear(matches, 3)
        await assert_row_count_and_clear(rounds, 2)
        await assert_row_count_and_clear(stage_item_inputs, 4)
        await assert_row_count_and_clear(stage_items, 1)
        await assert_row_count_and_clear(stages, 1)
