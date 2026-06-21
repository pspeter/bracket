from bracket.database import database
from bracket.utils.id_types import MatchId, StageItemInputId, TournamentId


async def sql_set_match_abstract_referee_slot(match_id: MatchId, slot: int) -> None:
    query = """
        UPDATE matches
        SET referee_slot = :slot
        WHERE matches.id = :match_id
        """
    await database.execute(query=query, values={"match_id": match_id, "slot": slot})


async def sql_get_referee_names(tournament_id: TournamentId) -> list[str]:
    """Return the distinct free-text referee names used within a tournament.

    Powers the "recently used names" section of the referee combobox; there is no separate
    referees table any more, so the names are derived from the matches themselves.
    """
    query = """
        SELECT DISTINCT matches.referee_name AS name
        FROM matches
        JOIN rounds ON rounds.id = matches.round_id
        JOIN stage_items ON stage_items.id = rounds.stage_item_id
        JOIN stages ON stages.id = stage_items.stage_id
        WHERE stages.tournament_id = :tournament_id
        AND matches.referee_name IS NOT NULL
        ORDER BY name
        """
    result = await database.fetch_all(query=query, values={"tournament_id": tournament_id})
    return [row._mapping["name"] for row in result]


async def sql_set_match_referee_slot(
    match_id: MatchId, stage_item_input_id: StageItemInputId | None
) -> None:
    query = """
        UPDATE matches
        SET referee_stage_item_input_id = :stage_item_input_id,
            referee_name = NULL
        WHERE matches.id = :match_id
        """
    await database.execute(
        query=query,
        values={"match_id": match_id, "stage_item_input_id": stage_item_input_id},
    )


async def sql_set_match_referee_name(match_id: MatchId, name: str) -> None:
    query = """
        UPDATE matches
        SET referee_name = :name,
            referee_stage_item_input_id = NULL
        WHERE matches.id = :match_id
        """
    await database.execute(query=query, values={"match_id": match_id, "name": name})


async def sql_clear_match_referee(match_id: MatchId) -> None:
    query = """
        UPDATE matches
        SET referee_stage_item_input_id = NULL,
            referee_name = NULL
        WHERE matches.id = :match_id
        """
    await database.execute(query=query, values={"match_id": match_id})
