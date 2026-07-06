"""Pure Mexicano placeholder skeleton builder (issue #259).

Mexicano is a standings-resolved, dynamic-round-count stage type. Unlike Swiss it does not
draw its structure from a round-robin schedule: every round has the same fixed shape -- adjacent
slots paired (0,1), (2,3), (4,5), ... -- and the running standings decide which team occupies
which slot when the round is resolved. This even-count slice rejects odd entrant counts; byes
land in a later slice.
"""

from bracket.logic.scheduling.swiss_skeleton import RoundSkeleton, SwissSkeleton


def build_mexicano_skeleton(team_count: int, games_per_player: int) -> SwissSkeleton:
    """Compute the round/match structure for a Mexicano stage item.

    Produces ``games_per_player`` identical rounds, each pairing adjacent slots with no bye.
    Reuses the ``SwissSkeleton``/``RoundSkeleton`` containers shared by all standings-resolved
    stage types. Odd ``team_count`` is not supported in this slice.
    """
    if team_count % 2 != 0:
        raise ValueError("Mexicano requires an even number of entrants")

    matches = tuple((slot, slot + 1) for slot in range(0, team_count, 2))
    rounds = tuple(RoundSkeleton(matches=matches, bye_slot=None) for _ in range(games_per_player))
    return SwissSkeleton(rounds=rounds)
