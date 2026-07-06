"""Strategy registry for standings-resolved stage items.

A *standings-resolved* stage item resolves its rounds from the running standings: on creation it
gets a placeholder skeleton (rounds + slot-matches with no teams), and each round is *resolved*
(teams assigned to slots) only once its predecessor completes. The lifecycle machinery -- skeleton
placeholder creation, the resolution policy, and the resolution orchestrator -- is shared across
all such stage types. Each type plugs in two pure strategy functions plus a skeleton builder:

- the **pairing selector**: which inputs meet in a round, and who (if anyone) gets the bye;
- the **slot assigner**: which selected pair lands in which match slot.

Swiss and Mexicano are the registered types.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from bracket.logic.scheduling.mexicano_round_pairing import select_mexicano_round_pairing
from bracket.logic.scheduling.mexicano_skeleton import build_mexicano_skeleton
from bracket.logic.scheduling.mexicano_slot_assigner import assign_mexicano_pairs_to_slots
from bracket.logic.scheduling.swiss_round_pairing import select_round_pairing
from bracket.logic.scheduling.swiss_skeleton import (
    RoundSkeleton,
    SwissSkeleton,
    build_swiss_skeleton,
)
from bracket.logic.scheduling.swiss_slot_assigner import assign_pairs_to_slots
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.models.db.util import RoundWithMatches
from bracket.utils.id_types import StageItemInputId


class PairingSelector(Protocol):
    def __call__(
        self,
        inputs: Sequence[StageItemInput],
        previous_rounds: list[RoundWithMatches],
    ) -> tuple[list[tuple[StageItemInput, StageItemInput]], StageItemInput | None]: ...


class SlotAssigner(Protocol):
    def __call__(
        self,
        pairs: Sequence[tuple[StageItemInput, StageItemInput]],
        bye: StageItemInput | None,
        round_skeleton: RoundSkeleton,
    ) -> dict[int, StageItemInputId]: ...


class SkeletonBuilder(Protocol):
    def __call__(self, team_count: int, games_per_player: int) -> SwissSkeleton: ...


@dataclass(frozen=True)
class StandingsResolvedStrategy:
    """The pluggable strategy points that make a stage type standings-resolved."""

    pairing_selector: PairingSelector
    slot_assigner: SlotAssigner
    skeleton_builder: SkeletonBuilder


STANDINGS_RESOLVED_STRATEGIES: dict[StageType, StandingsResolvedStrategy] = {
    StageType.SWISS: StandingsResolvedStrategy(
        pairing_selector=select_round_pairing,
        slot_assigner=assign_pairs_to_slots,
        skeleton_builder=build_swiss_skeleton,
    ),
    StageType.MEXICANO: StandingsResolvedStrategy(
        pairing_selector=select_mexicano_round_pairing,
        slot_assigner=assign_mexicano_pairs_to_slots,
        skeleton_builder=build_mexicano_skeleton,
    ),
}


def is_standings_resolved_stage_type(stage_type: StageType) -> bool:
    """Whether rounds of this stage type are resolved from standings by the shared machinery."""
    return stage_type in STANDINGS_RESOLVED_STRATEGIES


def get_standings_resolved_strategy(stage_type: StageType) -> StandingsResolvedStrategy | None:
    """Return the registered strategy for a stage type, or None if it is not standings-resolved."""
    return STANDINGS_RESOLVED_STRATEGIES.get(stage_type)
