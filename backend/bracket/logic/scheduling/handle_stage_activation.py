from collections import defaultdict

from fastapi import HTTPException
from pydantic import BaseModel
from starlette import status

from bracket.database import database
from bracket.logic.ranking.calculation import (
    determine_team_ranking_for_stage_item,
)
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.logic.scheduling.swiss_round_pairing import select_round_pairing
from bracket.logic.scheduling.swiss_slot_assigner import (
    assign_pairs_to_slots,
    skeleton_from_slot_pairs,
)
from bracket.models.db.match import MatchState
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputEmpty,
    StageItemInputFinal,
    StageItemInputTentative,
)
from bracket.models.db.team import Team
from bracket.models.db.util import StageItemWithRounds, StageWithStageItems
from bracket.sql.matches import clear_scores_for_matches_in_stage_item, sql_set_input_ids_for_match
from bracket.sql.rankings import get_ranking_for_stage_item
from bracket.sql.referees import sql_set_match_referee_slot
from bracket.sql.rounds import set_round_lifecycle_state
from bracket.sql.stage_item_inputs import (
    get_stage_item_input_by_id,
    sql_set_team_id_for_stage_item_input,
)
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import (
    StageId,
    StageItemId,
    StageItemInputId,
    TournamentId,
)
from bracket.utils.types import assert_some

StageItemXTeamRanking = dict[StageItemId, list[tuple[StageItemInputId, TeamStatistics]]]


class StageItemInputUpdate(BaseModel):
    stage_item_input: StageItemInputTentative
    team: Team


def get_pending_matches_message(pending_match_count: int) -> str:
    match_label = "match" if pending_match_count == 1 else "matches"
    return (
        "The active stage still has pending matches. "
        f"Complete all {pending_match_count} pending {match_label} before "
        "starting the next stage."
    )


def get_pending_match_count_in_stage(stage: StageWithStageItems) -> int:
    return sum(
        1
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.state is not MatchState.COMPLETED
    )


def determine_team_id(
    winner_from_stage_item_id: StageItemId,
    winner_position: int,
    stage_item_x_team_rankings: StageItemXTeamRanking,
) -> StageItemInputId:
    """
    Determine the team ID for a stage item input that didn't have a team assigned yet.

    Returns a team that was chosen from a previous stage item ranking.
    """

    team_ranking = stage_item_x_team_rankings[winner_from_stage_item_id]
    msg = (
        "Winner position is out of range of ranking of previous stage item. "
        f"Ranking has size: {len(team_ranking)}, winner position: {winner_position}"
    )
    assert len(team_ranking) >= winner_position, msg
    return team_ranking[winner_position - 1][0]


async def get_team_update_for_input(
    tournament_id: TournamentId,
    stage_item_input: StageItemInputTentative,
    stage_item_x_team_rankings: StageItemXTeamRanking,
) -> StageItemInputUpdate:
    target_stage_item_input_id = determine_team_id(
        stage_item_input.winner_from_stage_item_id,
        stage_item_input.winner_position,
        stage_item_x_team_rankings,
    )
    target_stage_item_input = await get_stage_item_input_by_id(
        tournament_id, target_stage_item_input_id
    )
    if isinstance(target_stage_item_input, StageItemInputEmpty):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please first assign teams to all stage items in the current stage.",
        )

    assert isinstance(target_stage_item_input, StageItemInputFinal), (
        f"Unexpected stage item type: {type(target_stage_item_input)}"
    )
    return StageItemInputUpdate(
        stage_item_input=stage_item_input, team=target_stage_item_input.team
    )


async def get_team_rankings_lookup_for_tournament(
    tournament_id: TournamentId, stages: list[StageWithStageItems]
) -> StageItemXTeamRanking:
    stage_items = {
        stage_item.id: stage_item for stage in stages for stage_item in stage.stage_items
    }
    return {
        stage_item_id: determine_team_ranking_for_stage_item(
            stage_item,
            assert_some(await get_ranking_for_stage_item(tournament_id, stage_item.id)),
        )
        for stage_item_id, stage_item in stage_items.items()
    }


async def get_updates_to_inputs_in_activated_stage(
    tournament_id: TournamentId, stage_id: StageId
) -> dict[StageItemId, list[StageItemInputUpdate]]:
    """
    Gets the team_id updates for stage item inputs of the newly activated stage.
    """
    stages = await get_full_tournament_details(tournament_id)
    team_rankings_per_stage_item = await get_team_rankings_lookup_for_tournament(
        tournament_id, stages
    )
    activated_stage = next((stage for stage in stages if stage.id == stage_id), None)
    assert activated_stage

    result = defaultdict(list)

    for stage_item in activated_stage.stage_items:
        for stage_item_input in stage_item.inputs:
            if isinstance(stage_item_input, StageItemInputTentative):
                result[stage_item.id].append(
                    await get_team_update_for_input(
                        tournament_id, stage_item_input, team_rankings_per_stage_item
                    )
                )

    return dict(result)


