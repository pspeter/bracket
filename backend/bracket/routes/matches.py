from fastapi import APIRouter, Depends, HTTPException
from heliclockter import datetime_utc
from starlette import status

from bracket.config import config
from bracket.logic.planning.conflicts import handle_conflicts
from bracket.logic.planning.matches import (
    get_scheduled_matches,
    handle_match_reschedule,
    reorder_all_matches_with_stage_boundaries,
    schedule_all_unscheduled_matches,
)
from bracket.logic.ranking.calculation import (
    recalculate_ranking_for_stage_item,
)
from bracket.logic.ranking.elimination import update_inputs_in_subsequent_elimination_rounds
from bracket.logic.scheduling.upcoming_matches import (
    get_draft_round_in_stage_item,
    get_upcoming_matches_for_swiss,
)
from bracket.models.db.match import (
    Match,
    MatchBody,
    MatchCreateBody,
    MatchCreateBodyFrontend,
    MatchFilter,
    MatchRescheduleBody,
    MatchScoreTrackingBody,
    MatchState,
)
from bracket.models.db.stage_item import StageType
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import user_authenticated_for_tournament
from bracket.routes.models import (
    ScoreTrackingMatchResponse,
    SingleMatchResponse,
    SuccessResponse,
    UpcomingMatchesResponse,
)
from bracket.routes.util import disallow_archived_tournament, match_dependency
from bracket.sql.courts import get_all_courts_in_tournament
from bracket.sql.matches import (
    sql_create_match,
    sql_delete_match,
    sql_get_match_with_details,
    sql_unschedule_match,
    sql_update_match,
)
from bracket.sql.rounds import get_round_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.id_types import MatchId, StageItemId, TournamentId

router = APIRouter(prefix=config.api_prefix)


async def validate_match_can_be_started(
    tournament_id: TournamentId, existing_match: Match, next_state: MatchState
) -> None:
    if existing_match.state is MatchState.NOT_STARTED and next_state in {
        MatchState.IN_PROGRESS,
        MatchState.COMPLETED,
    }:
        stages = await get_full_tournament_details(tournament_id, round_id=existing_match.round_id)
        for stage in stages:
            for stage_item in stage.stage_items:
                for round_ in stage_item.rounds:
                    if round_.id == existing_match.round_id:
                        if stage.is_active:
                            return
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=(
                                f'Cannot start this match because stage "{stage.name}" '
                                "has not started yet. Start that stage first."
                            ),
                        )

        raise ValueError(
            f"Could not find stage for match {existing_match.id} in tournament {tournament_id}"
        )


def validate_match_can_be_unscheduled(match: Match) -> None:
    if match.state is MatchState.NOT_STARTED:
        return

    state_label = "in progress" if match.state is MatchState.IN_PROGRESS else "completed"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Cannot move a {state_label} match back to Unscheduled. "
            "Only not started matches can be unscheduled."
        ),
    )


def get_match_body_with_state_updates(existing_match: Match, match_body: MatchBody) -> MatchBody:
    missing_fields = {
        "round_id": existing_match.round_id,
        "stage_item_input1_score": existing_match.stage_item_input1_score,
        "stage_item_input2_score": existing_match.stage_item_input2_score,
        "court_id": existing_match.court_id,
        "custom_duration_minutes": existing_match.custom_duration_minutes,
        "custom_margin_minutes": existing_match.custom_margin_minutes,
        "state": existing_match.state,
    }
    match_body = match_body.model_copy(
        update={
            key: value
            for key, value in missing_fields.items()
            if key not in match_body.model_fields_set
        }
    )

    scores_changed = (
        existing_match.stage_item_input1_score != match_body.stage_item_input1_score
        or existing_match.stage_item_input2_score != match_body.stage_item_input2_score
    )
    if scores_changed and match_body.state is not MatchState.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scores can only be changed while the match is in progress",
        )

    completed_at = None
    if match_body.state is MatchState.COMPLETED:
        completed_at = (
            existing_match.completed_at
            if existing_match.state is MatchState.COMPLETED
            and existing_match.completed_at is not None
            else datetime_utc.now()
        )

    return match_body.model_copy(update={"completed_at": completed_at})


def get_full_match_body_from_score_tracking(
    existing_match: Match, body: MatchScoreTrackingBody
) -> MatchBody:
    return MatchBody(
        round_id=existing_match.round_id,
        court_id=existing_match.court_id,
        custom_duration_minutes=existing_match.custom_duration_minutes,
        custom_margin_minutes=existing_match.custom_margin_minutes,
        stage_item_input1_score=body.stage_item_input1_score,
        stage_item_input2_score=body.stage_item_input2_score,
        state=body.state,
    )


