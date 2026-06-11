/**
 * Pure, headless state machine for the planning grid's tap-to-place interaction.
 *
 * The UI dispatches events (tap on a match card, tap on a tray match, tap on an
 * insertion line, unschedule, cancel) and the reducer returns the next selection
 * state plus the backend action the tap triggers (zero or one). Later slices
 * (zoom gating, action sheet) extend this same reducer.
 *
 * Positions are `position_in_schedule` values, which the backend keeps contiguous
 * (0..n-1) per court. An insertion line with index `k` on a court means "insert
 * before the match currently at position `k`"; `k === count` means "at the end".
 */

export interface GridMatchRef {
  matchId: number;
  courtId: number;
  position: number;
}

export type SelectionState =
  | { kind: 'idle' }
  | { kind: 'match-selected'; match: GridMatchRef }
  | { kind: 'tray-match-selected'; matchId: number };

export const IDLE_SELECTION: SelectionState = { kind: 'idle' };

export type SelectionEvent =
  | { type: 'tap-match'; match: GridMatchRef }
  | { type: 'tap-tray-match'; matchId: number }
  | { type: 'tap-insertion-line'; courtId: number; index: number }
  | { type: 'unschedule' }
  | { type: 'cancel' };

export type PlanningAction =
  | {
      type: 'reschedule';
      matchId: number;
      body: {
        old_court_id: number | null;
        old_position: number | null;
        new_court_id: number;
        new_position: number;
      };
    }
  | { type: 'swap'; matchId1: number; matchId2: number }
  | { type: 'unschedule'; matchId: number };

export interface SelectionTransition {
  state: SelectionState;
  actions: PlanningAction[];
}

function stay(state: SelectionState): SelectionTransition {
  return { state, actions: [] };
}

function place(selected: GridMatchRef, courtId: number, index: number): SelectionTransition {
  const sameCourt = courtId === selected.courtId;

  // The lines directly before and after the selected match put it back where it
  // already is; placing there is a no-op that just clears the selection.
  if (sameCourt && (index === selected.position || index === selected.position + 1)) {
    return stay(IDLE_SELECTION);
  }

  // When moving later on the same court, the match vacates its old slot first, so
  // everything after it shifts down by one. The backend then nudges the match after
  // the occupant of `new_position` (+0.5) instead of before it (-0.5).
  const newPosition = sameCourt && index > selected.position ? index - 1 : index;

  return {
    state: IDLE_SELECTION,
    actions: [
      {
        type: 'reschedule',
        matchId: selected.matchId,
        body: {
          old_court_id: selected.courtId,
          old_position: selected.position,
          new_court_id: courtId,
          new_position: newPosition,
        },
      },
    ],
  };
}

function placeFromTray(matchId: number, courtId: number, index: number): SelectionTransition {
  return {
    state: IDLE_SELECTION,
    actions: [
      {
        type: 'reschedule',
        matchId,
        body: {
          old_court_id: null,
          old_position: null,
          new_court_id: courtId,
          new_position: index,
        },
      },
    ],
  };
}

/**
 * Swap two scheduled matches as a single atomic backend operation. The backend
 * identifies both matches by id and trades their slots, so the action stays valid
 * even if the grid the user tapped on was slightly stale.
 */
function swap(selected: GridMatchRef, target: GridMatchRef): SelectionTransition {
  return {
    state: IDLE_SELECTION,
    actions: [{ type: 'swap', matchId1: selected.matchId, matchId2: target.matchId }],
  };
}

export function selectionReducer(
  state: SelectionState,
  event: SelectionEvent
): SelectionTransition {
  switch (state.kind) {
    case 'idle':
      switch (event.type) {
        case 'tap-match':
          return stay({ kind: 'match-selected', match: event.match });
        case 'tap-tray-match':
          return stay({ kind: 'tray-match-selected', matchId: event.matchId });
        default:
          return stay(state);
      }
    case 'match-selected':
      switch (event.type) {
        case 'cancel':
          return stay(IDLE_SELECTION);
        case 'tap-match':
          // Tapping the selected match again deselects; tapping another
          // scheduled match swaps the two.
          if (event.match.matchId === state.match.matchId) {
            return stay(IDLE_SELECTION);
          }
          return swap(state.match, event.match);
        case 'tap-tray-match':
          return stay({ kind: 'tray-match-selected', matchId: event.matchId });
        case 'tap-insertion-line':
          return place(state.match, event.courtId, event.index);
        case 'unschedule':
          return {
            state: IDLE_SELECTION,
            actions: [{ type: 'unschedule', matchId: state.match.matchId }],
          };
        default:
          return stay(state);
      }
    case 'tray-match-selected':
      switch (event.type) {
        case 'cancel':
          // The match was never scheduled; cancelling simply leaves it in the tray.
          return stay(IDLE_SELECTION);
        case 'tap-match':
          return stay({ kind: 'match-selected', match: event.match });
        case 'tap-tray-match':
          if (event.matchId === state.matchId) {
            return stay(IDLE_SELECTION);
          }
          return stay({ kind: 'tray-match-selected', matchId: event.matchId });
        case 'tap-insertion-line':
          return placeFromTray(state.matchId, event.courtId, event.index);
        default:
          return stay(state);
      }
    default:
      return stay(state);
  }
}
