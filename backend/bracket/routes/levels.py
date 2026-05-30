from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.models.db.level import LevelUpdateBody
from bracket.models.db.user import UserPublic
from bracket.routes.auth import user_authenticated
from bracket.routes.models import SuccessResponse
from bracket.sql.levels import sql_get_level, sql_update_level
from bracket.utils.id_types import LevelId

router = APIRouter(prefix=config.api_prefix)


@router.put("/levels/{level_id}", response_model=SuccessResponse)
async def update_level(
    level_id: LevelId,
    body: LevelUpdateBody,
    user: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    level = await sql_get_level(level_id)
    if level is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Level not found",
        )
    await sql_update_level(level_id, body)
    return SuccessResponse()
