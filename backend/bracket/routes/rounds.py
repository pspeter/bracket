from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import database
from bracket.logic.ranking.calculation import (
    recalculate_ranking_for_stage_item,
)
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.match import MatchState
from bracket.models.db.round import (
    Round,
    RoundCreateBody,
    RoundInsertable,
    RoundLifecycleState,
    RoundUpdateBody,
    SwapMatchInputsBody,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import RoundWithMatches
from bracket.routes.auth import user_authenticated_for_tournament
from bracket.routes.models import SuccessResponse
from bracket.routes.util import (
    disallow_archived_tournament,
    round_dependency,
    round_with_matches_dependency,
)
from bracket.sql.matches import sql_delete_match, sql_set_input_ids_for_match
from bracket.sql.rounds import (
    get_next_round_name,
    sql_create_round,
    sql_delete_round,
    sql_set_round_is_pinned,
)
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.id_types import RoundId, TournamentId
from tests.integration_tests.mocks import MOCK_NOW

router = APIRouter(prefix=config.api_prefix)


@router.delete("/tournaments/{tournament_id}/rounds/{round_id}", response_model=SuccessResponse)
async def delete_round(
    tournament_id: TournamentId,
    round_id: RoundId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    round_with_matches: RoundWithMatches = Depends(round_with_matches_dependency),
) -> SuccessResponse:
    for match in round_with_matches.matches:
        await sql_delete_match(match.id)

    await sql_delete_round(round_id)

    stage_item = await get_stage_item(tournament_id, round_with_matches.stage_item_id)
    await recalculate_ranking_for_stage_item(tournament_id, stage_item)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/rounds", response_model=SuccessResponse)
async def create_round(
    tournament_id: TournamentId,
    round_body: RoundCreateBody,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    await check_foreign_keys_belong_to_tournament(round_body, tournament_id)

    stages = await get_full_tournament_details(tournament_id)
    existing_rounds = [
        round_
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
    ]
    check_requirement(existing_rounds, user, "max_rounds")

    stage_item = await get_stage_item(tournament_id, stage_item_id=round_body.stage_item_id)

    if not stage_item.type.supports_dynamic_number_of_rounds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stage type {stage_item.type} doesn't support manual creation of rounds",
        )

    await sql_create_round(
        RoundInsertable(
            created=MOCK_NOW,
            stage_item_id=round_body.stage_item_id,
            name=await get_next_round_name(tournament_id, round_body.stage_item_id),
        ),
    )

    return SuccessResponse()


@router.put("/tournaments/{tournament_id}/rounds/{round_id}", response_model=SuccessResponse)
async def update_round_by_id(
    tournament_id: TournamentId,
    round_id: RoundId,
    round_body: RoundUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Round = Depends(round_dependency),
    ___: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    query = """
        UPDATE rounds
        SET name = :name, lifecycle_state = :lifecycle_state
        WHERE rounds.id IN (
            SELECT rounds.id
            FROM rounds
            JOIN stage_items ON rounds.stage_item_id = stage_items.id
            JOIN stages s on s.id = stage_items.stage_id
            WHERE s.tournament_id = :tournament_id
        )
        AND rounds.id = :round_id
    """
    await database.execute(
        query=query,
        values={
            "tournament_id": tournament_id,
            "round_id": round_id,
            "name": round_body.name,
            "lifecycle_state": round_body.lifecycle_state.value,
        },
    )
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/rounds/{round_id}/swap_inputs",
    response_model=SuccessResponse,
)
async def swap_match_inputs(
    tournament_id: TournamentId,
    round_id: RoundId,
    body: SwapMatchInputsBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    round_with_matches: RoundWithMatches = Depends(round_with_matches_dependency),
) -> SuccessResponse:
    """Swap team assignments between two matches in a RESOLVED not-started round.

    Pins the round so the manual override is preserved through upstream score corrections.
    Validated so that no referee ends up playing in the match they referee.
    """
    if round_with_matches.lifecycle_state != RoundLifecycleState.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only swap inputs in a RESOLVED round",
        )

    if any(m.state != MatchState.NOT_STARTED for m in round_with_matches.matches):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot swap inputs in a round that has already started",
        )

    matches_by_id = {m.id: m for m in round_with_matches.matches}
    match1 = matches_by_id.get(body.match1_id)
    match2 = matches_by_id.get(body.match2_id)

    if match1 is None or match2 is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both matches must belong to the specified round",
        )

    if match1.id == match2.id:
        return SuccessResponse()

    # Validate referee eligibility after swap: referee must not be one of the playing inputs.
    new_m1_inputs = {match2.stage_item_input1_id, match2.stage_item_input2_id}
    new_m2_inputs = {match1.stage_item_input1_id, match1.stage_item_input2_id}

    if (
        match1.referee_stage_item_input_id is not None
        and match1.referee_stage_item_input_id in new_m1_inputs
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Swap would cause a referee to play in their own match",
        )

    if (
        match2.referee_stage_item_input_id is not None
        and match2.referee_stage_item_input_id in new_m2_inputs
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Swap would cause a referee to play in their own match",
        )

    await sql_set_input_ids_for_match(
        round_id, body.match1_id, [match2.stage_item_input1_id, match2.stage_item_input2_id]
    )
    await sql_set_input_ids_for_match(
        round_id, body.match2_id, [match1.stage_item_input1_id, match1.stage_item_input2_id]
    )
    await sql_set_round_is_pinned(round_id, is_pinned=True)

    return SuccessResponse()
