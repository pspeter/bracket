from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import (
    update_inputs_in_complete_elimination_stage_item,
    update_inputs_in_subsequent_elimination_rounds,
)
from bracket.logic.scheduling.handle_stage_activation import (
    resolve_dependent_inputs_for_completed_stage_item,
)
from bracket.logic.scheduling.swiss_resolution_orchestrator import (
    auto_resolve_next_swiss_round,
)
from bracket.models.db.stage_item import StageType
from bracket.models.db.util import StageItemWithRounds
from bracket.utils.id_types import MatchId, RoundId, TournamentId


async def reconcile_stage_item(
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
    *,
    changed_round_id: RoundId | None = None,
    changed_match_ids: set[MatchId] | None = None,
) -> None:
    """Reconciliation.

    After anything moves a stage item's standings (score change, ranking config edit, round
    deletion, stage item rebuild), bring every standings-derived structure back in line: team
    stats/ELO, Swiss round pairings, elimination-tree inputs, and cross-stage-item inputs that
    reference this item's final ranking. Callers state THAT standings moved; this module decides
    what follows. All steps are idempotent no-ops when nothing they manage changed.
    """
    if changed_match_ids is not None and changed_round_id is None:
        raise ValueError("changed_match_ids may only be passed together with changed_round_id")

    await recalculate_ranking_for_stage_item(tournament_id, stage_item)
    await auto_resolve_next_swiss_round(tournament_id, stage_item)

    if stage_item.type is StageType.SINGLE_ELIMINATION:
        if changed_round_id is not None:
            await update_inputs_in_subsequent_elimination_rounds(
                tournament_id, changed_round_id, stage_item, changed_match_ids
            )
        else:
            await update_inputs_in_complete_elimination_stage_item(tournament_id, stage_item)

    await resolve_dependent_inputs_for_completed_stage_item(tournament_id, stage_item.id)
