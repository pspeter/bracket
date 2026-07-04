from fastapi import HTTPException
from starlette import status

from bracket.models.db.match import Match, MatchState
from bracket.models.db.stage_item_inputs import StageItemInputFinal
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
