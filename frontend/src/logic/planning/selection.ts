/**
 * Pure, headless state machine for the planning grid's tap-to-place interaction.
 *
 * The UI dispatches events (tap on a match card, tap on a tray match, tap on an
 * insertion line, confirmation buttons, unschedule, cancel) and the reducer
 * returns the next selection state plus the backend action the tap triggers
 * (zero or one).
 *
 * Tapping an already-selected match deselects it. Moves that would disturb a
 * played match or swap into the frozen past enter `confirm-move`; confirming
 * emits the stashed backend action, while cancelling returns to the selection.
 *
 * Positions are transient start-time-order indices (0..n-1) per court. An
 * insertion line with index `k` on a court means "insert before the match
 * currently at index `k`"; `k === count` means "at the end".
 *
 * `plannerReducer` wraps the selection machine with the semantic zoom level:
 * placement and swapping are only active at agenda/compact zoom, while taps at
 * overview zoom navigate (zoom in toward the tapped court/time region). An
 * active selection survives zoom changes.
 */

import { MoveDestination, needsMoveConfirmation } from './move_confirmation';
import { ZoomLevel, zoomIn, zoomOut } from './zoom';

export interface GridMatchRef {
  matchId: number;
  courtId: number;
  position: number;
  /** The match has started or completed; moving it requires confirmation. */
  played?: boolean;
  /**
   * Soft-locked: part of a court's frozen past (completed/in-progress, or
   * scheduled above such a match — see `MatchBlock.locked`). Taps on locked
   * matches never select or swap; an explicit override arrives with the
   * action sheet.
   */
  locked?: boolean;
}

export type SelectionState =
  | { kind: 'idle' }
  | { kind: 'match-selected'; match: GridMatchRef }
  | { kind: 'tray-match-selected'; matchId: number }
  | { kind: 'confirm-move'; previous: ActiveSelectionState; action: PlanningAction };

export type ActiveSelectionState = Extract<
  SelectionState,
  { kind: 'match-selected' } | { kind: 'tray-match-selected' }
>;

export const IDLE_SELECTION: SelectionState = { kind: 'idle' };

export type SelectionEvent =
  | { type: 'tap-match'; match: GridMatchRef }
  | { type: 'tap-tray-match'; matchId: number }
  | { type: 'tap-insertion-line'; courtId: number; index: number }
  | { type: 'unschedule' }
  | { type: 'confirm' }
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
  | { type: 'unschedule'; matchId: number }
  | { type: 'resize-break'; matchId: number; newDurationMinutes: number };

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
 * Swap two matches as a single atomic backend operation. The backend identifies
 * both matches by id and trades their slots, so the action stays valid even if
 * the grid the user tapped on was slightly stale. The tray counts as "no slot":
 * swapping a scheduled match with a tray match puts the tray match in its slot
 * and sends the scheduled match back to the tray.
 */
function swap(selectedMatchId: number, targetMatchId: number): SelectionTransition {
  return {
    state: IDLE_SELECTION,
    actions: [{ type: 'swap', matchId1: selectedMatchId, matchId2: targetMatchId }],
  };
}

function confirmOrPerform(
  previous: ActiveSelectionState,
  moved: Pick<GridMatchRef, 'played' | 'locked'>,
  destination: MoveDestination,
  transition: SelectionTransition
): SelectionTransition {
  const [action] = transition.actions;
  if (action == null || !needsMoveConfirmation(moved, destination)) {
    return transition;
  }
  return { state: { kind: 'confirm-move', previous, action }, actions: [] };
}

