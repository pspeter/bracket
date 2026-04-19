from fastapi import APIRouter, Depends, HTTPException

from bracket.config import config
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import update_inputs_in_subsequent_elimination_rounds
from bracket.models.db.match import Match, MatchScoreTrackingBody
from bracket.models.db.stage_item import StageType
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import tournament_by_score_tracking_token, user_authenticated_for_tournament
from bracket.routes.matches import (
    get_full_match_body_from_score_tracking,
    get_match_body_with_state_updates,
    get_score_tracking_match_response,
)
from bracket.routes.models import (
    ScoreTrackingInfo,
    ScoreTrackingInfoResponse,
    ScoreTrackingMatchResponse,
)
from bracket.routes.util import match_dependency
from bracket.sql.matches import sql_get_scheduled_matches_with_details, sql_update_match
from bracket.sql.rounds import get_round_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import MatchId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.get(
    "/score-tracking/{score_tracking_token}",
    response_model=ScoreTrackingInfoResponse,
)
async def get_score_tracking_info(
    tournament: Tournament = Depends(tournament_by_score_tracking_token),
) -> ScoreTrackingInfoResponse:
    matches = await sql_get_scheduled_matches_with_details(tournament.id)
    return ScoreTrackingInfoResponse(
        data=ScoreTrackingInfo(
            tournament_id=tournament.id,
            tournament_name=tournament.name,
            matches=matches,
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
) -> ScoreTrackingInfoResponse:
    tournament = await sql_get_tournament(tournament_id)
    matches = await sql_get_scheduled_matches_with_details(tournament_id)
    return ScoreTrackingInfoResponse(
        data=ScoreTrackingInfo(
            tournament_id=tournament.id,
            tournament_name=tournament.name,
            matches=matches,
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


@router.put(
    "/tournaments/{tournament_id}/score-tracking/matches/{match_id}",
    response_model=ScoreTrackingMatchResponse,
)
async def update_authenticated_score_tracking_match(
    tournament_id: TournamentId,
    match_id: MatchId,
    body: MatchScoreTrackingBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    match: Match = Depends(tournament_score_tracking_match_dependency),
) -> ScoreTrackingMatchResponse:
    tournament = await sql_get_tournament(tournament_id)
    match_body = get_match_body_with_state_updates(
        match, get_full_match_body_from_score_tracking(match, body)
    )
    await sql_update_match(match_id, match_body, tournament)

    round_ = await get_round_by_id(tournament_id, match.round_id)
    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)
    await recalculate_ranking_for_stage_item(tournament_id, stage_item)

    if stage_item.type == StageType.SINGLE_ELIMINATION:
        await update_inputs_in_subsequent_elimination_rounds(round_.id, stage_item, {match_id})

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


@router.put(
    "/score-tracking/{score_tracking_token}/matches/{match_id}",
    response_model=ScoreTrackingMatchResponse,
)
async def update_score_tracking_match(
    match_id: MatchId,
    body: MatchScoreTrackingBody,
    tournament: Tournament = Depends(tournament_by_score_tracking_token),
    match: Match = Depends(score_tracking_match_dependency),
) -> ScoreTrackingMatchResponse:
    tournament_full = await sql_get_tournament(tournament.id)
    match_body = get_match_body_with_state_updates(
        match, get_full_match_body_from_score_tracking(match, body)
    )
    await sql_update_match(match_id, match_body, tournament_full)

    round_ = await get_round_by_id(tournament.id, match.round_id)
    stage_item = await get_stage_item(tournament.id, round_.stage_item_id)
    await recalculate_ranking_for_stage_item(tournament.id, stage_item)

    if stage_item.type == StageType.SINGLE_ELIMINATION:
        await update_inputs_in_subsequent_elimination_rounds(round_.id, stage_item, {match_id})

    return await get_score_tracking_match_response(tournament.id, match_id)
