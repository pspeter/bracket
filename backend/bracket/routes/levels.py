from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.models.db.level import Level, LevelUpdateBody
from bracket.models.db.user import UserPublic
from bracket.routes.auth import user_authenticated_for_tournament
from bracket.routes.models import SuccessResponse
from bracket.routes.util import level_dependency
from bracket.sql.levels import sql_update_level
from bracket.utils.id_types import LevelId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.put("/tournaments/{tournament_id}/levels/{level_id}", response_model=SuccessResponse)
async def update_level(
    tournament_id: TournamentId,
    level_id: LevelId,
    body: LevelUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    level: Level = Depends(level_dependency),
) -> SuccessResponse:
    await sql_update_level(level_id, body)
    return SuccessResponse()