@router.get(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}/upcoming_matches",
    response_model=UpcomingMatchesResponse,
)
async def get_matches_to_schedule(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    elo_diff_threshold: int = 200,
    iterations: int = 2_000,
    only_recommended: bool = False,
    limit: int = 50,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> UpcomingMatchesResponse:
    match_filter = MatchFilter(
        elo_diff_threshold=elo_diff_threshold,
        only_recommended=only_recommended,
        limit=limit,
        iterations=iterations,
    )

    draft_round, stage_item = await get_draft_round_in_stage_item(tournament_id, stage_item_id)
    courts = await get_all_courts_in_tournament(tournament_id)
    if len(courts) <= len(draft_round.matches):
        return UpcomingMatchesResponse(data=[])

    return UpcomingMatchesResponse(
        data=get_upcoming_matches_for_swiss(match_filter, stage_item, draft_round)
    )


@router.delete("/tournaments/{tournament_id}/matches/{match_id}", response_model=SuccessResponse)
async def delete_match(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    match: Match = Depends(match_dependency),
) -> SuccessResponse:
    round_ = await get_round_by_id(tournament_id, match.round_id)
    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)

    if not round_.is_draft or stage_item.type != StageType.SWISS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only delete matches from draft rounds in Swiss stage items",
        )

    await sql_delete_match(match.id)

    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)

    await recalculate_ranking_for_stage_item(tournament_id, stage_item)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/matches", response_model=SingleMatchResponse)
async def create_match(
    tournament_id: TournamentId,
    match_body: MatchCreateBodyFrontend,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SingleMatchResponse:
    await check_foreign_keys_belong_to_tournament(match_body, tournament_id)

    round_ = await get_round_by_id(tournament_id, match_body.round_id)
    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)

    if not round_.is_draft or stage_item.type != StageType.SWISS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only create matches in draft rounds of Swiss stage items",
        )

    tournament = await sql_get_tournament(tournament_id)
    body_with_durations = MatchCreateBody(
        **match_body.model_dump(),
        duration_minutes=tournament.duration_minutes,
        margin_minutes=tournament.margin_minutes,
    )

    return SingleMatchResponse(data=await sql_create_match(body_with_durations))


@router.post("/tournaments/{tournament_id}/schedule_matches", response_model=SuccessResponse)
async def schedule_matches(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    stages = await get_full_tournament_details(tournament_id)
    await schedule_all_unscheduled_matches(tournament_id, stages)
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/matches/{match_id}/unschedule", response_model=SuccessResponse
)
async def unschedule_match(
    tournament_id: TournamentId,
    tournament: Tournament = Depends(disallow_archived_tournament),
    _: UserPublic = Depends(user_authenticated_for_tournament),
    match_row: Match = Depends(match_dependency),
) -> SuccessResponse:
    validate_match_can_be_unscheduled(match_row)
    old_court_id = match_row.court_id

    await sql_unschedule_match(match_row.id)

    if old_court_id is not None:
        stages = await get_full_tournament_details(tournament_id)
        scheduled_matches = get_scheduled_matches(stages)
        await reorder_all_matches_with_stage_boundaries(tournament, stages, scheduled_matches)

    await handle_conflicts(await get_full_tournament_details(tournament_id))
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/matches/{match_id}/reschedule", response_model=SuccessResponse
)
async def reschedule_match(
    tournament_id: TournamentId,
    match_id: MatchId,
    body: MatchRescheduleBody,
    tournament: Tournament = Depends(disallow_archived_tournament),
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    await check_foreign_keys_belong_to_tournament(body, tournament_id)
    await handle_match_reschedule(tournament, body, match_id)
    await handle_conflicts(await get_full_tournament_details(tournament_id))
    return SuccessResponse()


@router.put("/tournaments/{tournament_id}/matches/{match_id}", response_model=SuccessResponse)
async def update_match_by_id(
    tournament_id: TournamentId,
    match_id: MatchId,
    match_body: MatchBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    match: Match = Depends(match_dependency),
) -> SuccessResponse:
    await check_foreign_keys_belong_to_tournament(match_body, tournament_id)
    tournament = await sql_get_tournament(tournament_id)
    await validate_match_can_be_started(tournament_id, match, match_body.state)
    match_body = get_match_body_with_state_updates(match, match_body)

    await sql_update_match(match_id, match_body, tournament)

    round_ = await get_round_by_id(tournament_id, match.round_id)
    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)
    await recalculate_ranking_for_stage_item(tournament_id, stage_item)

    if (
        match_body.custom_duration_minutes != match.custom_duration_minutes
        or match_body.custom_margin_minutes != match.custom_margin_minutes
    ) and match.court_id is not None:
        tournament = await sql_get_tournament(tournament_id)
        stages = await get_full_tournament_details(tournament_id)
        scheduled_matches = get_scheduled_matches(stages)
        await reorder_all_matches_with_stage_boundaries(tournament, stages, scheduled_matches)

    if stage_item.type == StageType.SINGLE_ELIMINATION:
        await update_inputs_in_subsequent_elimination_rounds(round_.id, stage_item, {match_id})

    return SuccessResponse()


async def get_score_tracking_match_response(
    tournament_id: TournamentId, match_id: MatchId
) -> ScoreTrackingMatchResponse:
    match = await sql_get_match_with_details(tournament_id, match_id)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find match with id {match_id}",
        )
    return ScoreTrackingMatchResponse(data=match)
