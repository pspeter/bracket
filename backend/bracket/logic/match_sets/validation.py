from fastapi import HTTPException
from starlette import status

from bracket.models.db.match import (
    Match,
    MatchSet,
    MatchSetScoreEditBody,
    MatchSetState,
    MatchState,
)
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.sql.rankings import get_ranking_for_stage_item
from bracket.sql.rounds import get_round_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import TournamentId


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
                        match = next((m for m in round_.matches if m.id == existing_match.id), None)
                        if (
                            match is not None
                            and isinstance(match.stage_item_input1, StageItemInputFinal)
                            and isinstance(match.stage_item_input2, StageItemInputFinal)
                        ):
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


async def _draws_allowed_for_match(tournament_id: TournamentId, match: Match) -> bool:
    round_ = await get_round_by_id(tournament_id, match.round_id)
    stage_item = await get_stage_item(tournament_id, round_.stage_item_id)
    ranking = await get_ranking_for_stage_item(tournament_id, stage_item.id)
    return ranking is None or ranking.draws_allowed


async def validate_draws_allowed_for_end(
    tournament_id: TournamentId, match: Match, in_progress_set: MatchSet
) -> None:
    if in_progress_set.stage_item_input1_score != in_progress_set.stage_item_input2_score:
        return
    if not await _draws_allowed_for_match(tournament_id, match):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot end: draws are not allowed for this ranking",
        )


async def validate_draws_allowed_for_score_edit(
    tournament_id: TournamentId,
    match: Match,
    current_set_state: MatchSetState,
    body: MatchSetScoreEditBody,
) -> None:
    if current_set_state is not MatchSetState.COMPLETED:
        return
    if body.stage_item_input1_score != body.stage_item_input2_score:
        return
    if not await _draws_allowed_for_match(tournament_id, match):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit: draws are not allowed for this ranking",
        )
