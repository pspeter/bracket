from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.logic.match_sets.apply_update import (
    score_edit_and_recalculate,
    update_match_set_and_recalculate,
)
from bracket.models.db.match import Match, MatchSet, MatchSetBody, MatchSetScoreEditBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    tournament_by_score_tracking_token,
    user_authenticated_for_tournament,
)
from bracket.routes.models import ScoreTrackingMatchResponse
from bracket.routes.util import match_dependency
from bracket.sql.match_sets import sql_get_match_set
from bracket.utils.id_types import MatchId, MatchSetId, TournamentId

router = APIRouter(prefix=config.api_prefix)


async def _get_set_belonging_to_match(match_id: MatchId, match_set_id: MatchSetId) -> MatchSet:
    match_set = await sql_get_match_set(match_set_id)
    if match_set is None or match_set.match_id != match_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find set {match_set_id} for match {match_id}",
        )
    return match_set


@router.put(
    "/tournaments/{tournament_id}/matches/{match_id}/sets/{set_id}",
    response_model=ScoreTrackingMatchResponse,
)
async def update_match_set_authenticated(
    tournament_id: TournamentId,
    match_id: MatchId,
    set_id: MatchSetId,
    body: MatchSetBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    match: Match = Depends(match_dependency),
) -> ScoreTrackingMatchResponse:
    await _get_set_belonging_to_match(match.id, set_id)
    updated = await update_match_set_and_recalculate(tournament_id, match, set_id, body)
    return ScoreTrackingMatchResponse(data=updated)


@router.put(
    "/score-tracking/{score_tracking_token}/matches/{match_id}/sets/{set_id}",
    response_model=ScoreTrackingMatchResponse,
)
async def update_match_set_by_token(
    match_id: MatchId,
    set_id: MatchSetId,
    body: MatchSetBody,
    tournament: Tournament = Depends(tournament_by_score_tracking_token),
) -> ScoreTrackingMatchResponse:
    match = await match_dependency(tournament.id, match_id)
    if match.start_time is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Could not find scheduled match"
        )
    await _get_set_belonging_to_match(match.id, set_id)
    updated = await update_match_set_and_recalculate(tournament.id, match, set_id, body)
    return ScoreTrackingMatchResponse(data=updated)


@router.post(
    "/tournaments/{tournament_id}/matches/{match_id}/sets/{set_id}/score-edit",
    response_model=ScoreTrackingMatchResponse,
)
async def score_edit_authenticated(
    tournament_id: TournamentId,
    match_id: MatchId,
    set_id: MatchSetId,
    body: MatchSetScoreEditBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    match: Match = Depends(match_dependency),
) -> ScoreTrackingMatchResponse:
    await _get_set_belonging_to_match(match.id, set_id)
    updated = await score_edit_and_recalculate(tournament_id, match, set_id, body)
    return ScoreTrackingMatchResponse(data=updated)


@router.post(
    "/score-tracking/{score_tracking_token}/matches/{match_id}/sets/{set_id}/score-edit",
    response_model=ScoreTrackingMatchResponse,
)
async def score_edit_by_token(
    match_id: MatchId,
    set_id: MatchSetId,
    body: MatchSetScoreEditBody,
    tournament: Tournament = Depends(tournament_by_score_tracking_token),
) -> ScoreTrackingMatchResponse:
    match = await match_dependency(tournament.id, match_id)
    if match.start_time is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Could not find scheduled match"
        )
    await _get_set_belonging_to_match(match.id, set_id)
    updated = await score_edit_and_recalculate(tournament.id, match, set_id, body)
    return ScoreTrackingMatchResponse(data=updated)
