import { describe, expect, it } from 'vitest';

import {
  GridMatchRef,
  IDLE_SELECTION,
  PlannerState,
  SelectionState,
  initialPlannerState,
  plannerReducer,
  selectionReducer,
} from './selection';
import { ZoomLevel } from './zoom';

function ref(matchId: number, courtId: number, position: number): GridMatchRef {
  return { matchId, courtId, position };
}

function selected(match: GridMatchRef): SelectionState {
  return { kind: 'match-selected', match };
}

function planner(zoom: ZoomLevel, selection: SelectionState = IDLE_SELECTION): PlannerState {
  return { zoom, selection };
}

describe('selectionReducer', () => {
  describe('in idle state', () => {
    it('selects a match on tap without rescheduling', () => {
      const { state, reschedule } = selectionReducer(IDLE_SELECTION, {
        type: 'tap-match',
        match: ref(10, 1, 0),
      });

      expect(state).toEqual(selected(ref(10, 1, 0)));
      expect(reschedule).toBeNull();
    });

    it('ignores insertion line taps', () => {
      const { state, reschedule } = selectionReducer(IDLE_SELECTION, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 0,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toBeNull();
    });

    it('ignores cancel', () => {
      const { state, reschedule } = selectionReducer(IDLE_SELECTION, { type: 'cancel' });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toBeNull();
    });
  });

  describe('with a match selected', () => {
    // Court 1 has matches at positions 0..3; the selected match sits at position 2.
    const selection = selected(ref(10, 1, 2));

    it('cancel returns to idle without rescheduling', () => {
      const { state, reschedule } = selectionReducer(selection, { type: 'cancel' });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toBeNull();
    });

    it('tapping the selected match again deselects it', () => {
      const { state, reschedule } = selectionReducer(selection, {
        type: 'tap-match',
        match: ref(10, 1, 2),
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toBeNull();
    });

    it('tapping a different match selects that match instead', () => {
      const { state, reschedule } = selectionReducer(selection, {
        type: 'tap-match',
        match: ref(20, 2, 0),
      });

      expect(state).toEqual(selected(ref(20, 2, 0)));
      expect(reschedule).toBeNull();
    });

    it('placing on another court inserts before the match at that index', () => {
      const { state, reschedule } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 1,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toEqual({
        matchId: 10,
        body: { old_court_id: 1, old_position: 2, new_court_id: 2, new_position: 1 },
      });
    });

    it('placing at the start of another court uses position 0', () => {
      const { reschedule } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 0,
      });

      expect(reschedule).toEqual({
        matchId: 10,
        body: { old_court_id: 1, old_position: 2, new_court_id: 2, new_position: 0 },
      });
    });

    it('placing earlier on the same court keeps the insertion index as the position', () => {
      const { state, reschedule } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 0,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toEqual({
        matchId: 10,
        body: { old_court_id: 1, old_position: 2, new_court_id: 1, new_position: 0 },
      });
    });

    it('placing later on the same court accounts for the match leaving its slot', () => {
      // Insertion line 4 means "after the match currently at position 3"; once the
      // selected match vacates position 2, that target becomes position 3.
      const { reschedule } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 4,
      });

      expect(reschedule).toEqual({
        matchId: 10,
        body: { old_court_id: 1, old_position: 2, new_court_id: 1, new_position: 3 },
      });
    });

    it('placing directly before itself is a no-op that clears the selection', () => {
      const { state, reschedule } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 2,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toBeNull();
    });

    it('placing directly after itself is a no-op that clears the selection', () => {
      const { state, reschedule } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 3,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toBeNull();
    });
  });
});

