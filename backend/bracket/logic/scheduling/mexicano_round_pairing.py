"""Pure Mexicano round pairing selector (issues #259, #260).

Opponents are re-drawn every round from the current standings: the field is sorted by cumulative
points scored (then set difference, point difference and finally input slot as the deterministic
tiebreaker) and adjacent teams are paired 1v2, 3v4, ... Rematches are allowed -- unlike Swiss no
history is consulted for pairing. Because the slot tiebreaker orders an all-zero field by builder
order, round 1 pairs strictly by the builder's input order.

For an odd number of active entrants, one sits out each round. The bye is picked by rotation --
whoever has sat out the fewest times so far, ties broken by ascending slot -- never by standings
position, so the bottom of the field is never trapped as the permanent sitter.
"""

from collections.abc import Sequence

from bracket.models.db.stage_item_inputs import StageItemInput, StageItemInputFinal
from bracket.models.db.util import RoundWithMatches


def select_mexicano_round_pairing(
    inputs: Sequence[StageItemInput],
    previous_rounds: list[RoundWithMatches],
) -> tuple[list[tuple[StageItemInput, StageItemInput]], StageItemInput | None]:
    """Pair adjacent teams by current standings for one Mexicano round.

    Returns ``(pairs, bye)``. An odd active field produces a bye picked by fewest-byes-so-far
    rotation before the remaining entrants are paired adjacently by standings.
    """
    active = [i for i in inputs if not isinstance(i, StageItemInputFinal) or i.team.active]

    bye: StageItemInput | None = None
    pool = active
    if len(active) % 2 == 1:
        bye = _pick_bye(active, previous_rounds)
        pool = [i for i in active if i.id != bye.id]

    ordered = sorted(
        pool,
        key=lambda i: (-i.points, -i.set_difference, -i.point_difference, i.slot),
    )

    pairs = [(ordered[i], ordered[i + 1]) for i in range(0, len(ordered) - 1, 2)]
    return pairs, bye


def _pick_bye(
    inputs: Sequence[StageItemInput],
    previous_rounds: list[RoundWithMatches],
) -> StageItemInput:
    """Pick the entrant with the fewest byes so far; ties break by ascending slot.

    A bye is detected the same way ranking compensation detects one: absence from a round's
    playing slots (``stage_item_input1_id``/``stage_item_input2_id``), never via the referee
    slot, which is a general-purpose feature and not a reliable bye marker.
    """
    bye_counts = {i.id: 0 for i in inputs}
    for round_ in previous_rounds:
        played_ids = {
            inp_id
            for match in round_.matches
            for inp_id in (match.stage_item_input1_id, match.stage_item_input2_id)
            if inp_id is not None
        }
        for i in inputs:
            if i.id not in played_ids:
                bye_counts[i.id] += 1

    return min(inputs, key=lambda i: (bye_counts[i.id], i.slot))
