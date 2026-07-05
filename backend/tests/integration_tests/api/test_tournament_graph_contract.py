"""Pins the row-shape contract of ``get_full_tournament_details``.

The query in ``bracket/sql/stages.py`` builds the ``StageWithStageItems`` tree via
``LEFT JOIN`` + ``to_json(array_agg(...))``, which means an empty aggregate (a stage with no
stage items, or a stage item with no rounds/inputs) can come back from the driver as ``[None]``
or a JSON string rather than a clean empty list. ``bracket.sql.rows.normalize_stage_row`` is
responsible for cleaning that up before the row reaches ``StageWithStageItems.model_validate``.
These tests exercise that end-to-end, through real inserts, so a regression in either the
normalizer or the query shows up here rather than only in the model's own validators.
"""

import pytest

from bracket.sql.stages import get_full_tournament_details
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_STAGE2, DUMMY_STAGE_ITEM1
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_stage, inserted_stage_item


@pytest.mark.asyncio(loop_scope="session")
async def test_stage_with_zero_stage_items_returns_empty_list(
    auth_context: AuthContext,
) -> None:
    tournament_id = auth_context.tournament.id
    async with inserted_stage(
        DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})
    ) as stage_inserted:
        [stage] = await get_full_tournament_details(tournament_id, stage_id=stage_inserted.id)

        assert stage.stage_items == []


@pytest.mark.asyncio(loop_scope="session")
async def test_stage_item_with_zero_rounds_and_inputs_returns_empty_lists(
    auth_context: AuthContext,
) -> None:
    """A freshly inserted stage item has no rounds and no inputs yet (those are only created by
    the higher-level "create stage item" flow / builder). This is the (b) case from the task: a
    stage item with zero rounds, reachable through a real (if low-level) insert path.
    """
    tournament_id = auth_context.tournament.id
    async with inserted_stage(
        DUMMY_STAGE2.model_copy(update={"tournament_id": tournament_id})
    ) as stage_inserted:
        async with inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ):
            [stage] = await get_full_tournament_details(tournament_id, stage_id=stage_inserted.id)

            assert len(stage.stage_items) == 1
            [stage_item] = stage.stage_items
            assert stage_item.rounds == []
            assert stage_item.inputs == []
