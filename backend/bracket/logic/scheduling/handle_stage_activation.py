from bracket.database import database
from bracket.logic.apply_plan import apply_plan
from bracket.logic.plan import AssignTeamToInput, PlanItem
from bracket.logic.ranking.calculation import (
    determine_team_ranking_for_stage_item,
)
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.logic.scheduling.standings_resolution import is_standings_resolved_stage_type
from bracket.logic.scheduling.standings_resolution_orchestrator import build_round_assignment_plan
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.util import StageItemWithRounds, StageWithStageItems, is_round_complete
from bracket.sql.rankings import get_ranking_for_stage_item
from bracket.sql.stage_item_inputs import get_stage_item_input_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import (
    StageItemId,
    StageItemInputId,
    TournamentId,
)
from bracket.utils.types import assert_some

StageItemXTeamRanking = dict[StageItemId, list[tuple[StageItemInputId, TeamStatistics]]]


def determine_team_id(
    winner_from_stage_item_id: StageItemId,
    winner_position: int,
    stage_item_x_team_rankings: StageItemXTeamRanking,
) -> StageItemInputId:
    """
    Determine the team ID for a stage item input that didn't have a team assigned yet.

    Returns a team that was chosen from a previous stage item ranking.
    """

    team_ranking = stage_item_x_team_rankings[winner_from_stage_item_id]
    msg = (
        "Winner position is out of range of ranking of previous stage item. "
        f"Ranking has size: {len(team_ranking)}, winner position: {winner_position}"
    )
    assert len(team_ranking) >= winner_position, msg
    return team_ranking[winner_position - 1][0]


async def get_team_rankings_lookup_for_tournament(
    tournament_id: TournamentId, stages: list[StageWithStageItems]
) -> StageItemXTeamRanking:
    stage_items = {
        stage_item.id: stage_item for stage in stages for stage_item in stage.stage_items
    }
    return {
        stage_item_id: determine_team_ranking_for_stage_item(
            stage_item,
            assert_some(await get_ranking_for_stage_item(tournament_id, stage_item.id)),
        )
        for stage_item_id, stage_item in stage_items.items()
    }


