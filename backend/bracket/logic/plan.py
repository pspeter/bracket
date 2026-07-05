"""Plan vocabulary for reconciliation writes.

Reconciliation logic (ranking recalculation, Swiss pairing, elimination cascades, dependent-input
resolution) decides *what* needs to change. Rather than each step welding that decision to its own
ad-hoc write loop, every step returns a list of these immutable plan items describing the writes
it wants made. ``bracket.logic.apply_plan.apply_plan`` is the only place that turns a plan into
actual database writes.
"""

from dataclasses import dataclass

from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.round import RoundLifecycleState
from bracket.utils.id_types import MatchId, RoundId, StageItemInputId, TeamId


@dataclass(frozen=True)
class SetTeamStats:
    stage_item_input_id: StageItemInputId
    stats: TeamStatistics


@dataclass(frozen=True)
class SetMatchInputs:
    round_id: RoundId
    match_id: MatchId
    input_ids: list[StageItemInputId | None]


@dataclass(frozen=True)
class SetMatchRefereeSlot:
    match_id: MatchId
    stage_item_input_id: StageItemInputId


@dataclass(frozen=True)
class SetRoundLifecycleState:
    round_id: RoundId
    state: RoundLifecycleState


@dataclass(frozen=True)
class AssignTeamToInput:
    """Assign (or clear, when ``team_id`` is None) the team of a stage item input.

    ``previous_team_id`` is the team currently assigned to this input (None if it has none yet).
    It carries no write of its own; it lets the applier order a batch of these swap-safely, since
    two sibling inputs trading teams would otherwise transiently violate the unique
    (stage_item_id, team_id) constraint.
    """

    stage_item_input_id: StageItemInputId
    team_id: TeamId | None
    previous_team_id: TeamId | None


PlanItem = (
    SetTeamStats | SetMatchInputs | SetMatchRefereeSlot | SetRoundLifecycleState | AssignTeamToInput
)
