"""Pure Swiss round pairing selector (issue #152)."""

from collections.abc import Sequence

from bracket.logic.scheduling.ladder_teams import get_possible_upcoming_matches_for_swiss
from bracket.models.db.match import MatchFilter
from bracket.models.db.stage_item_inputs import StageItemInput, StageItemInputFinal
from bracket.models.db.util import RoundWithMatches
from bracket.utils.id_types import StageItemInputId

SWISS_MATCH_FILTER = MatchFilter(
    elo_diff_threshold=200,
    iterations=2000,
    only_recommended=True,
    limit=50,
)


def select_round_pairing(
    inputs: Sequence[StageItemInput],
    previous_rounds: list[RoundWithMatches],
) -> tuple[list[tuple[StageItemInput, StageItemInput]], StageItemInput | None]:
    """Select a complete perfect matching + optional bye for one Swiss round.

    Uses hardcoded optimizer defaults (elo-diff 200, iterations 2000,
    only-recommended, limit 50) and greedy completion to guarantee a full
    matching even when the optimizer's suggestion list is short.
    """
    active = [i for i in inputs if not isinstance(i, StageItemInputFinal) or i.team.active]

    bye: StageItemInput | None = None
    if len(active) % 2 == 1:
        bye = _pick_bye(active, previous_rounds)
        pool = [i for i in active if i.id != bye.id]
    else:
        pool = list(active)

    suggestions = get_possible_upcoming_matches_for_swiss(SWISS_MATCH_FILTER, previous_rounds, pool)

    used: set[StageItemInputId] = set()
    pairs: list[tuple[StageItemInput, StageItemInput]] = []

    for sug in suggestions:
        id1 = sug.stage_item_input1.id
        id2 = sug.stage_item_input2.id
        if id1 not in used and id2 not in used:
            pairs.append((sug.stage_item_input1, sug.stage_item_input2))
            used.add(id1)
            used.add(id2)

    # Fallback: pair remaining inputs when the optimizer falls short (rematch may be unavoidable)
    remaining = [i for i in pool if i.id not in used]
    while len(remaining) >= 2:
        pairs.append((remaining[0], remaining[1]))
        remaining = remaining[2:]

    return pairs, bye


def _pick_bye(
    inputs: Sequence[StageItemInput],
    previous_rounds: list[RoundWithMatches],
) -> StageItemInput:
    """Rotate bye through inputs by round count, falling back to index 0."""
    return inputs[len(previous_rounds) % len(inputs)]
