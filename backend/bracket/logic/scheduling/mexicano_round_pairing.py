"""Pure Mexicano round pairing selector (issue #259).

Opponents are re-drawn every round from the current standings: the field is sorted by cumulative
points scored (then set difference, point difference and finally input slot as the deterministic
tiebreaker) and adjacent teams are paired 1v2, 3v4, ... Rematches are allowed -- unlike Swiss no
history is consulted. Because the slot tiebreaker orders an all-zero field by builder order, round
1 pairs strictly by the builder's input order.
"""

from collections.abc import Sequence

from bracket.models.db.stage_item_inputs import StageItemInput, StageItemInputFinal
from bracket.models.db.util import RoundWithMatches


def select_mexicano_round_pairing(
    inputs: Sequence[StageItemInput],
    previous_rounds: list[RoundWithMatches],
) -> tuple[list[tuple[StageItemInput, StageItemInput]], StageItemInput | None]:
    """Pair adjacent teams by current standings for one Mexicano round.

    Returns ``(pairs, bye)``. This even-count slice never produces a bye.
    """
    active = [i for i in inputs if not isinstance(i, StageItemInputFinal) or i.team.active]
    ordered = sorted(
        active,
        key=lambda i: (-i.points, -i.set_difference, -i.point_difference, i.slot),
    )

    pairs = [(ordered[i], ordered[i + 1]) for i in range(0, len(ordered) - 1, 2)]
    return pairs, None
