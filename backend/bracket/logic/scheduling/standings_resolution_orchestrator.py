from bracket.logic.apply_plan import apply_plan
from bracket.logic.plan import PlanItem, SetMatchInputs, SetMatchRefereeSlot, SetRoundLifecycleState
from bracket.logic.scheduling.standings_resolution import (
    get_standings_resolved_strategy,
    is_standings_resolved_stage_type,
)
from bracket.logic.scheduling.standings_resolution_policy import (
    get_next_round_to_resolve,
    get_rounds_to_re_resolve,
)
from bracket.logic.scheduling.swiss_slot_assigner import skeleton_from_slot_pairs
from bracket.models.db.match import MatchState
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, is_round_complete
from bracket.sql.stage_items import get_stage_item
from bracket.utils.id_types import TournamentId


def build_unwire_plan(fresh: StageItemWithRounds) -> list[PlanItem]:
    """Plan clearing team assignments and reverting RESOLVED rounds with incomplete predecessors.

    Skips rounds that have already started (any match not NOT_STARTED) or that are pinned:
    no cascade may ever modify a downstream round that has started, and pinned rounds are
    never touched by the automated policy (consistent with ``get_rounds_to_re_resolve``).
    """
    plan: list[PlanItem] = []
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
            is_round_complete(prev) for prev in predecessors if prev.matches
        )
        if predecessors_complete:
            continue

        for match in round_.matches:
            if match.stage_item_input1_id is not None or match.stage_item_input2_id is not None:
                plan.append(
                    SetMatchInputs(round_id=round_.id, match_id=match.id, input_ids=[None, None])
                )
        plan.append(
            SetRoundLifecycleState(round_id=round_.id, state=RoundLifecycleState.PLACEHOLDER)
        )
    return plan


async def unwire_rounds_with_incomplete_predecessor(
    tournament_id: TournamentId,
    fresh: StageItemWithRounds,
) -> bool:
    """Clear team assignments and revert RESOLVED rounds with incomplete predecessors.

    Returns whether anything changed (i.e. the plan was non-empty).
    """
    plan = build_unwire_plan(fresh)
    if plan:
        await apply_plan(tournament_id, plan)
    return bool(plan)


def build_round_assignment_plan(
    stage_item: StageItemWithRounds,
    round_: RoundWithMatches,
    *,
    advance_to_resolved: bool,
) -> list[PlanItem]:
    """Run pairing selection + slot assignment for a single round and plan the result.

    The pairing selector and slot assigner are looked up from the stage type's registered
    standings-resolved strategy. Shared by the auto-resolution passes below and by round-1
    resolution (``handle_stage_activation._resolve_round_1_for_standings_resolved_stage_item``),
    which resolves against a ``stage_item`` whose other rounds are still all PLACEHOLDER -- the
    same as this function computing an empty ``previous_rounds``.
    """
    strategy = get_standings_resolved_strategy(stage_item.type)
    if strategy is None:
        return []

    inputs = [i for i in stage_item.inputs if isinstance(i, StageItemInputFinal) and i.team.active]
    if not inputs:
        return []

    previous_rounds = [
        r
        for r in stage_item.rounds
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

    pairs, bye = strategy.pairing_selector(inputs, previous_rounds)
    skeleton = skeleton_from_slot_pairs(slot_pairs, bye_slot)
    slot_mapping = strategy.slot_assigner(pairs, bye, skeleton)

    plan: list[PlanItem] = []
    for match in round_.matches:
        if match.input1_slot is None or match.input2_slot is None:
            continue
        input1_id = slot_mapping.get(match.input1_slot)
        input2_id = slot_mapping.get(match.input2_slot)
        # If the active pool is smaller than this round's pre-built skeleton (a mid-tournament
        # deactivation shrinking the field, see issue #261), the pairing selector produces fewer
        # pairs than there are matches, so some slots have no mapping. Write [None, None] rather
        # than skipping: this both clears any stale assignment a since-deactivated input left
        # behind, and (via `is_round_complete`) keeps the surplus match from blocking the round.
        plan.append(
            SetMatchInputs(round_id=round_.id, match_id=match.id, input_ids=[input1_id, input2_id])
        )

        if match.referee_slot is not None:
            ref_id = slot_mapping.get(match.referee_slot)
            if ref_id is not None:
                plan.append(SetMatchRefereeSlot(match_id=match.id, stage_item_input_id=ref_id))

    if advance_to_resolved:
        plan.append(SetRoundLifecycleState(round_id=round_.id, state=RoundLifecycleState.RESOLVED))

    return plan


async def auto_resolve_next_round(
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    """After ranking recalculation, resolve or re-resolve rounds as the policy dictates.

    Applies to standings-resolved stage items only. Two passes:
    1. Resolve the next PLACEHOLDER round ready for initial resolution.
    2. Re-resolve any RESOLVED not-started non-pinned rounds (so upstream score corrections
       flow into future pairings while leaving pinned and locked rounds untouched).
    """
    if not is_standings_resolved_stage_type(stage_item.type):
        return

    # Re-fetch with up-to-date ELO after recalculate_ranking_for_stage_item
    fresh = await get_stage_item(tournament_id, stage_item.id)

    if await unwire_rounds_with_incomplete_predecessor(tournament_id, fresh):
        return

    # Pass 1: initial resolution of next PLACEHOLDER round
    next_placeholder = get_next_round_to_resolve(fresh.rounds)
    if next_placeholder is not None:
        round_ = next((r for r in fresh.rounds if r.id == next_placeholder.id), None)
        if round_ is not None and round_.lifecycle_state == RoundLifecycleState.PLACEHOLDER:
            plan = build_round_assignment_plan(fresh, round_, advance_to_resolved=True)
            await apply_plan(tournament_id, plan)
            # Refresh after the first resolution so pass 2 sees the updated state
            fresh = await get_stage_item(tournament_id, stage_item.id)

    # Pass 2: re-resolve RESOLVED not-started non-pinned rounds
    for candidate in get_rounds_to_re_resolve(fresh.rounds):
        round_ = next((r for r in fresh.rounds if r.id == candidate.id), None)
        if round_ is not None and round_.lifecycle_state == RoundLifecycleState.RESOLVED:
            plan = build_round_assignment_plan(fresh, round_, advance_to_resolved=False)
            await apply_plan(tournament_id, plan)
