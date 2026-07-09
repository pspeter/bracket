from collections import defaultdict

from bracket.logic.apply_plan import apply_plan
from bracket.logic.plan import PlanItem, SetMatchInputs
from bracket.models.db.match import Match, MatchState
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.models.db.util import StageItemWithRounds
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    TournamentId,
)


def _feeder_input_for_slot(
    subsequent_match: Match,
    slot: int,
    *,
    affected_matches: dict[MatchId, Match],
    cleared_match_ids: set[MatchId],
) -> tuple[bool, StageItemInput | None]:
    """Return (changed, new_value) for a slot; changed=False keeps the existing value."""
    winner_from_id = (
        subsequent_match.stage_item_input1_winner_from_match_id
        if slot == 0
        else subsequent_match.stage_item_input2_winner_from_match_id
    )
    if winner_from_id is None:
        return False, None

    if winner_from_id in cleared_match_ids:
        return True, None

    feeder = affected_matches.get(winner_from_id)
    if feeder is None:
        return False, None

    if feeder.state is not MatchState.COMPLETED:
        return True, None

    winner = feeder.get_winner()
    if winner is None:
        return False, None
    return True, winner


def get_inputs_to_update_in_subsequent_elimination_rounds(
    current_round_id: RoundId,
    stage_item: StageItemWithRounds,
    match_ids: set[MatchId] | None = None,
) -> dict[MatchId, Match]:
    """
    Determine the updates of stage item input IDs in the elimination tree.

    Crucial aspect is that entering a winner for a match will influence matches of subsequent
    rounds, because of the tree-like structure of elimination stage items.

    A follower whose current state is not NOT_STARTED is never touched: no cascade may modify
    a downstream match that has already started (the 409 guard in
    ``reset_match_and_recalculate`` is what prevents ever reaching this function with such a
    follower in play for a reset; for the winner-flip case on a score edit, the follower simply
    keeps its existing inputs, and anything it in turn feeds is therefore unaffected too).
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
            if subsequent_match.state is not MatchState.NOT_STARTED:
                # This follower has already started: it must never be touched by a cascade, and
                # since it never changes, nothing it feeds further downstream changes either.
                continue

            updated_inputs: list[StageItemInput | None] = [
                subsequent_match.stage_item_input1,
                subsequent_match.stage_item_input2,
            ]
            original_inputs = updated_inputs.copy()

            for slot in (0, 1):
                changed, resolved = _feeder_input_for_slot(
                    subsequent_match,
                    slot,
                    affected_matches=affected_matches,
                    cleared_match_ids=cleared_match_ids,
                )
                if changed:
                    updated_inputs[slot] = resolved

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
                    updated.stage_item_input1_winner_from_match_id is not None
                    and updated.stage_item_input1_id is None
                ) or (
                    updated.stage_item_input2_winner_from_match_id is not None
                    and updated.stage_item_input2_id is None
                )
                if updated.state is not MatchState.COMPLETED or has_unresolved_inputs:
                    cleared_match_ids.add(subsequent_match.id)

    return {
        match_id: match
        for match_id, match in affected_matches.items()
        if match_ids is None or match_id not in match_ids
    }


def get_started_elimination_followers(
    stage_item: StageItemWithRounds, feeder_match_ids: set[MatchId]
) -> list[Match]:
    """Return started (non-NOT_STARTED) matches reachable from ``feeder_match_ids`` via
    ``stage_item_input{1,2}_winner_from_match_id`` links.

    Used by the reset 409 guard: a feeder cannot be reset while a downstream match that depends
    on its result has already started. Traversal stops at a not-started follower, since it never
    completed and therefore never propagated a winner any further down the tree.
    """
    followers_by_feeder: dict[MatchId, list[Match]] = defaultdict(list)
    for round_ in stage_item.rounds:
        for match in round_.matches:
            for winner_from_id in (
                match.stage_item_input1_winner_from_match_id,
                match.stage_item_input2_winner_from_match_id,
            ):
                if winner_from_id is not None:
                    followers_by_feeder[winner_from_id].append(match)

    started: list[Match] = []
    seen: set[MatchId] = set()
    frontier = list(feeder_match_ids)
    while frontier:
        feeder_id = frontier.pop()
        for follower in followers_by_feeder.get(feeder_id, []):
            if follower.id in seen:
                continue
            seen.add(follower.id)
            if follower.state is not MatchState.NOT_STARTED:
                started.append(follower)
            else:
                frontier.append(follower.id)
    return started


def build_elimination_input_plan(updates: dict[MatchId, Match]) -> list[PlanItem]:
    return [
        SetMatchInputs(
            round_id=match.round_id,
            match_id=match.id,
            input_ids=[match.stage_item_input1_id, match.stage_item_input2_id],
        )
        for match in updates.values()
    ]


async def update_inputs_in_subsequent_elimination_rounds(
    tournament_id: TournamentId,
    current_round_id: RoundId,
    stage_item: StageItemWithRounds,
    match_ids: set[MatchId] | None = None,
) -> None:
    updates = get_inputs_to_update_in_subsequent_elimination_rounds(
        current_round_id, stage_item, match_ids
    )
    plan = build_elimination_input_plan(updates)
    # Skip empty plans to avoid opening a pointless transaction.
    if plan:
        await apply_plan(tournament_id, plan)


async def update_inputs_in_complete_elimination_stage_item(
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    # Each round's updates are computed by the pure planner against the same in-memory
    # stage_item, which never changes across this loop (only the database does), so later
    # iterations don't observe earlier ones' writes -- collecting every round's plan items and
    # applying them once at the end is equivalent to applying them one round at a time.
    plan: list[PlanItem] = [
        item
        for round_ in stage_item.rounds
        for item in build_elimination_input_plan(
            get_inputs_to_update_in_subsequent_elimination_rounds(round_.id, stage_item)
        )
    ]
    # Skip empty plans to avoid opening a pointless transaction.
    if plan:
        await apply_plan(tournament_id, plan)