async def _resolve_round_1_for_standings_resolved_stage_item(
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    """Fill in concrete team assignments for round 1 of a standings-resolved stage item."""
    # Round 1 is the lowest-id round. Resolve that specific round rather than the first
    # placeholder in iteration order: the rounds can arrive in any order, so picking the first
    # placeholder could resolve a later round (leaving the real round 1 a placeholder that shows
    # TBD), and — once round 1 is resolved — could even mistake round 2 for round 1 and pair it
    # with round-1 logic. If the first round is already resolved, there is nothing to do here.
    first_round = min(stage_item.rounds, key=lambda round_: round_.id, default=None)
    if first_round is None or first_round.lifecycle_state is not RoundLifecycleState.PLACEHOLDER:
        return

    # build_round_assignment_plan derives previous_rounds from stage_item.rounds, which are all
    # still PLACEHOLDER at this point (round 1 is the very first round ever resolved), so it
    # naturally computes the same empty previous_rounds this used to pass explicitly.
    plan = build_round_assignment_plan(stage_item, first_round, advance_to_resolved=True)
    await apply_plan(tournament_id, plan)


async def try_resolve_first_round_when_inputs_filled(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
) -> None:
    """Resolve round 1 of a standings-resolved stage item as soon as all of its slots are filled.

    Round 1 is resolved once every input has a concrete team assigned. It is a no-op unless round 1
    is still a placeholder and every input is concrete, which keeps it safe to call repeatedly
    (e.g. once per team assignment) and on stage items whose inputs are still tentative.

    The whole check-and-resolve runs under a transaction-scoped advisory lock keyed on the
    stage item, so concurrent team assignments (e.g. the parallel "auto-assign teams" feature)
    serialize: the first caller resolves round 1, the rest observe it is no longer a placeholder
    and return. This prevents two callers from interleaving their slot writes.

    Only round 1 is pre-resolved today; later rounds are resolved sequentially as matches
    complete. If we ever want to pre-resolve more than one round up front, this is the place to
    extend (the skeleton already defines slot pairings for every round).
    """
    async with database.transaction():
        await database.execute(
            query="SELECT pg_advisory_xact_lock(:lock_key)",
            values={"lock_key": int(stage_item_id)},
        )

        stage_item = await get_stage_item(tournament_id, stage_item_id)
        if not is_standings_resolved_stage_type(stage_item.type):
            return

        # All inputs must reference concrete teams before we can pair round 1.
        if not stage_item.inputs or not all(
            isinstance(input_, StageItemInputFinal) for input_ in stage_item.inputs
        ):
            return

        first_round = min(stage_item.rounds, key=lambda round_: round_.id, default=None)
        if (
            first_round is None
            or first_round.lifecycle_state is not RoundLifecycleState.PLACEHOLDER
        ):
            return

        await _resolve_round_1_for_standings_resolved_stage_item(tournament_id, stage_item)


async def resolve_dependent_inputs_for_completed_stage_item(
    tournament_id: TournamentId,
    source_stage_item_id: StageItemId,
) -> None:
    """Resolve placeholder inputs that depend on a source stage item once it is complete.

    This is the auto-advance that replaces manual stage activation: as soon as every match in the
    source stage item is COMPLETED, any input elsewhere in the tournament of the form "winner
    (position N) of <source>" is resolved to the concrete team in that ranking position. It is
    safe to call on every score update — if the source is not complete yet it is a no-op, and once
    complete it always re-resolves (so a later score correction in the source flows downstream).
    """
    stages = await get_full_tournament_details(tournament_id)
    source_stage_item = next(
        (
            stage_item
            for stage in stages
            for stage_item in stage.stage_items
            if stage_item.id == source_stage_item_id
        ),
        None,
    )
    if source_stage_item is None:
        return

    source_matches = [match for round_ in source_stage_item.rounds for match in round_.matches]
    if not source_matches or not all(
        is_round_complete(round_) for round_ in source_stage_item.rounds
    ):
        return

    team_rankings = await get_team_rankings_lookup_for_tournament(tournament_id, stages)

    # Compute every target assignment before writing anything: sibling inputs of the same
    # dependent stage item may swap teams (e.g. a ranking edit flips positions 1 and 2 of the
    # source), and updating them one row at a time would transiently violate the unique
    # (stage_item_id, team_id) constraint. previous_team_id lets apply_plan order the batch
    # swap-safely.
    plan: list[PlanItem] = []
    affected_stage_item_ids: set[StageItemId] = set()
    for stage in stages:
        for stage_item in stage.stage_items:
            for stage_item_input in stage_item.inputs:
                if stage_item_input.winner_from_stage_item_id != source_stage_item_id:
                    continue

                target_input_id = determine_team_id(
                    source_stage_item_id,
                    assert_some(stage_item_input.winner_position),
                    team_rankings,
                )
                target_input = await get_stage_item_input_by_id(tournament_id, target_input_id)
                if not isinstance(target_input, StageItemInputFinal):
                    continue

                plan.append(
                    AssignTeamToInput(
                        stage_item_input_id=stage_item_input.id,
                        team_id=target_input.team.id,
                        previous_team_id=stage_item_input.team_id,
                    )
                )
                affected_stage_item_ids.add(stage_item.id)

    await apply_plan(tournament_id, plan)

    for stage_item_id in affected_stage_item_ids:
        affected_stage_item = await get_stage_item(tournament_id, stage_item_id)
        if is_standings_resolved_stage_type(affected_stage_item.type):
            await _resolve_round_1_for_standings_resolved_stage_item(
                tournament_id, affected_stage_item
            )
