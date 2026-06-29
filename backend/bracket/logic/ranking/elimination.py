from bracket.models.db.match import Match, MatchState, derive_match_state
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.models.db.util import StageItemWithRounds
from bracket.sql.matches import (
    sql_set_input_ids_for_match,
)
from bracket.utils.id_types import (
    MatchId,
    RoundId,
)

_UNCHANGED = object()


def _feeder_input_for_slot(
    subsequent_match: Match,
    slot: int,
    *,
    affected_matches: dict[MatchId, Match],
    cleared_match_ids: set[MatchId],
) -> StageItemInput | None | object:
    """Return the input for a slot, or _UNCHANGED if the existing value should be kept."""
    winner_from_id = (
        subsequent_match.stage_item_input1_winner_from_match_id
        if slot == 0
        else subsequent_match.stage_item_input2_winner_from_match_id
    )
    if winner_from_id is None:
        return _UNCHANGED

    if winner_from_id in cleared_match_ids:
        return None

    feeder = affected_matches.get(winner_from_id)
    if feeder is None:
        return _UNCHANGED

    if feeder.state is not MatchState.COMPLETED:
        return None

    winner = feeder.get_winner()
    if winner is None:
        return _UNCHANGED
    return winner


def get_inputs_to_update_in_subsequent_elimination_rounds(
    current_round_id: RoundId,
    stage_item: StageItemWithRounds,
    match_ids: set[MatchId] | None = None,
) -> dict[MatchId, Match]:
    """
    Determine the updates of stage item input IDs in the elimination tree.

    Crucial aspect is that entering a winner for a match will influence matches of subsequent
    rounds, because of the tree-like structure of elimination stage items.
    """
    current_round = next(round_ for round_ in stage_item.rounds if round_.id == current_round_id)
    affected_matches: dict[MatchId, Match] = {}
    cleared_match_ids: set[MatchId] = set()

    for match in current_round.matches:
        if match_ids is not None and match.id not in match_ids:
            continue
        if match.state is MatchState.COMPLETED:
            affected_matches[match.id] = match
        elif match_ids is not None:
            cleared_match_ids.add(match.id)

    subsequent_rounds = [round_ for round_ in stage_item.rounds if round_.id > current_round.id]
    subsequent_rounds.sort(key=lambda round_: round_.id)

    for subsequent_round in subsequent_rounds:
        for subsequent_match in subsequent_round.matches:
            updated_inputs: list[StageItemInput | None] = [
                subsequent_match.stage_item_input1,
                subsequent_match.stage_item_input2,
            ]
            original_inputs = updated_inputs.copy()

            for slot in (0, 1):
                resolved = _feeder_input_for_slot(
                    subsequent_match,
                    slot,
                    affected_matches=affected_matches,
                    cleared_match_ids=cleared_match_ids,
                )
                if resolved is not _UNCHANGED:
                    updated_inputs[slot] = resolved  # type: ignore[assignment]

            if original_inputs != updated_inputs:
                input_ids = [input_.id if input_ else None for input_ in updated_inputs]

                affected_matches[subsequent_match.id] = subsequent_match.model_copy(
                    update={
                        "stage_item_input1_id": input_ids[0],
                        "stage_item_input2_id": input_ids[1],
                        "stage_item_input1": updated_inputs[0],
                        "stage_item_input2": updated_inputs[1],
                    }
                )
                updated = affected_matches[subsequent_match.id]
                has_unresolved_inputs = (
                    (
                        updated.stage_item_input1_winner_from_match_id is not None
                        and updated.stage_item_input1_id is None
                    )
                    or (
                        updated.stage_item_input2_winner_from_match_id is not None
                        and updated.stage_item_input2_id is None
                    )
                )
                if (
                    derive_match_state(updated.match_sets) is not MatchState.COMPLETED
                    or has_unresolved_inputs
                ):
                    cleared_match_ids.add(subsequent_match.id)

    return {
        match_id: match
        for match_id, match in affected_matches.items()
        if match_ids is None or match_id not in match_ids
    }


async def update_inputs_in_subsequent_elimination_rounds(
    current_round_id: RoundId,
    stage_item: StageItemWithRounds,
    match_ids: set[MatchId] | None = None,
) -> None:
    updates = get_inputs_to_update_in_subsequent_elimination_rounds(
        current_round_id, stage_item, match_ids
    )
    for _, match in updates.items():
        await sql_set_input_ids_for_match(
            match.round_id, match.id, [match.stage_item_input1_id, match.stage_item_input2_id]
        )


async def update_inputs_in_complete_elimination_stage_item(
    stage_item: StageItemWithRounds,
) -> None:
    for round_ in stage_item.rounds:
        await update_inputs_in_subsequent_elimination_rounds(round_.id, stage_item)
