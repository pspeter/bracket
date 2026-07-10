from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from heliclockter import datetime_utc
from starlette import status

from bracket.database import database
from bracket.logic.match_sets.pointer import IllegalMatchTransitionError
from bracket.logic.match_sets.validation import (
    validate_draws_allowed_for_end,
    validate_match_can_be_started,
)
from bracket.logic.ranking.elimination import get_started_elimination_followers
from bracket.logic.reconcile import reconcile_stage_item
from bracket.logic.scheduling.standings_resolution import is_standings_resolved_stage_type
from bracket.models.db.match import (
    Match,
    MatchSetScoreEditBody,
    MatchSetState,
    MatchState,
    MatchWithDetails,
    derive_match_state,
)
from bracket.models.db.stage_item import StageType
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.sql.match_sets import get_sets_for_match, sql_score_edit_match_set
from bracket.sql.matches import (
    sql_end_match,
    sql_get_match_with_details,
    sql_get_play_all_sets_for_match,
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

    if new_state is MatchState.COMPLETED and match.completed_at is None:
        await sql_set_match_completed_at(match.id, datetime_utc.now())
    elif new_state is not MatchState.COMPLETED and match.completed_at is not None:
        await sql_set_match_completed_at(match.id, None)

    # Fetched only now, after the completed_at write above: reconcile_stage_item's own
    # completed_at bookkeeping (bracket.logic.reconcile._sync_completed_at_for_stage_item)
    # compares each match's *snapshotted* completed_at against its (already up to date)
    # derived state, so fetching post-write here keeps this match a no-op for that step
    # instead of a redundant second write with a slightly later timestamp.
    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)

    await reconcile_stage_item(
        tournament_id,
        stage_item,
        changed_round_id=round_.id,
        changed_match_ids={match.id},
    )

    updated = await sql_get_match_with_details(tournament_id, match.id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find match with id {match.id}",
        )
    return updated


async def derive_match_state_after_change(tournament_id: TournamentId, match: Match) -> MatchState:
    sets = await get_sets_for_match(match.id)
    play_all_sets = await sql_get_play_all_sets_for_match(match.id)
    return derive_match_state(sets, play_all_sets=play_all_sets)


async def apply_match_change_and_recalculate(
    tournament_id: TournamentId,
    match: Match,
    apply_change: Callable[[], Awaitable[None]],
) -> MatchWithDetails:
    async with database.transaction():
        try:
            await apply_change()
        except IllegalMatchTransitionError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        new_state = await derive_match_state_after_change(tournament_id, match)
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
        await validate_match_can_be_started(tournament_id, match_with_sets, MatchState.IN_PROGRESS)
    return await apply_match_change_and_recalculate(
        tournament_id, match, lambda: sql_start_match(match.id)
    )


async def end_match_and_recalculate(tournament_id: TournamentId, match: Match) -> MatchWithDetails:
    sets = await get_sets_for_match(match.id)
    in_progress_set = next((s for s in sets if s.state is MatchSetState.IN_PROGRESS), None)
    if in_progress_set is not None:
        await validate_draws_allowed_for_end(tournament_id, match, in_progress_set)
    return await apply_match_change_and_recalculate(
        tournament_id, match, lambda: sql_end_match(match.id)
    )


async def reopen_match_and_recalculate(
    tournament_id: TournamentId, match: Match
) -> MatchWithDetails:
    return await apply_match_change_and_recalculate(
        tournament_id, match, lambda: sql_reopen_match(match.id)
    )


def _get_started_downstream_matches(
    stage_item: StageItemWithRounds, round_: RoundWithMatches, match: Match
) -> list[Match]:
    """Matches that would be affected by resetting ``match`` but have already started.

    No cascade may ever modify a downstream match that has started, so these are the matches
    that block a reset.
    """
    if stage_item.type == StageType.SINGLE_ELIMINATION:
        return get_started_elimination_followers(stage_item, {match.id})
    if is_standings_resolved_stage_type(stage_item.type):
        return [
            subsequent_match
            for subsequent_round in stage_item.rounds
            if subsequent_round.id > round_.id
            for subsequent_match in subsequent_round.matches
            if subsequent_match.state is not MatchState.NOT_STARTED
        ]
    return []


async def reset_match_and_recalculate(
    tournament_id: TournamentId, match: Match
) -> MatchWithDetails:
    round_ = await get_round_by_id(tournament_id, match.round_id)
    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)

    blockers = _get_started_downstream_matches(stage_item, round_, match)
    if blockers:
        blocker_names = ", ".join(str(blocker.id) for blocker in blockers)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot reset this match because downstream match(es) "
                f"{blocker_names} have already started. Reset the downstream match(es) first."
            ),
        )

    return await apply_match_change_and_recalculate(
        tournament_id, match, lambda: sql_reset_match(match.id)
    )
