from typing import Literal, cast

from bracket.database import database
from bracket.models.db.stage import Stage
from bracket.models.db.util import StageWithStageItems
from bracket.utils.id_types import LevelId, RoundId, StageId, StageItemId, TournamentId
from bracket.utils.types import dict_without_none


async def get_full_tournament_details(
    tournament_id: TournamentId,
    round_id: RoundId | None = None,
    stage_id: StageId | None = None,
    stage_item_ids: set[StageItemId] | None = None,
) -> list[StageWithStageItems]:
    round_filter = "AND rounds.id = :round_id" if round_id is not None else ""
    stage_filter = "AND stages.id = :stage_id" if stage_id is not None else ""
    stage_item_filter = (
        "AND stage_items.id = any(:stage_item_ids)" if stage_item_ids is not None else ""
    )
    stage_item_filter_join = (
        "LEFT JOIN stage_items on stages.id = stage_items.stage_id"
        if stage_item_ids is not None
        else ""
    )

    query = f"""
        WITH inputs_with_teams AS (
            SELECT DISTINCT ON (stage_item_inputs.id)
                stage_item_inputs.*,
                to_json(t.*) AS team
            FROM stage_item_inputs
            JOIN stage_items on stage_item_inputs.stage_item_id = stage_items.id
            LEFT JOIN stages s2 on s2.id = stage_items.stage_id
            LEFT JOIN teams t on t.id = stage_item_inputs.team_id
            WHERE s2.tournament_id = :tournament_id
            {stage_item_filter}
            GROUP BY stage_item_inputs.id, t.id
        ), matches_with_inputs AS (
            SELECT DISTINCT ON (matches.id)
                matches.*,
                to_json(sii1) as stage_item_input1,
                to_json(sii2) as stage_item_input2,
                to_json(c) as court,
                to_json(ref_sii) AS referee
            FROM matches
            LEFT JOIN inputs_with_teams sii1 on sii1.id = matches.stage_item_input1_id
            LEFT JOIN inputs_with_teams sii2 on sii2.id = matches.stage_item_input2_id
            LEFT JOIN rounds r on matches.round_id = r.id
            LEFT JOIN stage_items si on r.stage_item_id = si.id
            LEFT JOIN stages s2 on s2.id = si.stage_id
            LEFT JOIN courts c on matches.court_id = c.id
            LEFT JOIN inputs_with_teams ref_sii on ref_sii.id = matches.referee_stage_item_input_id
            WHERE s2.tournament_id = :tournament_id
        ), rounds_with_matches AS (
            SELECT DISTINCT ON (rounds.id)
                rounds.*,
                to_json(array_agg(m.*)) AS matches
            FROM rounds
            LEFT JOIN matches_with_inputs m on m.round_id = rounds.id
            LEFT JOIN stage_items si on rounds.stage_item_id = si.id
            LEFT JOIN stages s2 on s2.id = si.stage_id
            WHERE s2.tournament_id = :tournament_id
            {round_filter}
            GROUP BY rounds.id
        ), stage_items_with_rounds AS (
            SELECT DISTINCT ON (stage_items.id)
                stage_items.*,
                to_json(array_agg(r.*)) AS rounds
            FROM stage_items
            JOIN stages st on stage_items.stage_id = st.id
            LEFT JOIN rounds_with_matches r on r.stage_item_id = stage_items.id
            WHERE st.tournament_id = :tournament_id
            {stage_item_filter}
            GROUP BY stage_items.id
        ), stage_items_with_inputs AS (
            SELECT DISTINCT ON (stage_items.id)
                stage_items.id,
                to_json(array_agg(sii)) AS inputs
            FROM stage_items
            LEFT JOIN inputs_with_teams sii ON stage_items.id = sii.stage_item_id
            WHERE sii.tournament_id = :tournament_id
            {stage_item_filter}
            GROUP BY stage_items.id
            ORDER BY stage_items.id
        ), stage_items_with_rounds_and_inputs AS (
            SELECT stage_items.*, stage_items_with_inputs.inputs, stage_items_with_rounds.rounds
            FROM stage_items
            JOIN stage_items_with_rounds ON stage_items_with_rounds.id = stage_items.id
            LEFT JOIN stage_items_with_inputs ON stage_items_with_inputs.id = stage_items.id
            ORDER BY stage_items.name
        )
        SELECT stages.*, to_json(array_agg(r.*)) AS stage_items
        FROM stages
        LEFT JOIN stage_items_with_rounds_and_inputs r on stages.id = r.stage_id
        {stage_item_filter_join}
        WHERE stages.tournament_id = :tournament_id
        {stage_filter}
        {stage_item_filter}
        GROUP BY stages.id
        ORDER BY stages.id
    """
    values = dict_without_none(
        {
            "tournament_id": tournament_id,
            "round_id": round_id,
            "stage_id": stage_id,
            "stage_item_ids": stage_item_ids,
        }
    )
    result = await database.fetch_all(query=query, values=values)
    return [StageWithStageItems.model_validate(dict(x._mapping)) for x in result]


