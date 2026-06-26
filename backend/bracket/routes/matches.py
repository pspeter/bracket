from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import database
from bracket.logic.planning.matches import (
    assign_missing_referees_only,
    eligible_referee_slot_ids,
    get_scheduled_matches,
    handle_match_reschedule,
    handle_match_resize_break,
    handle_match_swap,
    reoptimize_all_matches,
    reorder_all_matches,
    schedule_all_unscheduled_matches,
    validate_match_can_be_unscheduled,
)
from bracket.models.db.match import (
    Match,
    MatchBody,
    MatchCreateBodyFrontend,
    MatchRescheduleBody,
    MatchResizeBreakBody,
    MatchState,
    MatchSwapBody,
    SchedulerWeights,
)
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import user_authenticated_for_tournament
from bracket.routes.models import (
    ScoreTrackingMatchResponse,
    SingleMatchResponse,
    SuccessResponse,
)
from bracket.routes.util import disallow_archived_tournament, match_dependency
from bracket.sql.matches import (
    sql_get_match_with_details,
    sql_unschedule_match,
    sql_update_match,
)
from bracket.sql.referees import (
    sql_clear_match_referee,
    sql_set_match_referee_name,
    sql_set_match_referee_slot,
)
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.id_types import MatchId, StageItemInputId, TournamentId

router = APIRouter(prefix=config.api_prefix)


async def validate_referee_slot_for_match(
    tournament_id: TournamentId, match: Match, referee_stage_item_input_id: StageItemInputId
) -> None:
    """A referee slot must be eligible for the refereed match: a stage-item input in the match's
    own stage that is not one of the two slots playing the match. This reuses the same
    eligibility the CP-SAT auto-scheduler applies (see eligible_referee_slot_ids), so a
    hand-picked referee can never name a participant from a later stage who is still unknown
    while this match is played.
    """
    stages = await get_full_tournament_details(tournament_id)
    if referee_stage_item_input_id not in eligible_referee_slot_ids(stages, match.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Referee slot must be a stage-item input in the match's own stage",
        )


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
                        match = next(
                            (m for m in round_.matches if m.id == existing_match.id), None
                        )
                        if match is not None and isinstance(
                            match.stage_item_input1, StageItemInputFinal
                        ) and isinstance(match.stage_item_input2, StageItemInputFinal):
                            return
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=(
                                "Cannot start this match because its opponents are not "
                                "determined yet."
                            ),
                        )

        raise ValueError(
            f"Could not find stage for match {existing_match.id} in tournament {tournament_id}"
        )


@router.delete("/tournaments/{tournament_id}/matches/{match_id}", response_model=SuccessResponse)
async def delete_match(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    ___: Match = Depends(match_dependency),
) -> SuccessResponse:
    # Matches are managed automatically (the Swiss skeleton is fixed; other stage types
    # generate their full bracket up front), so individual matches can't be deleted.
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Matches cannot be deleted individually",
    )


@router.post("/tournaments/{tournament_id}/matches", response_model=SingleMatchResponse)
async def create_match(
    tournament_id: TournamentId,
    match_body: MatchCreateBodyFrontend,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SingleMatchResponse:
    # Matches are generated automatically for every stage type, so they can't be created
    # manually anymore (this was previously only allowed inside Swiss draft rounds).
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Matches cannot be created individually",
    )


@router.post("/tournaments/{tournament_id}/schedule_matches", response_model=SuccessResponse)
async def schedule_matches(
    tournament_id: TournamentId,
    weights: SchedulerWeights = SchedulerWeights(),
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    stages = await get_full_tournament_details(tournament_id)
    await schedule_all_unscheduled_matches(tournament_id, stages, weights)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/reoptimize_matches", response_model=SuccessResponse)
async def reoptimize_matches(
    tournament_id: TournamentId,
    weights: SchedulerWeights = SchedulerWeights(),
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    stages = await get_full_tournament_details(tournament_id)
    await reoptimize_all_matches(tournament_id, stages, weights)
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/matches/auto-assign-referees", response_model=SuccessResponse
)
async def auto_assign_referees(
    tournament_id: TournamentId,
    weights: SchedulerWeights = SchedulerWeights(),
    _: UserPublic = Depends(user_authenticated_for_tournament),
    tournament: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    if not tournament.referees_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Referees are not enabled for this tournament",
        )
    stages = await get_full_tournament_details(tournament_id)
    await assign_missing_referees_only(tournament, stages, weights)
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/matches/{match_id}/unschedule", response_model=SuccessResponse
)
async def unschedule_match(
    tournament_id: TournamentId,
    __: Tournament = Depends(disallow_archived_tournament),
    _: UserPublic = Depends(user_authenticated_for_tournament),
    match_row: Match = Depends(match_dependency),
) -> SuccessResponse:
    validate_match_can_be_unscheduled(match_row)
    await sql_unschedule_match(match_row.id)

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
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/matches/{match_id}/resize_break",
    response_model=SuccessResponse,
)
async def resize_match_break(
    tournament_id: TournamentId,
    match_id: MatchId,
    body: MatchResizeBreakBody,
    tournament: Tournament = Depends(disallow_archived_tournament),
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    async with database.transaction():
        await handle_match_resize_break(tournament, match_id, body.new_duration_minutes)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/matches/swap", response_model=SuccessResponse)
async def swap_matches(
    tournament_id: TournamentId,
    body: MatchSwapBody,
    tournament: Tournament = Depends(disallow_archived_tournament),
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    await check_foreign_keys_belong_to_tournament(body, tournament_id)
    async with database.transaction():
        await handle_match_swap(tournament, body)
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

    # Fields the client didn't send keep their existing values (a partial update must not null
    # out, e.g., the court just because only the duration was changed).
    fill_defaults = {
        "round_id": match.round_id,
        "court_id": match.court_id,
        "custom_duration_minutes": match.custom_duration_minutes,
    }
    match_body = match_body.model_copy(
        update={
            key: value
            for key, value in fill_defaults.items()
            if key not in match_body.model_fields_set
        }
    )

    # Only touch the referee when the client explicitly sent at least one referee field, so
    # other match edits (scores, duration, ...) never clear an existing assignment.
    referee_slot_provided = "referee_stage_item_input_id" in match_body.model_fields_set
    referee_name_provided = "referee_name" in match_body.model_fields_set
    referee_provided = referee_slot_provided or referee_name_provided

    referee_stage_item_input_id = match_body.referee_stage_item_input_id
    referee_name = match_body.referee_name

    if referee_stage_item_input_id is not None and referee_name is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At most one of referee_stage_item_input_id and referee_name may be set",
        )

    if referee_stage_item_input_id is not None:
        await validate_referee_slot_for_match(tournament_id, match, referee_stage_item_input_id)

    await sql_update_match(match_id, match_body, tournament)

    if referee_provided:
        if referee_stage_item_input_id is not None:
            await sql_set_match_referee_slot(match_id, referee_stage_item_input_id)
        elif referee_name is not None:
            await sql_set_match_referee_name(match_id, referee_name)
        else:
            await sql_clear_match_referee(match_id)

    if (
        match_body.custom_duration_minutes != match.custom_duration_minutes
        and match.court_id is not None
    ):
        # A duration change only shifts start times on the match's own court.
        tournament = await sql_get_tournament(tournament_id)
        stages = await get_full_tournament_details(tournament_id)
        court_matches = [
            match_pos
            for match_pos in get_scheduled_matches(stages)
            if match_pos.match.court_id == match.court_id
        ]
        await reorder_all_matches(tournament, court_matches)

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
