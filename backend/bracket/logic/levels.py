from fastapi import HTTPException
from starlette import status

from bracket.sql.levels import sql_get_level_for_tournament, sql_get_levels_for_tournament
from bracket.utils.id_types import LevelId, TournamentId


async def validate_level_id_for_tournament(
    tournament_id: TournamentId, level_id: LevelId | None
) -> None:
    tournament_levels = await sql_get_levels_for_tournament(tournament_id)
    if tournament_levels and level_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="level_id is required when the tournament has levels",
        )
    if not tournament_levels and level_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="level_id must be null when the tournament has no levels",
        )
    if level_id is not None:
        level = await sql_get_level_for_tournament(tournament_id, level_id)
        if level is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not find level with id {level_id}",
            )
