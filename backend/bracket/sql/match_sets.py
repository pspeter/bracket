from bracket.database import database
from bracket.models.db.match import MatchSet, MatchSetBody
from bracket.utils.id_types import MatchId, MatchSetId, RankingId, StageItemId

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
    """Insert ``num_sets`` NOT_STARTED sets (set_number 1..num_sets) for a match.

    Uses a single multi-row INSERT (via ``generate_series``) rather than one statement per
    set, so match creation stays a single round-trip regardless of ``num_sets``.
    """
    await database.execute(
        query="""
            INSERT INTO match_sets (match_id, set_number, state)
            SELECT :match_id, set_number, 'NOT_STARTED'
            FROM generate_series(1, :num_sets) AS set_number
        """,
        values={"match_id": match_id, "num_sets": max(num_sets, 1)},
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
    # Single multi-row insert (via generate_series) so a resize stays one round-trip per match,
    # matching how sql_create_match_sets pre-populates sets at match creation.
    await database.execute(
        query="""
            INSERT INTO match_sets (match_id, set_number, state)
            SELECT :match_id, set_number, 'NOT_STARTED'
            FROM generate_series(
                CAST(:from_set_number AS integer), CAST(:to_set_number AS integer)
            ) AS set_number
            ON CONFLICT (match_id, set_number) DO NOTHING
        """,
        values={
            "match_id": match_id,
            "from_set_number": from_set_number,
            "to_set_number": to_set_number,
        },
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


async def sql_get_match_ids_for_stage_item(stage_item_id: StageItemId) -> list[MatchId]:
    query = """
        SELECT matches.id
        FROM matches
        JOIN rounds ON rounds.id = matches.round_id
        WHERE rounds.stage_item_id = :stage_item_id
        """
    rows = await database.fetch_all(query=query, values={"stage_item_id": stage_item_id})
    return [MatchId(row._mapping["id"]) for row in rows]


async def _resize_sets_for_matches(
    match_ids: list[MatchId], old_num_sets: int, new_num_sets: int
) -> None:
    """Add trailing NOT_STARTED sets or delete trailing sets for the given matches."""
    for match_id in match_ids:
        if new_num_sets > old_num_sets:
            await sql_add_trailing_sets(match_id, old_num_sets + 1, new_num_sets)
        else:
            await sql_delete_trailing_sets(match_id, new_num_sets)


async def sql_resize_sets_for_ranking(
    ranking_id: RankingId, old_num_sets: int, new_num_sets: int
) -> None:
    """Add trailing NOT_STARTED sets or delete trailing sets for every match of a ranking."""
    if new_num_sets == old_num_sets:
        return

    match_ids = await sql_get_match_ids_for_ranking(ranking_id)
    await _resize_sets_for_matches(match_ids, old_num_sets, new_num_sets)


async def sql_resize_sets_for_stage_item(
    stage_item_id: StageItemId, old_num_sets: int, new_num_sets: int
) -> None:
    """Add trailing NOT_STARTED sets or delete trailing sets for every match of a stage item."""
    if new_num_sets == old_num_sets:
        return

    match_ids = await sql_get_match_ids_for_stage_item(stage_item_id)
    await _resize_sets_for_matches(match_ids, old_num_sets, new_num_sets)
