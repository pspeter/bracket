from bracket.database import database
from bracket.logic.planning.template import Blueprint, BlueprintInput
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyEmpty,
    StageItemInputCreateBodyTentative,
)
from bracket.models.db.util import StageWithStageItems
from bracket.sql.shared import sql_delete_stage_item_matches, sql_delete_stage_item_relations
from bracket.sql.stage_items import sql_create_stage_item_with_inputs, sql_delete_stage_item
from bracket.sql.stages import get_full_tournament_details, sql_create_stage
from bracket.utils.id_types import StageItemId, TournamentId


def build_stage_item_inputs(
    inputs: list[BlueprintInput],
    stage_item_ids_by_name: dict[str, StageItemId],
) -> list[StageItemInputCreateBodyEmpty | StageItemInputCreateBodyTentative]:
    created_inputs: list[StageItemInputCreateBodyEmpty | StageItemInputCreateBodyTentative] = []

    for input_ in inputs:
        if input_.winner_from is None:
            created_inputs.append(StageItemInputCreateBodyEmpty(slot=input_.slot))
            continue

        winner_from_stage_item_id = stage_item_ids_by_name.get(input_.winner_from)
        if winner_from_stage_item_id is None or input_.winner_position is None:
            raise ValueError(f"Could not resolve template input source {input_.winner_from}")

        created_inputs.append(
            StageItemInputCreateBodyTentative(
                slot=input_.slot,
                winner_from_stage_item_id=winner_from_stage_item_id,
                winner_position=input_.winner_position,
            )
        )

    return created_inputs


async def replace_stages_from_template(
    tournament_id: TournamentId, blueprint: Blueprint
) -> list[StageWithStageItems]:
    existing_stages = await get_full_tournament_details(tournament_id)

    async with database.transaction():
        # Matches may reference stage_item_inputs from other stage items (e.g. elimination
        # propagation). Delete all matches in the tournament first, then inputs/rounds,
        # mirroring sql_delete_tournament_completely.
        for stage in existing_stages:
            for stage_item in stage.stage_items:
                await sql_delete_stage_item_matches(stage_item.id)

        for stage in existing_stages:
            for stage_item in stage.stage_items:
                await sql_delete_stage_item_relations(stage_item.id)

        for stage in existing_stages:
            for stage_item in stage.stage_items:
                await sql_delete_stage_item(stage_item.id)

        await database.execute(
            query="""
                DELETE FROM stages
                WHERE tournament_id = :tournament_id
            """,
            values={"tournament_id": tournament_id},
        )

        stage_item_ids_by_name: dict[str, StageItemId] = {}
        for blueprint_stage in blueprint.stages:
            stage = await sql_create_stage(tournament_id, blueprint_stage.name)

            for blueprint_stage_item in blueprint_stage.items:
                stage_item = await sql_create_stage_item_with_inputs(
                    tournament_id,
                    StageItemWithInputsCreate(
                        stage_id=stage.id,
                        name=blueprint_stage_item.name,
                        type=blueprint_stage_item.type,
                        team_count=blueprint_stage_item.team_count,
                        inputs=build_stage_item_inputs(
                            blueprint_stage_item.inputs,
                            stage_item_ids_by_name,
                        ),
                    ),
                )
                stage_item_ids_by_name[blueprint_stage_item.name] = stage_item.id
                await build_matches_for_stage_item(stage_item, tournament_id)

    return await get_full_tournament_details(tournament_id)
