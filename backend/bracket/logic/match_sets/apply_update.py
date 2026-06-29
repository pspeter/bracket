from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from heliclockter import datetime_utc
from starlette import status

from bracket.database import database
from bracket.logic.match_sets.pointer import IllegalMatchTransitionError, IllegalSetTransitionError
from bracket.logic.match_sets.validation import validate_match_can_be_started
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import update_inputs_in_subsequent_elimination_rounds
from bracket.logic.scheduling.handle_stage_activation import (
    resolve_dependent_inputs_for_completed_stage_item,
)
from bracket.logic.scheduling.swiss_resolution_orchestrator import auto_resolve_next_swiss_round
from bracket.models.db.match import (
    Match,
    MatchSetBody,
    MatchSetScoreEditBody,
    MatchState,
    MatchWithDetails,
    derive_match_state,
)
from bracket.models.db.stage_item import StageType
from bracket.sql.match_sets import (
    get_sets_for_match,
    sql_score_edit_match_set,
    sql_update_match_set,
)
from bracket.sql.matches import (
    sql_end_match,
    sql_get_match_with_details,
    sql_reopen_match,
    sql_reset_match,
    sql_set_match_completed_at,
    sql_start_match,
)
from bracket.sql.rounds import get_round_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.utils.id_types import MatchSetId, TournamentId


async def recalculate_after_match_change(
    tournament_id: TournamentId,
    match: Match,
    *,
    new_state: MatchState,
) -> MatchWithDetails:
    round_ = await get_round_by_id(tournament_id, match.round_id)
    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)

    if new_state is MatchState.COMPLETED and match.completed_at is None:
        await sql_set_match_completed_at(match.id, datetime_utc.now())
    elif new_state is not MatchState.COMPLETED and match.completed_at is not None:
        await sql_set_match_completed_at(match.id, None)

    await recalculate_ranking_for_stage_item(tournament_id, stage_item)
    await auto_resolve_next_swiss_round(tournament_id, stage_item)

    if stage_item.type == StageType.SINGLE_ELIMINATION:
        await update_inputs_in_subsequent_elimination_rounds(round_.id, stage_item, {match.id})

    await resolve_dependent_inputs_for_completed_stage_item(tournament_id, stage_item.id)

    updated = await sql_get_match_with_details(tournament_id, match.id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find match with id {match.id}",
        )
    return updated


async def derive_match_state_after_change(tournament_id: TournamentId, match: Match) -> MatchState:
    sets = await get_sets_for_match(match.id)
    return derive_match_state(sets)


async def apply_match_change_and_recalculate(
    tournament_id: TournamentId,
    match: Match,
    apply_change: Callable[[], Awaitable[None]],
) -> MatchWithDetails:
    async with database.transaction():
        try:
            await apply_change()
        except (IllegalSetTransitionError, IllegalMatchTransitionError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        new_state = await derive_match_state_after_change(tournament_id, match)
        return await recalculate_after_match_change(tournament_id, match, new_state=new_state)


async def update_match_set_and_recalculate(
    tournament_id: TournamentId,
    match: Match,
    match_set_id: MatchSetId,
    body: MatchSetBody,
) -> MatchWithDetails:
    sets_before = await get_sets_for_match(match.id)
    match_with_sets = match.model_copy(update={"match_sets": sets_before})
    new_state = derive_match_state(
        [s if s.id != match_set_id else s.model_copy(update=body.model_dump()) for s in sets_before]
    )
    await validate_match_can_be_started(tournament_id, match_with_sets, new_state)

    async with database.transaction():
        try:
            await sql_update_match_set(match.id, match_set_id, body)
        except IllegalSetTransitionError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        return await recalculate_after_match_change(tournament_id, match, new_state=new_state)


async def score_edit_and_recalculate(
    tournament_id: TournamentId,
    match: Match,
    match_set_id: MatchSetId,
    body: MatchSetScoreEditBody,
) -> MatchWithDetails:
    async with database.transaction():
        await sql_score_edit_match_set(match.id, match_set_id, body)
        new_state = await derive_match_state_after_change(tournament_id, match)
        return await recalculate_after_match_change(tournament_id, match, new_state=new_state)


async def start_match_and_recalculate(
    tournament_id: TournamentId, match: Match
) -> MatchWithDetails:
    sets_before = await get_sets_for_match(match.id)
    match_with_sets = match.model_copy(update={"match_sets": sets_before})
    if match_with_sets.state is MatchState.NOT_STARTED:
        await validate_match_can_be_started(
            tournament_id, match_with_sets, MatchState.IN_PROGRESS
        )
    return await apply_match_change_and_recalculate(
        tournament_id, match, lambda: sql_start_match(match.id)
    )


async def end_match_and_recalculate(tournament_id: TournamentId, match: Match) -> MatchWithDetails:
    return await apply_match_change_and_recalculate(
        tournament_id, match, lambda: sql_end_match(match.id)
    )


async def reopen_match_and_recalculate(
    tournament_id: TournamentId, match: Match
) -> MatchWithDetails:
    return await apply_match_change_and_recalculate(
        tournament_id, match, lambda: sql_reopen_match(match.id)
    )


async def reset_match_and_recalculate(
    tournament_id: TournamentId, match: Match
) -> MatchWithDetails:
    return await apply_match_change_and_recalculate(
        tournament_id, match, lambda: sql_reset_match(match.id)
    )
