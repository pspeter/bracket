/**
 * Pure, headless state machine for the planning grid's tap-to-place interaction.
 *
 * The UI dispatches events (tap on a match card, tap on an insertion line, cancel)
 * and the reducer returns the next selection state plus, when a tap completes a
 * placement, the reschedule request to send to the backend. Later slices (swap,
 * tray placement, zoom gating, action sheet) extend this same reducer.
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

export type SelectionState = { kind: 'idle' } | { kind: 'match-selected'; match: GridMatchRef };

export const IDLE_SELECTION: SelectionState = { kind: 'idle' };

export type SelectionEvent =
  | { type: 'tap-match'; match: GridMatchRef }
  | { type: 'tap-insertion-line'; courtId: number; index: number }
  | { type: 'cancel' };

export interface RescheduleRequest {
  matchId: number;
  body: {
    old_court_id: number;
    old_position: number;
    new_court_id: number;
    new_position: number;
  };
}

export interface SelectionTransition {
  state: SelectionState;
  reschedule: RescheduleRequest | null;
}

function place(selected: GridMatchRef, courtId: number, index: number): SelectionTransition {
  const sameCourt = courtId === selected.courtId;

  // The lines directly before and after the selected match put it back where it
  // already is; placing there is a no-op that just clears the selection.
  if (sameCourt && (index === selected.position || index === selected.position + 1)) {
    return { state: IDLE_SELECTION, reschedule: null };
  }

  // When moving later on the same court, the match vacates its old slot first, so
  // everything after it shifts down by one. The backend then nudges the match after
  // the occupant of `new_position` (+0.5) instead of before it (-0.5).
  const newPosition = sameCourt && index > selected.position ? index - 1 : index;

  return {
    state: IDLE_SELECTION,
    reschedule: {
      matchId: selected.matchId,
      body: {
        old_court_id: selected.courtId,
        old_position: selected.position,
        new_court_id: courtId,
        new_position: newPosition,
      },
    },
  };
}

export function selectionReducer(
  state: SelectionState,
  event: SelectionEvent
): SelectionTransition {
  switch (state.kind) {
    case 'idle':
      if (event.type === 'tap-match') {
        return { state: { kind: 'match-selected', match: event.match }, reschedule: null };
      }
      return { state, reschedule: null };
    case 'match-selected':
      switch (event.type) {
        case 'cancel':
          return { state: IDLE_SELECTION, reschedule: null };
        case 'tap-match':
          // Tapping the selected match again deselects; tapping another match
          // moves the selection there (swap arrives in a later slice).
          if (event.match.matchId === state.match.matchId) {
            return { state: IDLE_SELECTION, reschedule: null };
          }
          return { state: { kind: 'match-selected', match: event.match }, reschedule: null };
        case 'tap-insertion-line':
          return place(state.match, event.courtId, event.index);
        default:
          return { state, reschedule: null };
      }
    default:
      return { state, reschedule: null };
  }
}
