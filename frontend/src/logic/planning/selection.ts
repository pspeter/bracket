/**
 * Pure, headless state machine for the planning grid's tap-to-place interaction.
 *
 * The UI dispatches events (tap on a match card, tap on an insertion line, cancel)
 * and the reducer returns the next selection state plus, when a tap completes a
 * placement, the reschedule request to send to the backend. Later slices (swap,
 * tray placement, action sheet) extend this same reducer.
 *
 * Positions are `position_in_schedule` values, which the backend keeps contiguous
 * (0..n-1) per court. An insertion line with index `k` on a court means "insert
 * before the match currently at position `k`"; `k === count` means "at the end".
 *
 * `plannerReducer` wraps the selection machine with the semantic zoom level:
 * selection and placement are only active at agenda/compact zoom, while taps at
 * overview zoom navigate (zoom in toward the tapped court/time region). An
 * active selection survives zoom changes.
 */

import { ZoomLevel, zoomIn, zoomOut } from './zoom';

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

export interface PlannerState {
  zoom: ZoomLevel;
  selection: SelectionState;
}

export function initialPlannerState(zoom: ZoomLevel): PlannerState {
  return { zoom, selection: IDLE_SELECTION };
}

export type PlannerEvent =
  | SelectionEvent
  | { type: 'zoom-in'; anchor?: FocusTarget | null }
  | { type: 'zoom-out'; anchor?: FocusTarget | null }
  | { type: 'set-zoom'; zoom: ZoomLevel }
  | { type: 'tap-overview'; courtId: number; fraction: number };

/**
 * Where to scroll the grid after a zoom change: a court plus a vertical
 * position expressed as a fraction (0..1) of the schedule's total length, so
 * it stays meaningful across the zoom levels' different scales.
 */
export interface FocusTarget {
  courtId: number;
  fraction: number;
}

export interface PlannerTransition {
  state: PlannerState;
  reschedule: RescheduleRequest | null;
  focus: FocusTarget | null;
}

function noEffect(state: PlannerState): PlannerTransition {
  return { state, reschedule: null, focus: null };
}

function zoomTo(
  state: PlannerState,
  zoom: ZoomLevel,
  anchor?: FocusTarget | null
): PlannerTransition {
  // Already clamped at this level: nothing changes, so nothing to focus.
  if (zoom === state.zoom) return noEffect(state);
  return { state: { ...state, zoom }, reschedule: null, focus: anchor ?? null };
}

export function plannerReducer(state: PlannerState, event: PlannerEvent): PlannerTransition {
  switch (event.type) {
    case 'zoom-in':
      return zoomTo(state, zoomIn(state.zoom), event.anchor);
    case 'zoom-out':
      return zoomTo(state, zoomOut(state.zoom), event.anchor);
    case 'set-zoom':
      return zoomTo(state, event.zoom);
    case 'tap-overview':
      // Overview taps navigate toward the tapped region; they never select or
      // place, and a selection in progress rides along to the next level.
      if (state.zoom !== 'overview') return noEffect(state);
      return zoomTo(state, zoomIn(state.zoom), {
        courtId: event.courtId,
        fraction: event.fraction,
      });
    case 'cancel': {
      const { state: selection } = selectionReducer(state.selection, event);
      return noEffect({ ...state, selection });
    }
    default: {
      // Targets at overview zoom are a few pixels wide; even if a stale UI
      // still dispatches a card or line tap there, it must never select or
      // place anything.
      if (state.zoom === 'overview') return noEffect(state);
      const { state: selection, reschedule } = selectionReducer(state.selection, event);
      return { state: { ...state, selection }, reschedule, focus: null };
    }
  }
}
