from bracket.database import database
from bracket.logic.match_sets.pointer import (
    IllegalSetTransitionError,
    apply_pointer_transition,
)
from bracket.models.db.match import MatchSet, MatchSetBody
from bracket.utils.id_types import MatchId, MatchSetId, RankingId, StageItemId

_MATCH_SET_STATE_CASE_OUTER = """
    CASE
        WHEN ms.set_number <= matches.completed_set_count THEN 'COMPLETED'
        WHEN ms.set_number = matches.completed_set_count + 1
             AND matches.current_set_in_progress THEN 'IN_PROGRESS'
        ELSE 'NOT_STARTED'
    END
"""

_MATCH_SET_STATE_CASE_JOINED = """
    CASE
        WHEN ms.set_number <= m.completed_set_count THEN 'COMPLETED'
        WHEN ms.set_number = m.completed_set_count + 1
             AND m.current_set_in_progress THEN 'IN_PROGRESS'
        ELSE 'NOT_STARTED'
    END
"""

_MATCH_SET_COLUMNS = f"""
    ms.id,
    ms.match_id,
    ms.set_number,
    ms.stage_item_input1_score,
    ms.stage_item_input2_score,
    {_MATCH_SET_STATE_CASE_JOINED} AS state
"""

# SQL fragment that aggregates a match's sets into a JSON array, ordered by set number.
# Correlates on the outer ``matches`` row, so callers must alias the matches table as ``matches``.
MATCH_SETS_SUBQUERY = f"""
    (
        SELECT COALESCE(
            json_agg(
                json_build_object(
                    'id', ms.id,
                    'match_id', ms.match_id,
                    'set_number', ms.set_number,
                    'stage_item_input1_score', ms.stage_item_input1_score,
                    'stage_item_input2_score', ms.stage_item_input2_score,
                    'state', {_MATCH_SET_STATE_CASE_OUTER}
                )
                ORDER BY ms.set_number
            ),
            '[]'::json
        )
        FROM match_sets ms
        WHERE ms.match_id = matches.id
    ) AS match_sets
"""


async def get_sets_for_match(match_id: MatchId) -> list[MatchSet]:
    query = f"""
        SELECT {_MATCH_SET_COLUMNS}
        FROM match_sets ms
        JOIN matches m ON m.id = ms.match_id
        WHERE ms.match_id = :match_id
        ORDER BY ms.set_number
        """
    rows = await database.fetch_all(query=query, values={"match_id": match_id})
    return [MatchSet.model_validate(dict(row._mapping)) for row in rows]


async def sql_get_match_set(match_set_id: MatchSetId) -> MatchSet | None:
    query = f"""
        SELECT {_MATCH_SET_COLUMNS}
        FROM match_sets ms
        JOIN matches m ON m.id = ms.match_id
        WHERE ms.id = :match_set_id
    """
    row = await database.fetch_one(query=query, values={"match_set_id": match_set_id})
    return MatchSet.model_validate(dict(row._mapping)) if row is not None else None


async def sql_create_match_sets(match_id: MatchId, num_sets: int) -> None:
    """Insert ``num_sets`` NOT_STARTED sets (set_number 1..num_sets) for a match.

    Uses a single multi-row INSERT (via ``generate_series``) rather than one statement per
    set, so match creation stays a single round-trip regardless of ``num_sets``.
    """
    await database.execute(
        query="""
            INSERT INTO match_sets (match_id, set_number)
            SELECT :match_id, set_number
            FROM generate_series(1, CAST(:num_sets AS integer)) AS set_number
        """,
        values={"match_id": match_id, "num_sets": max(num_sets, 1)},
    )


async def sql_update_match_set(
    match_id: MatchId, match_set_id: MatchSetId, body: MatchSetBody
) -> None:
    """Atomically update set scores and advance the match progress pointer."""
    lock_row = await database.fetch_one(
        query="""
            SELECT
                m.completed_set_count,
                m.current_set_in_progress,
                ms.set_number
            FROM matches m
            JOIN match_sets ms ON ms.match_id = m.id
            WHERE m.id = :match_id AND ms.id = :match_set_id
            FOR UPDATE OF m
        """,
        values={"match_id": match_id, "match_set_id": match_set_id},
    )
    if lock_row is None:
        raise ValueError(f"Could not find set {match_set_id} for match {match_id}")

    completed_set_count = int(lock_row._mapping["completed_set_count"])
    current_set_in_progress = bool(lock_row._mapping["current_set_in_progress"])
    set_number = int(lock_row._mapping["set_number"])

    try:
        new_completed, new_in_progress = apply_pointer_transition(
            completed_set_count,
            current_set_in_progress,
            set_number,
            body.state,
        )
    except IllegalSetTransitionError:
        raise

    await database.execute(
        query="""
            UPDATE match_sets
            SET stage_item_input1_score = :stage_item_input1_score,
                stage_item_input2_score = :stage_item_input2_score
            WHERE id = :match_set_id
        """,
        values={
            "match_set_id": match_set_id,
            "stage_item_input1_score": body.stage_item_input1_score,
            "stage_item_input2_score": body.stage_item_input2_score,
        },
    )

    if (
        new_completed != completed_set_count
        or new_in_progress != current_set_in_progress
    ):
        await database.execute(
            query="""
                UPDATE matches
                SET completed_set_count = :completed_set_count,
                    current_set_in_progress = :current_set_in_progress
                WHERE id = :match_id
            """,
            values={
                "match_id": match_id,
                "completed_set_count": new_completed,
                "current_set_in_progress": new_in_progress,
            },
        )


async def sql_add_trailing_sets(
    match_id: MatchId, from_set_number: int, to_set_number: int
) -> None:
    # Single multi-row insert (via generate_series) so a resize stays one round-trip per match,
    # matching how sql_create_match_sets pre-populates sets at match creation.
    await database.execute(
        query="""
            INSERT INTO match_sets (match_id, set_number)
            SELECT :match_id, set_number
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
    await database.execute(
        query="""
            UPDATE matches
            SET completed_set_count = LEAST(completed_set_count, :keep_up_to),
                current_set_in_progress = CASE
                    WHEN completed_set_count >= :keep_up_to THEN FALSE
                    ELSE current_set_in_progress
                END
            WHERE id = :match_id
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
    """True if any match under this ranking has started or completed at least one set."""
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM matches
            JOIN rounds ON rounds.id = matches.round_id
            JOIN stage_items ON stage_items.id = rounds.stage_item_id
            WHERE stage_items.ranking_id = :ranking_id
              AND (
                  matches.completed_set_count > 0
                  OR matches.current_set_in_progress
              )
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
