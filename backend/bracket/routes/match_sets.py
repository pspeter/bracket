from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.logic.match_sets.apply_update import score_edit_and_recalculate
from bracket.models.db.match import MatchSet, MatchSetScoreEditBody
from bracket.routes.match_access import (
    ResolvedMatch,
    resolved_match_via_auth,
    resolved_match_via_token,
)
from bracket.routes.models import ScoreTrackingMatchResponse
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


async def _score_edit(
    resolved: ResolvedMatch, set_id: MatchSetId, body: MatchSetScoreEditBody
) -> ScoreTrackingMatchResponse:
    await _get_set_belonging_to_match(resolved.match.id, set_id)
    updated = await score_edit_and_recalculate(resolved.tournament_id, resolved.match, set_id, body)
    return ScoreTrackingMatchResponse(data=updated)


@router.post(
    "/tournaments/{tournament_id}/matches/{match_id}/sets/{set_id}/score-edit",
    response_model=ScoreTrackingMatchResponse,
)
async def score_edit_authenticated(
    # tournament_id/match_id are also resolved inside the dependency; they are re-declared
    # here purely to keep the OpenAPI path-parameter order identical to before the refactor
    # (FastAPI lists a route's own params before dependency params).
    tournament_id: TournamentId,
    match_id: MatchId,
    set_id: MatchSetId,
    body: MatchSetScoreEditBody,
    resolved: ResolvedMatch = Depends(resolved_match_via_auth),
) -> ScoreTrackingMatchResponse:
    return await _score_edit(resolved, set_id, body)


@router.post(
    "/score-tracking/{score_tracking_token}/matches/{match_id}/sets/{set_id}/score-edit",
    response_model=ScoreTrackingMatchResponse,
)
async def score_edit_by_token(
    # match_id is also resolved inside the dependency; it is re-declared here purely to
    # keep the OpenAPI path-parameter order identical to before the refactor.
    match_id: MatchId,
    set_id: MatchSetId,
    body: MatchSetScoreEditBody,
    resolved: ResolvedMatch = Depends(resolved_match_via_token),
) -> ScoreTrackingMatchResponse:
    return await _score_edit(resolved, set_id, body)
