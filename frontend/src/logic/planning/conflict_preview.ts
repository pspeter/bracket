/**
 * Conflict preview for the planning grid, built on the shared client conflict
 * engine (`computeConflictFlags`).
 *
 * Every placement affordance — an insertion line on a court, or a scheduled match
 * the current selection could swap with — is previewed by simulating the candidate
 * action with `applyPlanningActions`, recomputing the conflict flags for the
 * resulting schedule, and diffing them against the pre-action flags. An affordance
 * is highlighted when the action would introduce a conflict that was not already
 * present, so the highlight reflects every conflict type the engine detects
 * (team/slot double-booking, referee, winner-of and cross-stage precedence, short
 * break, round order) rather than just team overlap.
 */
import { ConflictFlags, ConflictStage, computeConflictFlags } from './conflicts';
import { ScheduleGridLayout, computeInsertionLines } from './layout';
import { applyPlanningActions } from './optimistic';
import { PlanningAction, SelectionState, selectionReducer } from './selection';

export interface ConflictPreview {
  insertionLines: Set<string>;
  swapTargets: Set<number>;
}

const CONFLICT_FLAG_KEYS = [
  'stage_item_input1_conflict',
  'stage_item_input2_conflict',
  'precedence_conflict',
  'feeder_precedence_conflict',
  'short_break_conflict',
  'referee_conflict',
  'round_order_conflict',
] as const satisfies readonly (keyof ConflictFlags)[];

export function insertionLineKey(courtId: number, index: number): string {
  return `${courtId}:${index}`;
}

function emptyPreview(): ConflictPreview {
  return { insertionLines: new Set(), swapTargets: new Set() };
}

function getSelectedMatchId(selection: SelectionState): number | null {
  switch (selection.kind) {
    case 'match-selected':
      return selection.match.matchId;
    case 'tray-match-selected':
      return selection.matchId;
    default:
      return null;
  }
}

/**
 * The actions a tap would trigger from the current selection. A tap that needs a
 * move confirmation stashes its action in the resulting `confirm-move` state
 * rather than emitting it, so the preview reaches in to recover the pending action.
 */
function transitionActions(transition: ReturnType<typeof selectionReducer>): PlanningAction[] {
  if (transition.actions.length > 0) return transition.actions;
  return transition.state.kind === 'confirm-move' ? [transition.state.action] : [];
}

/**
 * Whether applying `actions` to `stages` introduces a conflict flag the pre-action
 * `baseline` did not already carry. Conflicts are relational, so the whole schedule
 * is re-evaluated and every match compared — a move can push an unrelated match
 * into a conflict, not just the one being placed.
 */
function actionsIntroduceConflict(
  stages: ConflictStage[],
  baseline: Map<number, ConflictFlags>,
  defaultBreakMinutes: number,
  tournamentStartTime: string | Date,
  refereesEnabled: boolean,
  actions: PlanningAction[]
): boolean {
  if (actions.length === 0) return false;

  const simulated = applyPlanningActions(stages, actions, tournamentStartTime, defaultBreakMinutes);
  const postFlags = computeConflictFlags(simulated, defaultBreakMinutes, { refereesEnabled });

  for (const [matchId, flags] of postFlags) {
    const before = baseline.get(matchId);
    for (const key of CONFLICT_FLAG_KEYS) {
      if (flags[key] && before?.[key] !== true) {
        return true;
      }
    }
  }
  return false;
}

export function computeConflictPreview({
  stages,
  layout,
  selection,
  tournamentStartTime,
  refereesEnabled,
}: {
  stages: ConflictStage[];
  layout: ScheduleGridLayout;
  selection: SelectionState;
  tournamentStartTime: string | Date;
  refereesEnabled: boolean;
}): ConflictPreview {
  if (getSelectedMatchId(selection) == null) return emptyPreview();

  const defaultBreakMinutes = layout.defaultBreakMinutes;
  const baseline = computeConflictFlags(stages, defaultBreakMinutes, { refereesEnabled });
  const preview = emptyPreview();

  const introducesConflict = (actions: PlanningAction[]): boolean =>
    actionsIntroduceConflict(
      stages,
      baseline,
      defaultBreakMinutes,
      tournamentStartTime,
      refereesEnabled,
      actions
    );

  for (const { court, blocks } of layout.courts) {
    for (const line of computeInsertionLines(blocks)) {
      const transition = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: court.id,
        index: line.index,
      });
      if (introducesConflict(transitionActions(transition))) {
        preview.insertionLines.add(insertionLineKey(court.id, line.index));
      }
    }

    blocks.forEach((block, blockIndex) => {
      const transition = selectionReducer(selection, {
        type: 'tap-match',
        match: { matchId: block.match.id, courtId: court.id, position: blockIndex },
      });
      if (introducesConflict(transitionActions(transition))) {
        preview.swapTargets.add(block.match.id);
      }
    });
  }

  return preview;
}
