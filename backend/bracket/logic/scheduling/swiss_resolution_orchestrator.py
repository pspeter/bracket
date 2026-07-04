from bracket.logic.scheduling.swiss_resolution_policy import (
    get_next_round_to_resolve,
    get_rounds_to_re_resolve,
)
from bracket.logic.scheduling.swiss_round_pairing import select_round_pairing
from bracket.logic.scheduling.swiss_slot_assigner import (
    assign_pairs_to_slots,
    skeleton_from_slot_pairs,
)
from bracket.models.db.match import MatchState
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.sql.matches import sql_set_input_ids_for_match
from bracket.sql.referees import sql_set_match_referee_slot
from bracket.sql.rounds import set_round_lifecycle_state
from bracket.sql.stage_items import get_stage_item
from bracket.utils.id_types import TournamentId


async def unwire_swiss_rounds_with_incomplete_predecessor(
    tournament_id: TournamentId,
    fresh: StageItemWithRounds,
) -> bool:
    """Clear team assignments and revert RESOLVED rounds with incomplete predecessors.

    Skips rounds that have already started (any match not NOT_STARTED) or that are pinned:
    no cascade may ever modify a downstream round that has started, and pinned rounds are
    never touched by the automated policy (consistent with ``get_rounds_to_re_resolve``).
    """
    changed = False
    sorted_rounds = sorted(fresh.rounds, key=lambda r: r.id)
    for i, round_ in enumerate(sorted_rounds):
        if round_.lifecycle_state is not RoundLifecycleState.RESOLVED:
            continue
        if round_.is_pinned:
            continue
        if any(m.state is not MatchState.NOT_STARTED for m in round_.matches):
            continue
        predecessors = sorted_rounds[:i]
        if not predecessors:
            continue
        predecessors_complete = all(
            all(m.state is MatchState.COMPLETED for m in prev.matches)
            for prev in predecessors
            if prev.matches
        )
        if predecessors_complete:
            continue

        for match in round_.matches:
            if match.stage_item_input1_id is not None or match.stage_item_input2_id is not None:
                await sql_set_input_ids_for_match(round_.id, match.id, [None, None])
                changed = True
        await set_round_lifecycle_state(round_.id, tournament_id, RoundLifecycleState.PLACEHOLDER)
        changed = True
    return changed


async def _assign_teams_to_round(
    tournament_id: TournamentId,
    fresh: StageItemWithRounds,
    round_: RoundWithMatches,
    *,
    advance_to_resolved: bool,
) -> None:
    """Run pairing selection + slot assignment for a single round and persist the result."""
    inputs = [i for i in fresh.inputs if isinstance(i, StageItemInputFinal) and i.team.active]
    if not inputs:
        return

    previous_rounds = [
        r
        for r in fresh.rounds
        if r.lifecycle_state != RoundLifecycleState.PLACEHOLDER and r.id != round_.id
    ]

    slot_pairs = [
        (m.input1_slot, m.input2_slot)
        for m in round_.matches
        if m.input1_slot is not None and m.input2_slot is not None
    ]
    bye_slot = next(
        (m.referee_slot for m in round_.matches if m.referee_slot is not None),
        None,
    )

    pairs, bye = select_round_pairing(inputs, previous_rounds)
    skeleton = skeleton_from_slot_pairs(slot_pairs, bye_slot)
    slot_mapping = assign_pairs_to_slots(pairs, bye, skeleton)

    for match in round_.matches:
        if match.input1_slot is None or match.input2_slot is None:
            continue
        input1_id = slot_mapping.get(match.input1_slot)
        input2_id = slot_mapping.get(match.input2_slot)
        if input1_id is None or input2_id is None:
            continue
        await sql_set_input_ids_for_match(round_.id, match.id, [input1_id, input2_id])

        if match.referee_slot is not None:
            ref_id = slot_mapping.get(match.referee_slot)
            if ref_id is not None:
                await sql_set_match_referee_slot(match.id, ref_id)

    if advance_to_resolved:
        await set_round_lifecycle_state(round_.id, tournament_id, RoundLifecycleState.RESOLVED)


async def auto_resolve_next_swiss_round(
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    """After ranking recalculation, resolve or re-resolve Swiss rounds as the policy dictates.

    Two passes:
    1. Resolve the next PLACEHOLDER round ready for initial resolution.
    2. Re-resolve any RESOLVED not-started non-pinned rounds (so upstream score corrections
       flow into future pairings while leaving pinned and locked rounds untouched).
    """
    if stage_item.type != StageType.SWISS:
        return

    # Re-fetch with up-to-date ELO after recalculate_ranking_for_stage_item
    fresh = await get_stage_item(tournament_id, stage_item.id)

    if await unwire_swiss_rounds_with_incomplete_predecessor(tournament_id, fresh):
        return

    # Pass 1: initial resolution of next PLACEHOLDER round
    next_placeholder = get_next_round_to_resolve(fresh.rounds)
    if next_placeholder is not None:
        round_ = next((r for r in fresh.rounds if r.id == next_placeholder.id), None)
        if round_ is not None and round_.lifecycle_state == RoundLifecycleState.PLACEHOLDER:
            await _assign_teams_to_round(tournament_id, fresh, round_, advance_to_resolved=True)
            # Refresh after the first resolution so pass 2 sees the updated state
            fresh = await get_stage_item(tournament_id, stage_item.id)

    # Pass 2: re-resolve RESOLVED not-started non-pinned rounds
    for candidate in get_rounds_to_re_resolve(fresh.rounds):
        round_ = next((r for r in fresh.rounds if r.id == candidate.id), None)
        if round_ is not None and round_.lifecycle_state == RoundLifecycleState.RESOLVED:
            await _assign_teams_to_round(tournament_id, fresh, round_, advance_to_resolved=False)
