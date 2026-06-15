from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.models.db.user import UserPublic
from bracket.routes.auth import user_authenticated_for_tournament
from bracket.routes.models import RefereesResponse
from bracket.sql.referees import sql_get_referees
from bracket.utils.id_types import TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.get("/tournaments/{tournament_id}/referees", response_model=RefereesResponse)
async def get_referees(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> RefereesResponse:
    return RefereesResponse(data=await sql_get_referees(tournament_id))
