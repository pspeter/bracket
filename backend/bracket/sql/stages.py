from bracket.database import database
from bracket.models.db.stage import Stage
from bracket.models.db.util import StageWithStageItems
from bracket.sql.match_sets import MATCH_SETS_SUBQUERY
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
    match_sets = MATCH_SETS_SUBQUERY

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
                to_json(ref_sii) AS referee,
                s2.level_id AS level_id,
                rnk.side_switch_every_n_points AS side_switch_every_n_points,
                rnk.num_sets AS num_sets,
                rnk.max_points AS max_points,
                rnk.last_set_max_points AS last_set_max_points,
                rnk.two_point_advantage AS two_point_advantage,
                {match_sets}
            FROM matches
            LEFT JOIN inputs_with_teams sii1 on sii1.id = matches.stage_item_input1_id
            LEFT JOIN inputs_with_teams sii2 on sii2.id = matches.stage_item_input2_id
            LEFT JOIN rounds r on matches.round_id = r.id
            LEFT JOIN stage_items si on r.stage_item_id = si.id
            LEFT JOIN stages s2 on s2.id = si.stage_id
            LEFT JOIN rankings rnk on rnk.id = si.ranking_id
            LEFT JOIN courts c on matches.court_id = c.id
            LEFT JOIN inputs_with_teams ref_sii on ref_sii.id = matches.referee_stage_item_input_id
            WHERE s2.tournament_id = :tournament_id
        ), rounds_with_matches AS (
            SELECT DISTINCT ON (rounds.id)
                rounds.*,
                to_json(array_agg(m.* ORDER BY m.id)) AS matches
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
                to_json(array_agg(r.* ORDER BY r.id)) AS rounds
            FROM stage_items
            JOIN stages st on stage_items.stage_id = st.id
            LEFT JOIN rounds_with_matches r on r.stage_item_id = stage_items.id
            WHERE st.tournament_id = :tournament_id
            {stage_item_filter}
            GROUP BY stage_items.id
        ), stage_items_with_inputs AS (
            SELECT DISTINCT ON (stage_items.id)
                stage_items.id,
                to_json(array_agg(sii ORDER BY sii.slot)) AS inputs
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
        SELECT stages.*, to_json(array_agg(r.* ORDER BY r.name)) AS stage_items
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
    level_id: LevelId | None = None,
) -> Stage:
    query = """
        INSERT INTO stages (created, name, tournament_id, level_id)
        VALUES (NOW(), :name, :tournament_id, :level_id)
        RETURNING *
        """
    result = await database.fetch_one(
        query=query,
        values={
            "tournament_id": tournament_id,
            "name": name,
            "level_id": level_id,
        },
    )

    if result is None:
        raise ValueError("Could not create stage")

    return Stage.model_validate(dict(result._mapping))