describe('plannerReducer', () => {
  it('starts idle at the requested zoom level', () => {
    expect(initialPlannerState('compact')).toEqual(planner('compact'));
  });

  describe('zoom events', () => {
    it('zoom-in and zoom-out snap between the three levels and clamp at the ends', () => {
      expect(plannerReducer(planner('overview'), { type: 'zoom-in' }).state.zoom).toBe('compact');
      expect(plannerReducer(planner('compact'), { type: 'zoom-in' }).state.zoom).toBe('agenda');
      expect(plannerReducer(planner('agenda'), { type: 'zoom-in' }).state.zoom).toBe('agenda');
      expect(plannerReducer(planner('agenda'), { type: 'zoom-out' }).state.zoom).toBe('compact');
      expect(plannerReducer(planner('overview'), { type: 'zoom-out' }).state.zoom).toBe('overview');
    });

    it('set-zoom jumps straight to a level', () => {
      const { state } = plannerReducer(planner('agenda'), { type: 'set-zoom', zoom: 'overview' });
      expect(state.zoom).toBe('overview');
    });

    it('never reschedules or focuses', () => {
      const transition = plannerReducer(planner('compact', selected(ref(10, 1, 2))), {
        type: 'zoom-out',
      });
      expect(transition.reschedule).toBeNull();
      expect(transition.focus).toBeNull();
    });

    it('an active selection survives zoom changes in both directions', () => {
      const start = planner('compact', selected(ref(10, 1, 2)));

      const zoomedOut = plannerReducer(start, { type: 'zoom-out' }).state;
      expect(zoomedOut).toEqual(planner('overview', selected(ref(10, 1, 2))));

      const zoomedBackIn = plannerReducer(zoomedOut, { type: 'zoom-in' }).state;
      expect(zoomedBackIn).toEqual(planner('compact', selected(ref(10, 1, 2))));
    });
  });

  describe('at agenda and compact zoom', () => {
    it.each(['agenda', 'compact'] as ZoomLevel[])('selects a tapped match at %s', (zoom) => {
      const { state, reschedule } = plannerReducer(planner(zoom), {
        type: 'tap-match',
        match: ref(10, 1, 0),
      });

      expect(state).toEqual(planner(zoom, selected(ref(10, 1, 0))));
      expect(reschedule).toBeNull();
    });

    it.each(['agenda', 'compact'] as ZoomLevel[])(
      'places the selected match on an insertion line at %s',
      (zoom) => {
        const { state, reschedule } = plannerReducer(planner(zoom, selected(ref(10, 1, 2))), {
          type: 'tap-insertion-line',
          courtId: 2,
          index: 1,
        });

        expect(state).toEqual(planner(zoom));
        expect(reschedule).toEqual({
          matchId: 10,
          body: { old_court_id: 1, old_position: 2, new_court_id: 2, new_position: 1 },
        });
      }
    );

    it('ignores overview taps', () => {
      const start = planner('compact', selected(ref(10, 1, 2)));
      const transition = plannerReducer(start, {
        type: 'tap-overview',
        courtId: 2,
        offsetMinutes: 90,
      });

      expect(transition.state).toEqual(start);
      expect(transition.reschedule).toBeNull();
      expect(transition.focus).toBeNull();
    });
  });

  describe('at overview zoom', () => {
    it('a tap on a match never selects or places', () => {
      const start = planner('overview');
      const transition = plannerReducer(start, { type: 'tap-match', match: ref(10, 1, 0) });

      expect(transition.state).toEqual(start);
      expect(transition.reschedule).toBeNull();
    });

    it('a tap on an insertion line never places, even with an active selection', () => {
      const start = planner('overview', selected(ref(10, 1, 2)));
      const transition = plannerReducer(start, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 1,
      });

      expect(transition.state).toEqual(start);
      expect(transition.reschedule).toBeNull();
    });

    it('a tap on the grid zooms in toward the tapped court/time region', () => {
      const { state, reschedule, focus } = plannerReducer(planner('overview'), {
        type: 'tap-overview',
        courtId: 3,
        offsetMinutes: 120,
      });

      expect(state.zoom).toBe('compact');
      expect(focus).toEqual({ courtId: 3, offsetMinutes: 120 });
      expect(reschedule).toBeNull();
    });

    it('zooming in via a tap keeps the active selection for placement at compact', () => {
      const start = planner('overview', selected(ref(10, 1, 2)));

      const navigated = plannerReducer(start, {
        type: 'tap-overview',
        courtId: 2,
        offsetMinutes: 60,
      });
      expect(navigated.state).toEqual(planner('compact', selected(ref(10, 1, 2))));

      const placed = plannerReducer(navigated.state, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 0,
      });
      expect(placed.reschedule).toEqual({
        matchId: 10,
        body: { old_court_id: 1, old_position: 2, new_court_id: 2, new_position: 0 },
      });
    });

    it('cancel still clears the selection', () => {
      const { state } = plannerReducer(planner('overview', selected(ref(10, 1, 2))), {
        type: 'cancel',
      });
      expect(state).toEqual(planner('overview'));
    });
  });
});
