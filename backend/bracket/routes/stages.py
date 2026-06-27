from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import database
from bracket.logic.levels import validate_level_id_for_tournament
from bracket.logic.planning.template import build_template_blueprint, max_until_rank_for_template
from bracket.logic.planning.template_service import replace_stages_from_template
from bracket.logic.scheduling.builder import determine_available_inputs
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.stage import (
    Stage,
    StageCreateBody,
    StageTemplateCreateBody,
    StageUpdateBody,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import StageWithStageItems
from bracket.routes.auth import (
    user_authenticated_for_tournament,
    user_authenticated_or_public_dashboard,
)
from bracket.routes.models import (
    StageItemInputOptionsResponse,
    StagesWithStageItemsResponse,
    SuccessResponse,
)
from bracket.routes.util import disallow_archived_tournament, stage_dependency
from bracket.sql.stages import (
    get_full_tournament_details,
    sql_create_stage,
    sql_delete_stage,
)
from bracket.sql.teams import get_teams_with_members
from bracket.utils.id_types import StageId, TournamentId

router = APIRouter(prefix=config.api_prefix)


def validate_stage_template_body(stage_body: StageTemplateCreateBody) -> None:
    if stage_body.groups not in {2, 3, 4}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="groups must be 2, 3, or 4",
        )

    if stage_body.total_teams < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="total_teams must be at least 4",
        )

    teams_per_group = stage_body.total_teams // stage_body.groups
    if teams_per_group < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Each group must contain at least 2 teams",
        )

    if stage_body.until_rank == "all":
        return

    if stage_body.until_rank < 2 or stage_body.until_rank % 2 != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='until_rank must be an even integer >= 2 or "all"',
        )

    max_until_rank = max_until_rank_for_template(stage_body.groups, stage_body.total_teams)
    if stage_body.until_rank > max_until_rank:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"until_rank must be <= {max_until_rank} for this configuration",
        )


@router.get("/tournaments/{tournament_id}/stages", response_model=StagesWithStageItemsResponse)
async def get_stages(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_or_public_dashboard),
) -> StagesWithStageItemsResponse:
    stages_ = await get_full_tournament_details(tournament_id)
    return StagesWithStageItemsResponse(data=stages_)


@router.delete("/tournaments/{tournament_id}/stages/{stage_id}", response_model=SuccessResponse)
async def delete_stage(
    tournament_id: TournamentId,
    stage_id: StageId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    _stage: StageWithStageItems = Depends(stage_dependency),
) -> SuccessResponse:
    await sql_delete_stage(tournament_id, stage_id)

    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stages", response_model=SuccessResponse)
async def create_stage(
    tournament_id: TournamentId,
    body: StageCreateBody = StageCreateBody(),
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    await validate_level_id_for_tournament(tournament_id, body.level_id)

    existing_stages = await get_full_tournament_details(tournament_id)
    check_requirement(existing_stages, user, "max_stages")

    await sql_create_stage(tournament_id, level_id=body.level_id)
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/stages/from-template",
    response_model=StagesWithStageItemsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stages_from_template(
    tournament_id: TournamentId,
    stage_body: StageTemplateCreateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> StagesWithStageItemsResponse:
    validate_stage_template_body(stage_body)
    await validate_level_id_for_tournament(tournament_id, stage_body.level_id)

    stages_ = await replace_stages_from_template(
        tournament_id,
        build_template_blueprint(stage_body.to_template_config()),
        level_id=stage_body.level_id,
    )
    return StagesWithStageItemsResponse(data=stages_)


@router.put("/tournaments/{tournament_id}/stages/{stage_id}", response_model=SuccessResponse)
async def update_stage(
    tournament_id: TournamentId,
    stage_id: StageId,
    stage_body: StageUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    stage: Stage = Depends(stage_dependency),  # pylint: disable=redefined-builtin
) -> SuccessResponse:
    values = {"tournament_id": tournament_id, "stage_id": stage_id}
    query = """
        UPDATE stages
        SET name = :name
        WHERE stages.id = :stage_id
        AND stages.tournament_id = :tournament_id
    """
    await database.execute(
        query=query,
        values={**values, "name": stage_body.name},
    )
    return SuccessResponse()


@router.get(
    "/tournaments/{tournament_id}/available_inputs",
    response_model=StageItemInputOptionsResponse,
)
async def get_available_inputs(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> StageItemInputOptionsResponse:
    stages = await get_full_tournament_details(tournament_id)
    teams = await get_teams_with_members(tournament_id)
    return StageItemInputOptionsResponse(data=determine_available_inputs(teams, stages))
