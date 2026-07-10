from heliclockter import datetime_utc

from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import (
    update_inputs_in_complete_elimination_stage_item,
    update_inputs_in_subsequent_elimination_rounds,
)
from bracket.logic.scheduling.handle_stage_activation import (
    resolve_dependent_inputs_for_completed_stage_item,
)
from bracket.logic.scheduling.standings_resolution_orchestrator import (
    auto_resolve_next_round,
)
from bracket.models.db.match import MatchState
from bracket.models.db.stage_item import StageType
from bracket.models.db.util import StageItemWithRounds
from bracket.sql.matches import sql_set_match_completed_at
from bracket.utils.id_types import MatchId, RoundId, TournamentId


async def _sync_completed_at_for_stage_item(stage_item: StageItemWithRounds) -> None:
    """Keep every match's `completed_at` in lockstep with its derived `state`.

    Match state is fully derived from its sets (and the ranking's `play_all_sets` flag), so it
    can flip for many matches at once purely from a ranking config edit -- with no single-match
    transition (`bracket.logic.match_sets.apply_update`) in the loop to stamp/clear
    `completed_at` itself. This mirrors that path's own bookkeeping so any reconciliation, not
    just a per-match one, leaves `completed_at` consistent with the state it is derived
    alongside. A no-op for matches whose `completed_at` already agrees with their state.
    """
    now = datetime_utc.now()
    for round_ in stage_item.rounds:
        for match in round_.matches:
            if match.state is MatchState.COMPLETED and match.completed_at is None:
                await sql_set_match_completed_at(match.id, now)
            elif match.state is not MatchState.COMPLETED and match.completed_at is not None:
                await sql_set_match_completed_at(match.id, None)


async def reconcile_stage_item(
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
    *,
    changed_round_id: RoundId | None = None,
    changed_match_ids: set[MatchId] | None = None,
) -> None:
    """Reconciliation.

    After anything moves a stage item's standings (score change, ranking config edit, round
    deletion, stage item rebuild), bring every standings-derived structure back in line: match
    `completed_at`, team stats/ELO, Swiss round pairings, elimination-tree inputs, and
    cross-stage-item inputs that reference this item's final ranking. Callers state THAT
    standings moved; this module decides what follows. All steps are idempotent no-ops when
    nothing they manage changed.
    """
    if changed_match_ids is not None and changed_round_id is None:
        raise ValueError("changed_match_ids may only be passed together with changed_round_id")

    await _sync_completed_at_for_stage_item(stage_item)
    await recalculate_ranking_for_stage_item(tournament_id, stage_item)
    await auto_resolve_next_round(tournament_id, stage_item)

    if stage_item.type is StageType.SINGLE_ELIMINATION:
        if changed_round_id is not None:
            await update_inputs_in_subsequent_elimination_rounds(
                tournament_id, changed_round_id, stage_item, changed_match_ids
            )
        else:
            await update_inputs_in_complete_elimination_stage_item(tournament_id, stage_item)

    await resolve_dependent_inputs_for_completed_stage_item(tournament_id, stage_item.id)
