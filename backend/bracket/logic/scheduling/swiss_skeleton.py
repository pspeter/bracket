import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RoundSkeleton:
    matches: tuple[tuple[int, int], ...]
    bye_slot: int | None


@dataclass(frozen=True)
class SwissSkeleton:
    rounds: tuple[RoundSkeleton, ...]

    @property
    def round_count(self) -> int:
        return len(self.rounds)


def _circle_method(n: int) -> list[list[tuple[int, int]]]:
    """Round-robin schedule for n teams (n even) via circle method. Returns n-1 rounds."""
    teams = list(range(n))
    rounds = []
    for _ in range(n - 1):
        rounds.append([(teams[i], teams[n - 1 - i]) for i in range(n // 2)])
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds


def build_swiss_skeleton(team_count: int, games_per_player: int) -> SwissSkeleton:
    """
    Pure function: compute the round/match/bye structure for a Swiss stage item.

    Slots are 0-indexed integers.  For odd team_count a rotating bye is included;
    for even team_count every round is a perfect matching with no bye.
    The number of rounds is the minimum needed so every slot reaches at least
    games_per_player games.
    """
    has_bye = team_count % 2 == 1
    effective_n = team_count + 1 if has_bye else team_count

    if has_bye:
        rounds_needed = math.ceil(games_per_player * team_count / (team_count - 1))
    else:
        rounds_needed = games_per_player

    base = _circle_method(effective_n)

    result: list[RoundSkeleton] = []
    for i in range(rounds_needed):
        matches: list[tuple[int, int]] = []
        bye_slot: int | None = None
        for a, b in base[i % len(base)]:
            if a == team_count or b == team_count:
                bye_slot = b if a == team_count else a
            else:
                matches.append((a, b))
        result.append(RoundSkeleton(matches=tuple(matches), bye_slot=bye_slot))

    return SwissSkeleton(rounds=tuple(result))
