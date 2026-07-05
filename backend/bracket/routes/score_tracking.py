import asyncio

from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.models.db.tournament import LevelResponse, Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    tournament_by_score_tracking_token,
    user_authenticated_for_tournament,
)
from bracket.routes.match_access import (
    ResolvedMatch,
    resolved_match_via_token,
    resolved_scheduled_match_via_auth,
)
from bracket.routes.matches import (
    get_score_tracking_match_response,
)
from bracket.routes.models import (
    ScoreTrackingInfo,
    ScoreTrackingInfoResponse,
    ScoreTrackingMatchResponse,
)
from bracket.sql.courts import get_all_courts_in_tournament
from bracket.sql.levels import sql_get_levels_for_tournament
from bracket.sql.matches import sql_get_scheduled_matches_with_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import CourtId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.get(
    "/score-tracking/{score_tracking_token}",
    response_model=ScoreTrackingInfoResponse,
)
async def get_score_tracking_info(
    tournament: Tournament = Depends(tournament_by_score_tracking_token),
    court_id: CourtId | None = None,
) -> ScoreTrackingInfoResponse:
    matches, levels, courts = await asyncio.gather(
        sql_get_scheduled_matches_with_details(tournament.id, court_id),
        sql_get_levels_for_tournament(tournament.id),
        get_all_courts_in_tournament(tournament.id),
    )
    return ScoreTrackingInfoResponse(
        data=ScoreTrackingInfo(
            tournament_id=tournament.id,
            tournament_name=tournament.name,
            matches=matches,
            referees_enabled=tournament.referees_enabled,
            levels=[LevelResponse.model_validate(level) for level in levels],
            courts=courts,
        )
    )


@router.get(
    "/tournaments/{tournament_id}/score-tracking",
    response_model=ScoreTrackingInfoResponse,
)
async def get_authenticated_score_tracking_info(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    court_id: CourtId | None = None,
) -> ScoreTrackingInfoResponse:
    tournament, matches, levels, courts = await asyncio.gather(
        sql_get_tournament(tournament_id),
        sql_get_scheduled_matches_with_details(tournament_id, court_id),
        sql_get_levels_for_tournament(tournament_id),
        get_all_courts_in_tournament(tournament_id),
    )
    return ScoreTrackingInfoResponse(
        data=ScoreTrackingInfo(
            tournament_id=tournament.id,
            tournament_name=tournament.name,
            matches=matches,
            referees_enabled=tournament.referees_enabled,
            levels=[LevelResponse.model_validate(level) for level in levels],
            courts=courts,
        )
    )


@router.get(
    "/tournaments/{tournament_id}/score-tracking/matches/{match_id}",
    response_model=ScoreTrackingMatchResponse,
)
async def get_authenticated_score_tracking_match(
    resolved: ResolvedMatch = Depends(resolved_scheduled_match_via_auth),
) -> ScoreTrackingMatchResponse:
    return await get_score_tracking_match_response(resolved.tournament_id, resolved.match.id)


@router.get(
    "/score-tracking/{score_tracking_token}/matches/{match_id}",
    response_model=ScoreTrackingMatchResponse,
)
async def get_score_tracking_match(
    resolved: ResolvedMatch = Depends(resolved_match_via_token),
) -> ScoreTrackingMatchResponse:
    return await get_score_tracking_match_response(resolved.tournament_id, resolved.match.id)
