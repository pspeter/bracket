from bracket.models.db.match import MatchState
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.util import RoundWithMatches


def get_next_round_to_resolve(rounds: list[RoundWithMatches]) -> RoundWithMatches | None:
    """Return the next PLACEHOLDER round that is ready to resolve, or None.

    Round R is ready only when every match in round R-1 is COMPLETED.
    Resolution is strictly sequential.
    """
    sorted_rounds = sorted(rounds, key=lambda r: r.id)
    for i, round_ in enumerate(sorted_rounds):
        if round_.lifecycle_state != RoundLifecycleState.PLACEHOLDER:
            continue
        if i == 0:
            return round_
        prev_round = sorted_rounds[i - 1]
        if prev_round.matches and all(m.state == MatchState.COMPLETED for m in prev_round.matches):
            return round_
    return None
