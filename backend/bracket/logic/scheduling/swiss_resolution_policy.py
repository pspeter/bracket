from bracket.models.db.match import MatchState
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.util import RoundWithMatches


def get_rounds_to_re_resolve(rounds: list[RoundWithMatches]) -> list[RoundWithMatches]:
    """Return all RESOLVED not-started non-pinned rounds eligible for re-resolution.

    These are rounds where team assignments can be overwritten by an upstream score correction.
    Pinned rounds (is_pinned=True) are never touched by the automated policy.
    """
    return [
        r
        for r in rounds
        if r.lifecycle_state == RoundLifecycleState.RESOLVED
        and all(m.state == MatchState.NOT_STARTED for m in r.matches)
        and not r.is_pinned
    ]


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