async def _resolve_round_1_for_swiss_stage_item(
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    """Fill in concrete team assignments for round 1 of a Swiss stage item."""
    placeholder_round = next(
        (r for r in stage_item.rounds if r.lifecycle_state == RoundLifecycleState.PLACEHOLDER),
        None,
    )
    if placeholder_round is None:
        return

    inputs = [i for i in stage_item.inputs if isinstance(i, StageItemInputFinal) and i.team.active]
    if not inputs:
        return

    slot_pairs = [
        (m.input1_slot, m.input2_slot)
        for m in placeholder_round.matches
        if m.input1_slot is not None and m.input2_slot is not None
    ]
    bye_slot = next(
        (m.referee_slot for m in placeholder_round.matches if m.referee_slot is not None),
        None,
    )

    pairs, bye = select_round_pairing(inputs, [])
    skeleton = skeleton_from_slot_pairs(slot_pairs, bye_slot)
    slot_mapping = assign_pairs_to_slots(pairs, bye, skeleton)

    for match in placeholder_round.matches:
        if match.input1_slot is None or match.input2_slot is None:
            continue
        input1_id = slot_mapping.get(match.input1_slot)
        input2_id = slot_mapping.get(match.input2_slot)
        if input1_id is None or input2_id is None:
            continue
        await sql_set_input_ids_for_match(placeholder_round.id, match.id, [input1_id, input2_id])

        if match.referee_slot is not None:
            ref_id = slot_mapping.get(match.referee_slot)
            if ref_id is not None:
                await sql_set_match_referee_slot(match.id, ref_id)

    await set_round_lifecycle_state(
        placeholder_round.id, tournament_id, RoundLifecycleState.RESOLVED
    )


async def try_resolve_first_swiss_round_in_active_stage(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
) -> None:
    """Resolve round 1 of a Swiss stage item without waiting for stage activation.

    Round 1 of a Swiss stage item is normally resolved when its stage is activated. A Swiss
    stage item created inside an already-active stage would never get that hook again, so this
    resolves round 1 as soon as every input has a concrete team assigned. It is a no-op unless
    round 1 is still a placeholder, which keeps it safe to call repeatedly (e.g. once per team
    assignment). Callers must only invoke this for stage items in an active stage.

    The whole check-and-resolve runs under a transaction-scoped advisory lock keyed on the
    stage item, so concurrent team assignments (e.g. the parallel "auto-assign teams" feature)
    serialize: the first caller resolves round 1, the rest observe it is no longer a placeholder
    and return. This prevents two callers from interleaving their slot writes.

    Only round 1 is pre-resolved today; later rounds are resolved sequentially as matches
    complete. If we ever want to pre-resolve more than one round up front, this is the place to
    extend (the skeleton already defines slot pairings for every round).
    """
    async with database.transaction():
        await database.execute(
            query="SELECT pg_advisory_xact_lock(:lock_key)",
            values={"lock_key": int(stage_item_id)},
        )

        stage_item = await get_stage_item(tournament_id, stage_item_id)
        if stage_item.type is not StageType.SWISS:
            return

        # All inputs must reference concrete teams before we can pair round 1.
        if not stage_item.inputs or not all(
            isinstance(input_, StageItemInputFinal) for input_ in stage_item.inputs
        ):
            return

        first_round = min(stage_item.rounds, key=lambda round_: round_.id, default=None)
        if (
            first_round is None
            or first_round.lifecycle_state is not RoundLifecycleState.PLACEHOLDER
        ):
            return

        await _resolve_round_1_for_swiss_stage_item(tournament_id, stage_item)


async def update_matches_in_activated_stage(tournament_id: TournamentId, stage_id: StageId) -> None:
    """
    Sets the team_id for stage item inputs of the newly activated stage.
    For Swiss stage items also resolves round 1 placeholder matches.
    """
    updates_per_stage_item = await get_updates_to_inputs_in_activated_stage(tournament_id, stage_id)
    for stage_item_updates in updates_per_stage_item.values():
        for update in stage_item_updates:
            await sql_set_team_id_for_stage_item_input(
                tournament_id, update.stage_item_input.id, update.team.id
            )

    # Re-fetch after tentative inputs are resolved so inputs are Final
    stages = await get_full_tournament_details(tournament_id, stage_id=stage_id)
    activated_stage = next((s for s in stages if s.id == stage_id), None)
    if activated_stage is None:
        return

    for stage_item in activated_stage.stage_items:
        if stage_item.type == StageType.SWISS:
            await _resolve_round_1_for_swiss_stage_item(tournament_id, stage_item)


async def update_matches_in_deactivated_stage(
    tournament_id: TournamentId, deactivated_stage: StageWithStageItems
) -> None:
    """
    Unsets the team_id for stage item inputs of the newly deactivated stage.
    """
    for stage_item in deactivated_stage.stage_items:
        await clear_scores_for_matches_in_stage_item(tournament_id, stage_item.id)

        for stage_item_input in stage_item.inputs:
            if stage_item_input.winner_from_stage_item_id is not None:
                await sql_set_team_id_for_stage_item_input(tournament_id, stage_item_input.id, None)
