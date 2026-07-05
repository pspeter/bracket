"""The persistence seam for reconciliation: logic modules return a plan of writes; this module
crosses the database seam once.
"""

from collections.abc import Sequence

from bracket.database import database
from bracket.logic.plan import (
    AssignTeamToInput,
    PlanItem,
    SetMatchInputs,
    SetMatchRefereeSlot,
    SetRoundLifecycleState,
    SetTeamStats,
)
from bracket.sql.matches import sql_set_input_ids_for_match
from bracket.sql.referees import sql_set_match_referee_slot
from bracket.sql.rounds import set_round_lifecycle_state
from bracket.sql.stage_item_inputs import sql_set_team_id_for_stage_item_input
from bracket.sql.teams import update_team_stats
from bracket.utils.id_types import TournamentId


def ordered_team_assignment_writes(
    items: Sequence[AssignTeamToInput],
) -> list[AssignTeamToInput]:
    """Order a batch of ``AssignTeamToInput`` writes swap-safely.

    First NULL-clear every input whose team is actually changing, then write every final
    assignment. This makes any permutation of teams among the batch (e.g. a ranking edit that
    flips which position two dependent inputs track) safe with respect to the unique
    (stage_item_id, team_id) constraint: the intermediate NULL state never collides, because it
    is written for every changing row before any final value is written.
    """
    clears = [
        AssignTeamToInput(item.stage_item_input_id, None, item.previous_team_id)
        for item in items
        if item.previous_team_id is not None and item.previous_team_id != item.team_id
    ]
    return [*clears, *items]


async def apply_plan(tournament_id: TournamentId, plan: Sequence[PlanItem]) -> None:
    """The persistence seam for reconciliation: logic modules return a plan of writes; this
    module crosses the database seam once.

    Opens a single transaction (a savepoint when already nested inside one) and dispatches every
    plan item to the existing sql/ function that performs its write. ``AssignTeamToInput`` items
    are applied as a batch via ``ordered_team_assignment_writes`` for swap safety; every other
    item type is applied in the order it appears in the plan.
    """
    assignments = [item for item in plan if isinstance(item, AssignTeamToInput)]
    other_items = [item for item in plan if not isinstance(item, AssignTeamToInput)]

    async with database.transaction():
        for item in other_items:
            match item:
                case SetTeamStats(stage_item_input_id, stats):
                    await update_team_stats(tournament_id, stage_item_input_id, stats)
                case SetMatchInputs(round_id, match_id, input_ids):
                    await sql_set_input_ids_for_match(round_id, match_id, input_ids)
                case SetMatchRefereeSlot(match_id, stage_item_input_id):
                    await sql_set_match_referee_slot(match_id, stage_item_input_id)
                case SetRoundLifecycleState(round_id, state):
                    await set_round_lifecycle_state(round_id, tournament_id, state)

        for assignment in ordered_team_assignment_writes(assignments):
            await sql_set_team_id_for_stage_item_input(
                tournament_id, assignment.stage_item_input_id, assignment.team_id
            )