export function selectionReducer(
  state: SelectionState,
  event: SelectionEvent,
  mode: PlannerMode = 'move'
): SelectionTransition {
  switch (state.kind) {
    case 'idle':
      switch (event.type) {
        case 'tap-match':
          if (mode === 'unschedule') {
            if (event.match.locked || event.match.played) return stay(IDLE_SELECTION);
            return {
              state: IDLE_SELECTION,
              actions: [{ type: 'unschedule', matchId: event.match.matchId }],
            };
          }
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
          // Tapping the selected match again deselects it; tapping another match
          // — scheduled or in the tray — swaps the two.
          if (event.match.matchId === state.match.matchId) {
            return stay(IDLE_SELECTION);
          }
          return confirmOrPerform(
            state,
            state.match,
            { kind: 'swap', match: event.match },
            swap(state.match.matchId, event.match.matchId)
          );
        case 'tap-tray-match':
          return swap(state.match.matchId, event.matchId);
        case 'tap-insertion-line':
          return confirmOrPerform(
            state,
            state.match,
            { kind: 'free-slot' },
            place(state.match, event.courtId, event.index)
          );
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
          return confirmOrPerform(
            state,
            {},
            { kind: 'swap', match: event.match },
            swap(state.matchId, event.match.matchId)
          );
        case 'tap-tray-match':
          // Swapping two tray matches is meaningless, so taps inside the tray
          // keep switching the selection instead.
          if (event.matchId === state.matchId) {
            return stay(IDLE_SELECTION);
          }
          return stay({ kind: 'tray-match-selected', matchId: event.matchId });
        case 'tap-insertion-line':
          return placeFromTray(state.matchId, event.courtId, event.index);
        default:
          return stay(state);
      }
    case 'confirm-move':
      switch (event.type) {
        case 'confirm':
          return { state: IDLE_SELECTION, actions: [state.action] };
        case 'cancel':
          return stay(state.previous);
        default:
          // The popup is modal; grid taps slipping through must not change anything.
          return stay(state);
      }
    default:
      return stay(state);
  }
}

export interface PlannerState {
  zoom: ZoomLevel;
  mode: PlannerMode;
  selection: SelectionState;
}

export type PlannerMode = 'move' | 'unschedule' | 'edit';

export function initialPlannerState(zoom: ZoomLevel): PlannerState {
  return { zoom, mode: 'move', selection: IDLE_SELECTION };
}

export type PlannerEvent =
  | SelectionEvent
  | { type: 'set-mode'; mode: PlannerMode }
  | { type: 'zoom-in'; anchor?: FocusTarget | null }
  | { type: 'zoom-out'; anchor?: FocusTarget | null }
  | { type: 'set-zoom'; zoom: ZoomLevel }
  | { type: 'tap-overview'; courtId: number; fraction: number }
  | { type: 'resize-break'; matchId: number; newDurationMinutes: number };

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
  actions: PlanningAction[];
  focus: FocusTarget | null;
}

function noEffect(state: PlannerState): PlannerTransition {
  return { state, actions: [], focus: null };
}

function zoomTo(
  state: PlannerState,
  zoom: ZoomLevel,
  anchor?: FocusTarget | null
): PlannerTransition {
  // Already clamped at this level: nothing changes, so nothing to focus.
  if (zoom === state.zoom) return noEffect(state);
  return { state: { ...state, zoom }, actions: [], focus: anchor ?? null };
}

function delegate(state: PlannerState, event: SelectionEvent): PlannerTransition {
  const { state: selection, actions } = selectionReducer(state.selection, event, state.mode);
  return { state: { ...state, selection }, actions, focus: null };
}

export function plannerReducer(state: PlannerState, event: PlannerEvent): PlannerTransition {
  switch (event.type) {
    case 'set-mode':
      return {
        state: { ...state, mode: event.mode, selection: IDLE_SELECTION },
        actions: [],
        focus: null,
      };
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
    case 'resize-break':
      // Editing a derived break is an explicit popup action on a specific match;
      // it never touches the selection. Break elements only render at the card
      // zoom levels, so a stale dispatch at overview is ignored.
      if (state.zoom === 'overview') return noEffect(state);
      return {
        state,
        actions: [
          {
            type: 'resize-break',
            matchId: event.matchId,
            newDurationMinutes: event.newDurationMinutes,
          },
        ],
        focus: null,
      };
    case 'cancel':
    case 'unschedule':
    case 'confirm':
      // Explicit buttons, not grid geometry: usable at any zoom level.
      return delegate(state, event);
    case 'tap-tray-match':
      // Tray rows are finger-sized at every zoom, so selecting from the tray
      // at overview is fine (orient first, then zoom in to place). But with a
      // selection active the tap would swap, and swap targets are gated to
      // agenda/compact like all other placement.
      if (state.zoom === 'overview' && state.selection.kind !== 'idle') {
        return noEffect(state);
      }
      return delegate(state, event);
    default: {
      // Targets at overview zoom are a few pixels wide; even if a stale UI
      // still dispatches a card or line tap there, it must never select,
      // swap or place anything.
      if (state.zoom === 'overview') return noEffect(state);
      return delegate(state, event);
    }
  }
}
