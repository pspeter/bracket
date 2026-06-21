"""Pure pair→slot assigner for Swiss round resolution (issue #152)."""

import itertools

from bracket.logic.scheduling.swiss_skeleton import RoundSkeleton
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.utils.id_types import StageItemInputId


def assign_pairs_to_slots(
    pairs: list[tuple[StageItemInput, StageItemInput]],
    bye: StageItemInput | None,
    round_skeleton: RoundSkeleton,
    previous_slot_assignments: list[dict[int, StageItemInputId]] | None = None,
) -> dict[int, StageItemInputId]:
    """Map pairs onto skeleton slot indices, keeping each pair in the same match slot.

    Returns {slot_index: stage_item_input_id}. The bye team is placed in the
    bye_slot (referee position) and does not occupy any playing slot.

    When previous_slot_assignments is provided, the function picks the permutation
    of pairs that minimises total slot reuse from prior rounds (fairness objective).
    """
    match_slots = list(round_skeleton.matches)
    best: dict[int, StageItemInputId] | None = None
    best_score = len(pairs) * 2 + 1  # worse than worst possible

    for pair_order in itertools.permutations(range(len(pairs))):
        candidate: dict[int, StageItemInputId] = {}
        for match_idx, pair_idx in enumerate(pair_order):
            slot1, slot2 = match_slots[match_idx]
            inp1, inp2 = pairs[pair_idx]
            candidate[slot1] = inp1.id
            candidate[slot2] = inp2.id

        score = _slot_reuse_count(candidate, previous_slot_assignments)
        if best is None or score < best_score:
            best = candidate
            best_score = score

    assert best is not None
    if bye is not None and round_skeleton.bye_slot is not None:
        best[round_skeleton.bye_slot] = bye.id

    return best


def skeleton_from_slot_pairs(
    slot_pairs: list[tuple[int, int]],
    bye_slot: int | None,
) -> RoundSkeleton:
    """Reconstruct a RoundSkeleton from a round's match slot pairs and bye slot."""
    return RoundSkeleton(matches=tuple(slot_pairs), bye_slot=bye_slot)


def _slot_reuse_count(
    candidate: dict[int, StageItemInputId],
    history: list[dict[int, StageItemInputId]] | None,
) -> int:
    """Count how many teams are in the same slot they occupied in the most recent round."""
    if not history:
        return 0
    prev = history[-1]
    return sum(1 for slot, inp_id in candidate.items() if prev.get(slot) == inp_id)