async def sql_delete_stage(tournament_id: TournamentId, stage_id: StageId) -> None:
    from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys

    async with database.transaction():
        stage_item_rows = await database.fetch_all(
            query="SELECT id FROM stage_items WHERE stage_id = :stage_id",
            values={"stage_id": stage_id},
        )
        for row in stage_item_rows:
            await sql_delete_stage_item_with_foreign_keys(StageItemId(row["id"]))

        query = """
            DELETE FROM stages
            WHERE stages.id = :stage_id
            AND stages.tournament_id = :tournament_id
            """
        await database.execute(
            query=query, values={"stage_id": stage_id, "tournament_id": tournament_id}
        )


async def sql_create_stage(
    tournament_id: TournamentId,
    name: str = "Stage",
    *,
    is_active: bool = False,
    level_id: LevelId | None = None,
) -> Stage:
    query = """
        INSERT INTO stages (created, is_active, name, tournament_id, level_id)
        VALUES (NOW(), :is_active, :name, :tournament_id, :level_id)
        RETURNING *
        """
    result = await database.fetch_one(
        query=query,
        values={
            "tournament_id": tournament_id,
            "name": name,
            "is_active": is_active,
            "level_id": level_id,
        },
    )

    if result is None:
        raise ValueError("Could not create stage")

    return Stage.model_validate(dict(result._mapping))


async def sql_has_active_stage(tournament_id: TournamentId) -> bool:
    query = """
        SELECT EXISTS(
            SELECT 1 FROM stages
            WHERE tournament_id = :tournament_id
            AND is_active IS TRUE
        )
    """
    result = await database.fetch_val(query=query, values={"tournament_id": tournament_id})
    return bool(result)


async def get_next_stage_in_tournament(
    tournament_id: TournamentId,
    direction: Literal["next", "previous"],
    level_id: LevelId | None = None,
) -> StageId | None:
    select_query = """
        SELECT id
        FROM stages
        WHERE
            CASE WHEN :direction='next'
            THEN (
                id > COALESCE(
                    (
                        SELECT id FROM stages
                        WHERE is_active IS TRUE
                        AND stages.tournament_id = :tournament_id
                        AND stages.level_id IS NOT DISTINCT FROM :level_id
                        ORDER BY id ASC
                        LIMIT 1
                    ),
                    -1
                )
            )
            ELSE (
                id < COALESCE(
                    (
                        SELECT id FROM stages
                        WHERE is_active IS TRUE
                        AND stages.tournament_id = :tournament_id
                        AND stages.level_id IS NOT DISTINCT FROM :level_id
                        ORDER BY id DESC
                        LIMIT 1
                    ),
                    10000000000
                )
            )
            END
        AND stages.tournament_id = :tournament_id
        AND stages.level_id IS NOT DISTINCT FROM :level_id
        AND is_active IS FALSE
        ORDER BY
            CASE WHEN :direction='next' THEN id END ASC,
            CASE WHEN NOT :direction='next' THEN id END DESC
    """
    return cast(
        "StageId | None",
        await database.execute(
            query=select_query,
            values={
                "tournament_id": tournament_id,
                "direction": direction,
                "level_id": level_id,
            },
        ),
    )


async def sql_activate_next_stage(
    new_active_stage_id: StageId,
    tournament_id: TournamentId,
    level_id: LevelId | None = None,
) -> None:
    update_query = """
        UPDATE stages
        SET is_active = (stages.id = :new_active_stage_id)
        WHERE stages.tournament_id = :tournament_id
        AND stages.level_id IS NOT DISTINCT FROM :level_id
    """
    await database.execute(
        query=update_query,
        values={
            "tournament_id": tournament_id,
            "new_active_stage_id": new_active_stage_id,
            "level_id": level_id,
        },
    )
