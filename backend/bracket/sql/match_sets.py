from bracket.database import database
from bracket.models.db.match import MatchSet, MatchSetBody
from bracket.utils.id_types import MatchId, MatchSetId, RankingId

# SQL fragment that aggregates a match's sets into a JSON array, ordered by set number.
# Correlates on the outer ``matches`` row, so callers must alias the matches table as ``matches``.
MATCH_SETS_SUBQUERY = """
    (
        SELECT COALESCE(json_agg(ms.* ORDER BY ms.set_number), '[]'::json)
        FROM match_sets ms
        WHERE ms.match_id = matches.id
    ) AS match_sets
"""


async def get_sets_for_match(match_id: MatchId) -> list[MatchSet]:
    query = """
        SELECT * FROM match_sets
        WHERE match_id = :match_id
        ORDER BY set_number
        """
    rows = await database.fetch_all(query=query, values={"match_id": match_id})
    return [MatchSet.model_validate(dict(row._mapping)) for row in rows]


async def sql_get_match_set(match_set_id: MatchSetId) -> MatchSet | None:
    query = "SELECT * FROM match_sets WHERE id = :match_set_id"
    row = await database.fetch_one(query=query, values={"match_set_id": match_set_id})
    return MatchSet.model_validate(dict(row._mapping)) if row is not None else None


async def sql_create_match_sets(match_id: MatchId, num_sets: int) -> None:
    """Insert ``num_sets`` NOT_STARTED sets (set_number 1..num_sets) for a match."""
    for set_number in range(1, max(num_sets, 1) + 1):
        await database.execute(
            query="""
                INSERT INTO match_sets (match_id, set_number, state)
                VALUES (:match_id, :set_number, 'NOT_STARTED')
            """,
            values={"match_id": match_id, "set_number": set_number},
        )


async def sql_update_match_set(match_set_id: MatchSetId, body: MatchSetBody) -> None:
    query = """
        UPDATE match_sets
        SET stage_item_input1_score = :stage_item_input1_score,
            stage_item_input2_score = :stage_item_input2_score,
            state = :state
        WHERE id = :match_set_id
        """
    await database.execute(
        query=query,
        values={
            "match_set_id": match_set_id,
            "stage_item_input1_score": body.stage_item_input1_score,
            "stage_item_input2_score": body.stage_item_input2_score,
            "state": body.state.value,
        },
    )


async def sql_add_trailing_sets(
    match_id: MatchId, from_set_number: int, to_set_number: int
) -> None:
    for set_number in range(from_set_number, to_set_number + 1):
        await database.execute(
            query="""
                INSERT INTO match_sets (match_id, set_number, state)
                VALUES (:match_id, :set_number, 'NOT_STARTED')
                ON CONFLICT (match_id, set_number) DO NOTHING
            """,
            values={"match_id": match_id, "set_number": set_number},
        )


async def sql_delete_trailing_sets(match_id: MatchId, keep_up_to_set_number: int) -> None:
    await database.execute(
        query="""
            DELETE FROM match_sets
            WHERE match_id = :match_id AND set_number > :keep_up_to
        """,
        values={"match_id": match_id, "keep_up_to": keep_up_to_set_number},
    )


async def sql_get_match_ids_for_ranking(ranking_id: RankingId) -> list[MatchId]:
    query = """
        SELECT matches.id
        FROM matches
        JOIN rounds ON rounds.id = matches.round_id
        JOIN stage_items ON stage_items.id = rounds.stage_item_id
        WHERE stage_items.ranking_id = :ranking_id
        """
    rows = await database.fetch_all(query=query, values={"ranking_id": ranking_id})
    return [MatchId(row._mapping["id"]) for row in rows]


async def sql_ranking_has_active_sets(ranking_id: RankingId) -> bool:
    """True if any match under this ranking has a set that is IN_PROGRESS or COMPLETED."""
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM match_sets ms
            JOIN matches ON matches.id = ms.match_id
            JOIN rounds ON rounds.id = matches.round_id
            JOIN stage_items ON stage_items.id = rounds.stage_item_id
            WHERE stage_items.ranking_id = :ranking_id
              AND ms.state IN ('IN_PROGRESS', 'COMPLETED')
        ) AS has_active
        """
    row = await database.fetch_one(query=query, values={"ranking_id": ranking_id})
    return bool(row._mapping["has_active"]) if row is not None else False


async def sql_resize_sets_for_ranking(
    ranking_id: RankingId, old_num_sets: int, new_num_sets: int
) -> None:
    """Add trailing NOT_STARTED sets or delete trailing sets for every match of a ranking."""
    if new_num_sets == old_num_sets:
        return

    match_ids = await sql_get_match_ids_for_ranking(ranking_id)
    for match_id in match_ids:
        if new_num_sets > old_num_sets:
            await sql_add_trailing_sets(match_id, old_num_sets + 1, new_num_sets)
        else:
            await sql_delete_trailing_sets(match_id, new_num_sets)
