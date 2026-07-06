"""Pure pair->slot assigner for Mexicano round resolution (issue #259).

The assigner is the identity: pairs arrive already ordered by standings (top pair first), so the
i-th pair is dropped into the i-th match slot. Combined with match slots taken in ascending order,
the top-standings pair always lands in the first match slot -- no fairness permutation search like
Swiss, because Mexicano deliberately re-draws opponents every round.
"""

from collections.abc import Sequence

from bracket.logic.scheduling.swiss_skeleton import RoundSkeleton
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.utils.id_types import StageItemInputId


def assign_mexicano_pairs_to_slots(
    pairs: Sequence[tuple[StageItemInput, StageItemInput]],
    bye: StageItemInput | None,
    round_skeleton: RoundSkeleton,
) -> dict[int, StageItemInputId]:
    """Map the i-th pair onto the i-th match slot (ascending slot order)."""
    match_slots = sorted(round_skeleton.matches, key=lambda slots: slots[0])
    mapping: dict[int, StageItemInputId] = {}
    for (slot1, slot2), (input1, input2) in zip(match_slots, pairs):
        mapping[slot1] = input1.id
        mapping[slot2] = input2.id

    if bye is not None and round_skeleton.bye_slot is not None:
        mapping[round_skeleton.bye_slot] = bye.id

    return mapping
