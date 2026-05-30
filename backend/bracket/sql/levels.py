from bracket.database import database
from bracket.models.db.level import Level, LevelUpdateBody
from bracket.utils.id_types import LevelId, TournamentId


async def sql_create_level(tournament_id: TournamentId, name: str, position: int) -> Level:
    query = """
        INSERT INTO levels (tournament_id, name, position)
        VALUES (:tournament_id, :name, :position)
        RETURNING *
        """
    result = await database.fetch_one(
        query=query,
        values={"tournament_id": tournament_id, "name": name, "position": position},
    )
    assert result is not None
    return Level.model_validate(result)


async def sql_get_levels_for_tournament(tournament_id: TournamentId) -> list[Level]:
    query = """
        SELECT *
        FROM levels
        WHERE tournament_id = :tournament_id
        ORDER BY position
        """
    result = await database.fetch_all(query=query, values={"tournament_id": tournament_id})
    return [Level.model_validate(x) for x in result]


async def sql_update_level(level_id: LevelId, body: LevelUpdateBody) -> Level:
    query = """
        UPDATE levels
        SET name = :name
        WHERE id = :level_id
        RETURNING *
        """
    result = await database.fetch_one(
        query=query, values={"level_id": level_id, "name": body.name}
    )
    assert result is not None
    return Level.model_validate(result)


async def sql_get_level(level_id: LevelId) -> Level | None:
    query = """
        SELECT *
        FROM levels
        WHERE id = :level_id
        """
    result = await database.fetch_one(query=query, values={"level_id": level_id})
    return Level.model_validate(result) if result is not None else None
