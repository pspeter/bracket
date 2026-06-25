from fastapi import APIRouter, Depends, HTTPException
from heliclockter import datetime_utc
from starlette import status

from bracket.config import config
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import update_inputs_in_subsequent_elimination_rounds
from bracket.logic.scheduling.swiss_resolution_orchestrator import auto_resolve_next_swiss_round
from bracket.models.db.match import (
    Match,
    MatchSet,
    MatchSetBody,
    MatchState,
    MatchWithDetails,
    derive_match_state,
)
from bracket.models.db.stage_item import StageType
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    tournament_by_score_tracking_token,
    user_authenticated_for_tournament,
)
from bracket.routes.matches import validate_match_can_be_started
from bracket.routes.models import ScoreTrackingMatchResponse
from bracket.routes.util import match_dependency
from bracket.sql.match_sets import (
    get_sets_for_match,
    sql_get_match_set,
    sql_update_match_set,
)
from bracket.sql.matches import sql_get_match_with_details, sql_set_match_completed_at
from bracket.sql.rounds import get_round_by_id
from bracket.sql.stage_items import get_stage_item
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


async def update_match_set_and_recalculate(
    tournament_id: TournamentId,
    match: Match,
    match_set_id: MatchSetId,
    body: MatchSetBody,
) -> MatchWithDetails:
    await _get_set_belonging_to_match(match.id, match_set_id)

    # The match's overall state is derived from its sets; validate a start transition against
    # the same rule the match-level update used (a match can only start in an active stage).
    sets_before = await get_sets_for_match(match.id)
    match_with_sets = match.model_copy(update={"match_sets": sets_before})
    new_state = derive_match_state(
        [s if s.id != match_set_id else s.model_copy(update=body.model_dump()) for s in sets_before]
    )
    await validate_match_can_be_started(tournament_id, match_with_sets, new_state)

    await sql_update_match_set(match_set_id, body)

    # completed_at side effect: set when the match becomes completed, clear when it reverts.
    if new_state is MatchState.COMPLETED and match.completed_at is None:
        await sql_set_match_completed_at(match.id, datetime_utc.now())
    elif new_state is not MatchState.COMPLETED and match.completed_at is not None:
        await sql_set_match_completed_at(match.id, None)

    round_ = await get_round_by_id(tournament_id, match.round_id)
    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)
    await recalculate_ranking_for_stage_item(tournament_id, stage_item)
    await auto_resolve_next_swiss_round(tournament_id, stage_item)

    if stage_item.type == StageType.SINGLE_ELIMINATION:
        await update_inputs_in_subsequent_elimination_rounds(round_.id, stage_item, {match.id})

    updated = await sql_get_match_with_details(tournament_id, match.id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find match with id {match.id}",
        )
    return updated


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
    updated = await update_match_set_and_recalculate(tournament.id, match, set_id, body)
    return ScoreTrackingMatchResponse(data=updated)
