from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import database
from bracket.logic.levels import validate_level_id_for_tournament
from bracket.logic.planning.template import build_template_blueprint, max_until_rank_for_template
from bracket.logic.planning.template_service import replace_stages_from_template
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import (
    update_inputs_in_complete_elimination_stage_item,
)
from bracket.logic.scheduling.builder import determine_available_inputs
from bracket.logic.scheduling.handle_stage_activation import (
    get_pending_match_count_in_stage,
    get_pending_matches_message,
    get_updates_to_inputs_in_activated_stage,
    update_matches_in_activated_stage,
    update_matches_in_deactivated_stage,
)
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.stage import (
    Stage,
    StageActivateBody,
    StageCreateBody,
    StageRankingUpdateBody,
    StageTemplateCreateBody,
    StageUpdateBody,
)
from bracket.models.db.stage_item import StageType
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import StageWithStageItems
from bracket.routes.auth import (
    user_authenticated_for_tournament,
    user_authenticated_or_public_dashboard,
)
from bracket.routes.models import (
    StageItemInputOptionsResponse,
    StageRankingResponse,
    StagesWithStageItemsResponse,
    SuccessResponse,
)
from bracket.routes.util import disallow_archived_tournament, stage_dependency
from bracket.sql.match_sets import sql_resize_sets_for_stage_item
from bracket.sql.rankings import get_ranking_by_id
from bracket.sql.stage_items import get_stage_item, sql_set_ranking_for_stage_items
from bracket.sql.stages import (
    get_full_tournament_details,
    get_next_stage_in_tournament,
    sql_activate_next_stage,
    sql_create_stage,
    sql_delete_stage,
)
from bracket.sql.teams import get_teams_with_members
from bracket.utils.id_types import LevelId, StageId, TournamentId

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


@router.put(
    "/tournaments/{tournament_id}/stages/{stage_id}/ranking", response_model=SuccessResponse
)
async def set_ranking_for_stage_items(
    tournament_id: TournamentId,
    stage_id: StageId,
    stage_body: StageRankingUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    stage: StageWithStageItems = Depends(stage_dependency),
) -> SuccessResponse:
    ranking = await get_ranking_by_id(tournament_id, stage_body.ranking_id)
    if ranking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find ranking with id {stage_body.ranking_id}",
        )

    has_single_elimination = any(
        stage_item.type is StageType.SINGLE_ELIMINATION for stage_item in stage.stage_items
    )
    if ranking.num_sets % 2 == 0 and has_single_elimination:
        raise HTTPException(
            status_code=422,
            detail="Even number of sets is not supported for single elimination brackets.",
        )

    async with database.transaction():
        # Reassigning items to a ranking with a different set count must resize the set rows of
        # their existing matches, mirroring the per-stage-item update path.
        for stage_item in stage.stage_items:
            if stage_item.ranking_id == ranking.id:
                continue
            old_ranking = (
                await get_ranking_by_id(tournament_id, stage_item.ranking_id)
                if stage_item.ranking_id is not None
                else None
            )
            old_num_sets = old_ranking.num_sets if old_ranking is not None else 1
            await sql_resize_sets_for_stage_item(stage_item.id, old_num_sets, ranking.num_sets)

        await sql_set_ranking_for_stage_items(stage_id, stage_body.ranking_id)

        for stage_item in stage.stage_items:
            updated_stage_item = await get_stage_item(tournament_id, stage_item.id)
            await recalculate_ranking_for_stage_item(tournament_id, updated_stage_item)
            if updated_stage_item.type is StageType.SINGLE_ELIMINATION:
                await update_inputs_in_complete_elimination_stage_item(updated_stage_item)

    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stages/activate", response_model=SuccessResponse)
async def activate_next_stage(
    tournament_id: TournamentId,
    stage_body: StageActivateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    await validate_level_id_for_tournament(tournament_id, stage_body.level_id)

    new_active_stage_id = await get_next_stage_in_tournament(
        tournament_id, stage_body.direction, stage_body.level_id
    )
    if new_active_stage_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"There is no {stage_body.direction} stage",
        )

    stages = await get_full_tournament_details(tournament_id)
    deactivated_stage = next(
        (stage for stage in stages if stage.is_active and stage.level_id == stage_body.level_id),
        None,
    )

    if stage_body.direction == "next":
        if deactivated_stage is not None:
            pending_match_count = get_pending_match_count_in_stage(deactivated_stage)
            if pending_match_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=get_pending_matches_message(pending_match_count),
                )
        await update_matches_in_activated_stage(tournament_id, new_active_stage_id)
    else:
        if deactivated_stage:
            await update_matches_in_deactivated_stage(tournament_id, deactivated_stage)

    await sql_activate_next_stage(new_active_stage_id, tournament_id, stage_body.level_id)
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


@router.get("/tournaments/{tournament_id}/next_stage_rankings")
async def get_next_stage_rankings(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    level_id: LevelId | None = None,
) -> StageRankingResponse:
    """
    Get the rankings for the stage items in this stage.
    """
    await validate_level_id_for_tournament(tournament_id, level_id)
    stages = await get_full_tournament_details(tournament_id)
    level_stages = [stage for stage in stages if stage.level_id == level_id]
    active_stage = next((stage for stage in level_stages if stage.is_active), None)
    pending_match_count = (
        get_pending_match_count_in_stage(active_stage) if active_stage is not None else 0
    )
    pending_matches_message = (
        get_pending_matches_message(pending_match_count) if pending_match_count > 0 else None
    )

    if pending_match_count > 0:
        return StageRankingResponse(
            data={},
            has_pending_matches=True,
            pending_match_count=pending_match_count,
            pending_matches_message=pending_matches_message,
        )

    next_stage_id = await get_next_stage_in_tournament(tournament_id, "next", level_id)

    if next_stage_id is None:
        return StageRankingResponse(
            data={},
            has_pending_matches=pending_match_count > 0,
            pending_match_count=pending_match_count,
            pending_matches_message=pending_matches_message,
        )

    return StageRankingResponse(
        data=await get_updates_to_inputs_in_activated_stage(tournament_id, next_stage_id),
        has_pending_matches=pending_match_count > 0,
        pending_match_count=pending_match_count,
        pending_matches_message=pending_matches_message,
    )
