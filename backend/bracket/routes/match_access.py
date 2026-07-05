from typing import NamedTuple

from fastapi import Depends, HTTPException
from starlette import status

from bracket.models.db.match import Match
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    tournament_by_score_tracking_token,
    user_authenticated_for_tournament,
)
from bracket.routes.util import match_dependency
from bracket.utils.id_types import MatchId, TournamentId


class ResolvedMatch(NamedTuple):
    """The (tournament, match) pair a verb operates on, resolved by whichever adapter
    authorized the request: an authenticated user, or a score-tracking token."""

    tournament_id: TournamentId
    match: Match


def _raise_if_unscheduled(match: Match) -> None:
    if match.start_time is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Could not find scheduled match"
        )


async def resolved_match_via_auth(
    tournament_id: TournamentId,
    match_id: MatchId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> ResolvedMatch:
    match = await match_dependency(tournament_id, match_id)
    return ResolvedMatch(tournament_id=tournament_id, match=match)


async def resolved_scheduled_match_via_auth(
    tournament_id: TournamentId,
    match_id: MatchId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> ResolvedMatch:
    match = await match_dependency(tournament_id, match_id)
    _raise_if_unscheduled(match)
    return ResolvedMatch(tournament_id=tournament_id, match=match)


async def resolved_match_via_token(
    match_id: MatchId,
    tournament: Tournament = Depends(tournament_by_score_tracking_token),
) -> ResolvedMatch:
    match = await match_dependency(tournament.id, match_id)
    _raise_if_unscheduled(match)
    return ResolvedMatch(tournament_id=tournament.id, match=match)
