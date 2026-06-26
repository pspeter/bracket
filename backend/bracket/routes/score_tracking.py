import asyncio

from fastapi import APIRouter, Depends, HTTPException

from bracket.config import config
from bracket.models.db.match import Match
from bracket.models.db.tournament import LevelResponse, Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    tournament_by_score_tracking_token,
    user_authenticated_for_tournament,
)
from bracket.routes.matches import (
    get_score_tracking_match_response,
)
from bracket.routes.models import (
    ScoreTrackingInfo,
    ScoreTrackingInfoResponse,
    ScoreTrackingMatchResponse,
)
from bracket.routes.util import match_dependency
from bracket.sql.courts import get_all_courts_in_tournament
from bracket.sql.levels import sql_get_levels_for_tournament
from bracket.sql.matches import sql_get_scheduled_matches_with_details
from bracket.sql.stages import sql_has_active_stage
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import CourtId, MatchId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.get(
    "/score-tracking/{score_tracking_token}",
    response_model=ScoreTrackingInfoResponse,
)
async def get_score_tracking_info(
    tournament: Tournament = Depends(tournament_by_score_tracking_token),
    court_id: CourtId | None = None,
) -> ScoreTrackingInfoResponse:
    matches, has_active_stage, levels, courts = await asyncio.gather(
        sql_get_scheduled_matches_with_details(tournament.id, court_id),
        sql_has_active_stage(tournament.id),
        sql_get_levels_for_tournament(tournament.id),
        get_all_courts_in_tournament(tournament.id),
    )
    return ScoreTrackingInfoResponse(
        data=ScoreTrackingInfo(
            tournament_id=tournament.id,
            tournament_name=tournament.name,
            matches=matches,
            has_active_stage=has_active_stage,
            referees_enabled=tournament.referees_enabled,
            levels=[LevelResponse.model_validate(level) for level in levels],
            courts=courts,
        )
    )


async def score_tracking_match_dependency(
    match_id: MatchId, tournament: Tournament = Depends(tournament_by_score_tracking_token)
) -> Match:
    match = await match_dependency(tournament.id, match_id)
    if match.start_time is None:
        raise HTTPException(status_code=404, detail="Could not find scheduled match")
    return match


async def tournament_score_tracking_match_dependency(
    tournament_id: TournamentId,
    match_id: MatchId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> Match:
    match = await match_dependency(tournament_id, match_id)
    if match.start_time is None:
        raise HTTPException(status_code=404, detail="Could not find scheduled match")
    return match


@router.get(
    "/tournaments/{tournament_id}/score-tracking",
    response_model=ScoreTrackingInfoResponse,
)
async def get_authenticated_score_tracking_info(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    court_id: CourtId | None = None,
) -> ScoreTrackingInfoResponse:
    tournament, matches, has_active_stage, levels, courts = await asyncio.gather(
        sql_get_tournament(tournament_id),
        sql_get_scheduled_matches_with_details(tournament_id, court_id),
        sql_has_active_stage(tournament_id),
        sql_get_levels_for_tournament(tournament_id),
        get_all_courts_in_tournament(tournament_id),
    )
    return ScoreTrackingInfoResponse(
        data=ScoreTrackingInfo(
            tournament_id=tournament.id,
            tournament_name=tournament.name,
            matches=matches,
            has_active_stage=has_active_stage,
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
    tournament_id: TournamentId,
    match_id: MatchId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Match = Depends(tournament_score_tracking_match_dependency),
) -> ScoreTrackingMatchResponse:
    return await get_score_tracking_match_response(tournament_id, match_id)


@router.get(
    "/score-tracking/{score_tracking_token}/matches/{match_id}",
    response_model=ScoreTrackingMatchResponse,
)
async def get_score_tracking_match(
    match_id: MatchId,
    tournament: Tournament = Depends(tournament_by_score_tracking_token),
    _: Match = Depends(score_tracking_match_dependency),
) -> ScoreTrackingMatchResponse:
    return await get_score_tracking_match_response(tournament.id, match_id)
