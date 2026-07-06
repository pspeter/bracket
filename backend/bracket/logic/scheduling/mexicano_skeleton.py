"""Pure Mexicano placeholder skeleton builder (issues #259, #260).

Mexicano is a standings-resolved, dynamic-round-count stage type. Unlike Swiss it does not
draw its structure from a round-robin schedule: every round has the same fixed shape -- adjacent
slots paired (0,1), (2,3), (4,5), ... -- and the running standings decide which team occupies
which slot when the round is resolved.

For an odd entrant count, one slot per round is reserved as a rotating bye (mirroring the Swiss
odd-count handling): the last slot never plays and is instead assigned to whichever entrant sits
out that round. The round count is bumped to ``ceil(games_per_player * n / (n - 1))`` -- the same
formula Swiss uses -- so every entrant still reaches at least ``games_per_player`` games despite
one round in every ``n`` being a bye for them.
"""

import math

from bracket.logic.scheduling.swiss_skeleton import RoundSkeleton, SwissSkeleton


def build_mexicano_skeleton(team_count: int, games_per_player: int) -> SwissSkeleton:
    """Compute the round/match structure for a Mexicano stage item.

    Produces identical rounds, each pairing adjacent slots. For an even ``team_count`` there is
    no bye and ``games_per_player`` rounds are produced. For an odd ``team_count`` the last slot
    is reserved as a bye every round, and the round count follows the Swiss odd-count formula.
    """
    has_bye = team_count % 2 == 1
    playing_count = team_count - 1 if has_bye else team_count
    bye_slot = team_count - 1 if has_bye else None
    rounds_needed = (
        math.ceil(games_per_player * team_count / (team_count - 1)) if has_bye else games_per_player
    )

    matches = tuple((slot, slot + 1) for slot in range(0, playing_count, 2))
    rounds = tuple(RoundSkeleton(matches=matches, bye_slot=bye_slot) for _ in range(rounds_needed))
    return SwissSkeleton(rounds=rounds)
