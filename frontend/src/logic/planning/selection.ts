/**
 * Pure, headless state machine for the planning grid's tap-to-place interaction.
 *
 * The UI dispatches events (tap on a match card, tap on an insertion line, cancel)
 * and the reducer returns the next selection state plus, when a tap completes a
 * placement or swap, the request(s) to send to the backend. Tray selection and
 * unschedule extend this same reducer.
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

export interface RescheduleRequest {
  matchId: number;
  body: {
    old_court_id: number | null;
    old_position: number | null;
    new_court_id: number;
    new_position: number;
  };
}

export interface SwapRequest {
  first: RescheduleRequest;
  second: RescheduleRequest;
}

export interface SelectionTransition {
  state: SelectionState;
  reschedule: RescheduleRequest | null;
  swap: SwapRequest | null;
  unschedule: { matchId: number } | null;
}

function idle(overrides: Partial<Omit<SelectionTransition, 'state'>> = {}): SelectionTransition {
  return {
    state: IDLE_SELECTION,
    reschedule: null,
    swap: null,
    unschedule: null,
    ...overrides,
  };
}

function noOp(state: SelectionState): SelectionTransition {
  return { state, reschedule: null, swap: null, unschedule: null };
}

function place(selected: GridMatchRef, courtId: number, index: number): SelectionTransition {
  const sameCourt = courtId === selected.courtId;

  // The lines directly before and after the selected match put it back where it
  // already is; placing there is a no-op that just clears the selection.
  if (sameCourt && (index === selected.position || index === selected.position + 1)) {
    return idle();
  }

  // When moving later on the same court, the match vacates its old slot first, so
  // everything after it shifts down by one. The backend then nudges the match after
  // the occupant of `new_position` (+0.5) instead of before it (-0.5).
  const newPosition = sameCourt && index > selected.position ? index - 1 : index;

  return idle({
    reschedule: {
      matchId: selected.matchId,
      body: {
        old_court_id: selected.courtId,
        old_position: selected.position,
        new_court_id: courtId,
        new_position: newPosition,
      },
    },
  });
}

function placeTray(matchId: number, courtId: number, index: number): SelectionTransition {
  // Tray matches have no old court/position. The backend inserts at new_position-0.5,
  // placing before the match currently at index `new_position`.
  return idle({
    reschedule: {
      matchId,
      body: {
        old_court_id: null,
        old_position: null,
        new_court_id: courtId,
        new_position: index,
      },
    },
  });
}

function swap(matchA: GridMatchRef, matchB: GridMatchRef): SelectionTransition {
  // After step one (moving A to B's position), B shifts:
  //   - Different courts: B shifts up one (A is inserted before/at B).
  //   - Same court, A before B: B shifts down one (A's removal slides B closer).
  //   - Same court, A after B: B shifts up one (A is inserted before B).
  const bPositionAfterFirst =
    matchA.courtId !== matchB.courtId || matchA.position > matchB.position
      ? matchB.position + 1
      : matchB.position - 1;

  const first: RescheduleRequest = {
    matchId: matchA.matchId,
    body: {
      old_court_id: matchA.courtId,
      old_position: matchA.position,
      new_court_id: matchB.courtId,
      new_position: matchB.position,
    },
  };

  const second: RescheduleRequest = {
    matchId: matchB.matchId,
    body: {
      old_court_id: matchB.courtId,
      old_position: bPositionAfterFirst,
      new_court_id: matchA.courtId,
      new_position: matchA.position,
    },
  };

  return idle({ swap: { first, second } });
}

export function selectionReducer(
  state: SelectionState,
  event: SelectionEvent
): SelectionTransition {
  switch (state.kind) {
    case 'idle':
      if (event.type === 'tap-match') {
        return noOp({ kind: 'match-selected', match: event.match });
      }
      if (event.type === 'tap-tray-match') {
        return noOp({ kind: 'tray-match-selected', matchId: event.matchId });
      }
      return noOp(state);

    case 'match-selected':
      switch (event.type) {
        case 'cancel':
          return idle();
        case 'tap-match':
          if (event.match.matchId === state.match.matchId) {
            return idle();
          }
          return swap(state.match, event.match);
        case 'tap-tray-match':
          return noOp({ kind: 'tray-match-selected', matchId: event.matchId });
        case 'tap-insertion-line':
          return place(state.match, event.courtId, event.index);
        case 'unschedule':
          return idle({ unschedule: { matchId: state.match.matchId } });
        default:
          return noOp(state);
      }

    case 'tray-match-selected':
      switch (event.type) {
        case 'cancel':
          return idle();
        case 'tap-tray-match':
          if (event.matchId === state.matchId) {
            return idle();
          }
          return noOp({ kind: 'tray-match-selected', matchId: event.matchId });
        case 'tap-match':
          // Tapping a grid match during tray placement is a no-op: the user
          // is in placement mode and should tap an insertion line, not a card.
          return noOp(state);
        case 'tap-insertion-line':
          return placeTray(state.matchId, event.courtId, event.index);
        default:
          return noOp(state);
      }

    default:
      return noOp(state);
  }
}
