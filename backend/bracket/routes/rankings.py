from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import database
from bracket.logic.reconcile import reconcile_stage_item
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.ranking import RankingBody, RankingCreateBody
from bracket.models.db.stage_item import StageType
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    user_authenticated_for_tournament,
    user_authenticated_or_public_dashboard,
)
from bracket.routes.models import (
    RankingsResponse,
    SuccessResponse,
)
from bracket.routes.util import disallow_archived_tournament
from bracket.sql.match_sets import (
    sql_ranking_has_active_sets,
    sql_resize_sets_for_ranking,
)
from bracket.sql.rankings import (
    get_all_rankings_in_tournament,
    sql_create_ranking,
    sql_delete_ranking,
    sql_update_ranking,
)
from bracket.sql.stage_item_inputs import get_stage_item_ids_by_ranking_id
from bracket.sql.stage_items import get_stage_item, get_stage_items_for_ranking
from bracket.utils.id_types import RankingId, TournamentId

router = APIRouter(prefix=config.api_prefix)


def _normalize_best_of_n_invariants(ranking_body: RankingBody) -> RankingBody:
    """Enforce the best-of-n coupling between `play_all_sets`, `num_sets` and `draws_allowed`.

    Best-of-n mode is active whenever `play_all_sets` is off and `num_sets` is greater than
    one. In that mode an even `num_sets` can never produce a clean set-win majority, so it is
    rejected with a 422 (mirroring the existing even-sets/single-elimination check below).
    `draws_allowed` is silently normalized to false, since best-of-n depends on every set
    having a winner to guarantee the match does too. Single-set rankings and rankings with
    `play_all_sets` on are untouched.
    """
    if ranking_body.play_all_sets or ranking_body.num_sets <= 1:
        return ranking_body

    if ranking_body.num_sets % 2 == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "Even number of sets is not supported in best-of-n mode (play out all sets off)."
            ),
        )

    if ranking_body.draws_allowed:
        return ranking_body.model_copy(update={"draws_allowed": False})

    return ranking_body


@router.get("/tournaments/{tournament_id}/rankings")
async def get_rankings(
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_or_public_dashboard),
) -> RankingsResponse:
    return RankingsResponse(data=await get_all_rankings_in_tournament(tournament_id))


@router.put("/tournaments/{tournament_id}/rankings/{ranking_id}")
async def update_ranking_by_id(
    tournament_id: TournamentId,
    ranking_id: RankingId,
    ranking_body: RankingBody,
    force: bool = False,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    ranking_body = _normalize_best_of_n_invariants(ranking_body)

    if ranking_body.num_sets % 2 == 0:
        stage_items_for_ranking = await get_stage_items_for_ranking(tournament_id, ranking_id)
        if any(si.type == StageType.SINGLE_ELIMINATION for si in stage_items_for_ranking):
            raise HTTPException(
                status_code=422,
                detail="Even number of sets is not supported for single elimination brackets.",
            )

    # Detect a change to a field that feeds match state derivation, so existing matches' set
    # rows/states can be reconciled. `num_sets` changes existing matches' set rows (resized);
    # `play_all_sets` changes how the same set rows derive a match's state (e.g. a decided
    # best-of-n match can complete or regress instantly). Both are destructive when matches
    # already have in-progress or completed sets, so they are refused with a 409 unless
    # explicitly forced. `draws_allowed` has no derived-state impact and stays ungated.
    existing_rankings = await get_all_rankings_in_tournament(tournament_id)
    existing_ranking = next((r for r in existing_rankings if r.id == ranking_id), None)
    old_num_sets = existing_ranking.num_sets if existing_ranking else ranking_body.num_sets
    old_play_all_sets = (
        existing_ranking.play_all_sets if existing_ranking else ranking_body.play_all_sets
    )

    derived_state_config_changed = (
        ranking_body.num_sets != old_num_sets or ranking_body.play_all_sets != old_play_all_sets
    )

    if derived_state_config_changed and not force:
        if await sql_ranking_has_active_sets(ranking_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Matches with in-progress or completed sets exist. Pass force=true to proceed."
                ),
            )

    # The ranking update, the set resize it triggers, and the dependent ranking
    # recalculations must be atomic, so set rows can't be left inconsistent with the ranking's
    # num_sets if a later step fails.
    async with database.transaction():
        await sql_update_ranking(
            tournament_id=tournament_id,
            ranking_id=ranking_id,
            ranking_body=ranking_body,
        )

        if ranking_body.num_sets != old_num_sets:
            await sql_resize_sets_for_ranking(ranking_id, old_num_sets, ranking_body.num_sets)

        stage_item_ids = await get_stage_item_ids_by_ranking_id(ranking_id)
        for stage_item_id in stage_item_ids:
            stage_item = await get_stage_item(tournament_id, stage_item_id)
            await reconcile_stage_item(tournament_id, stage_item)
    return SuccessResponse()


@router.delete("/tournaments/{tournament_id}/rankings/{ranking_id}")
async def delete_ranking(
    tournament_id: TournamentId,
    ranking_id: RankingId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    await sql_delete_ranking(tournament_id, ranking_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/rankings")
async def create_ranking(
    ranking_body: RankingCreateBody,
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    ranking_body = _normalize_best_of_n_invariants(ranking_body)

    existing_rankings = await get_all_rankings_in_tournament(tournament_id)
    check_requirement(existing_rankings, user, "max_rankings")

    highest_position = (
        max(x.position for x in existing_rankings) if len(existing_rankings) > 0 else -1
    )
    await sql_create_ranking(tournament_id, ranking_body, highest_position + 1)
    return SuccessResponse()
