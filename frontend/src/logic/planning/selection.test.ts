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

function lockedRef(matchId: number, courtId: number, position: number): GridMatchRef {
  return { matchId, courtId, position, locked: true };
}

function selected(match: GridMatchRef): SelectionState {
  return { kind: 'match-selected', match };
}

function traySelected(matchId: number): SelectionState {
  return { kind: 'tray-match-selected', matchId };
}

function sheetOpen(match: GridMatchRef): SelectionState {
  return { kind: 'action-sheet-open', match };
}

function planner(zoom: ZoomLevel, selection: SelectionState = IDLE_SELECTION): PlannerState {
  return { zoom, selection };
}

describe('selectionReducer', () => {
  describe('in idle state', () => {
    it('selects a match on tap without any actions', () => {
      const { state, actions } = selectionReducer(IDLE_SELECTION, {
        type: 'tap-match',
        match: ref(10, 1, 0),
      });

      expect(state).toEqual(selected(ref(10, 1, 0)));
      expect(actions).toEqual([]);
    });

    it('selects a tray match on tap without any actions', () => {
      const { state, actions } = selectionReducer(IDLE_SELECTION, {
        type: 'tap-tray-match',
        matchId: 30,
      });

      expect(state).toEqual(traySelected(30));
      expect(actions).toEqual([]);
    });

    it('ignores insertion line taps', () => {
      const { state, actions } = selectionReducer(IDLE_SELECTION, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 0,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });

    it('ignores unschedule', () => {
      const { state, actions } = selectionReducer(IDLE_SELECTION, { type: 'unschedule' });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });

    it('ignores cancel', () => {
      const { state, actions } = selectionReducer(IDLE_SELECTION, { type: 'cancel' });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });
  });

  describe('with a scheduled match selected', () => {
    // Court 1 has matches at positions 0..3; the selected match sits at position 2.
    const selection = selected(ref(10, 1, 2));

    it('cancel returns to idle without any actions', () => {
      const { state, actions } = selectionReducer(selection, { type: 'cancel' });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });

    it('tapping the selected match again opens the action sheet', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-match',
        match: ref(10, 1, 2),
      });

      expect(state).toEqual(sheetOpen(ref(10, 1, 2)));
      expect(actions).toEqual([]);
    });

    it('placing on another court inserts before the match at that index', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 1,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([
        {
          type: 'reschedule',
          matchId: 10,
          body: { old_court_id: 1, old_position: 2, new_court_id: 2, new_position: 1 },
        },
      ]);
    });

    it('placing at the start of another court uses position 0', () => {
      const { actions } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 0,
      });

      expect(actions).toEqual([
        {
          type: 'reschedule',
          matchId: 10,
          body: { old_court_id: 1, old_position: 2, new_court_id: 2, new_position: 0 },
        },
      ]);
    });

    it('placing earlier on the same court keeps the insertion index as the position', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 0,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([
        {
          type: 'reschedule',
          matchId: 10,
          body: { old_court_id: 1, old_position: 2, new_court_id: 1, new_position: 0 },
        },
      ]);
    });

    it('placing later on the same court accounts for the match leaving its slot', () => {
      // Insertion line 4 means "after the match currently at position 3"; once the
      // selected match vacates position 2, that target becomes position 3.
      const { actions } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 4,
      });

      expect(actions).toEqual([
        {
          type: 'reschedule',
          matchId: 10,
          body: { old_court_id: 1, old_position: 2, new_court_id: 1, new_position: 3 },
        },
      ]);
    });

    it('placing directly before itself is a no-op that clears the selection', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 2,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });

    it('placing directly after itself is a no-op that clears the selection', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 1,
        index: 3,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });

    it('unschedule sends the selected match back to the tray and clears the selection', () => {
      const { state, actions } = selectionReducer(selection, { type: 'unschedule' });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([{ type: 'unschedule', matchId: 10 }]);
    });

    it('tapping a tray match swaps it into the selected slot', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-tray-match',
        matchId: 30,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([{ type: 'swap', matchId1: 10, matchId2: 30 }]);
    });
  });

  describe('swapping two scheduled matches', () => {
    it('tapping a match on another court emits a single id-based swap action', () => {
      const { state, actions } = selectionReducer(selected(ref(10, 1, 2)), {
        type: 'tap-match',
        match: ref(20, 2, 1),
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([{ type: 'swap', matchId1: 10, matchId2: 20 }]);
    });

    it('swaps with a match on the same court regardless of relative position', () => {
      const { actions } = selectionReducer(selected(ref(10, 1, 3)), {
        type: 'tap-match',
        match: ref(20, 1, 1),
      });

      expect(actions).toEqual([{ type: 'swap', matchId1: 10, matchId2: 20 }]);
    });
  });

  describe('with a tray match selected', () => {
    const selection = traySelected(30);

    it('cancel returns to idle without any actions, leaving the match unscheduled', () => {
      const { state, actions } = selectionReducer(selection, { type: 'cancel' });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });

    it('tapping the selected tray match again deselects it', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-tray-match',
        matchId: 30,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });

    it('tapping a different tray match selects that match instead', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-tray-match',
        matchId: 31,
      });

      expect(state).toEqual(traySelected(31));
      expect(actions).toEqual([]);
    });

    it('tapping a scheduled match swaps the tray match into its slot', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-match',
        match: ref(10, 1, 2),
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([{ type: 'swap', matchId1: 30, matchId2: 10 }]);
    });

    it('placing on an insertion line schedules the tray match there', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 1,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([
        {
          type: 'reschedule',
          matchId: 30,
          body: { old_court_id: null, old_position: null, new_court_id: 2, new_position: 1 },
        },
      ]);
    });

    it('ignores unschedule, since the match is already unscheduled', () => {
      const { state, actions } = selectionReducer(selection, { type: 'unschedule' });

      expect(state).toEqual(selection);
      expect(actions).toEqual([]);
    });
  });

  describe('soft-locked (completed/in-progress) matches', () => {
    it('tapping a locked match from idle opens the action sheet instead of selecting', () => {
      // The sheet is the discoverable home of the "move anyway" override, so it
      // must be reachable for played matches even though selection is soft-locked.
      const { state, actions } = selectionReducer(IDLE_SELECTION, {
        type: 'tap-match',
        match: lockedRef(10, 1, 0),
      });

      expect(state).toEqual(sheetOpen(lockedRef(10, 1, 0)));
      expect(actions).toEqual([]);
    });

    it('tapping a locked match with a scheduled match selected does not swap', () => {
      const selection = selected(ref(10, 1, 2));
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-match',
        match: lockedRef(20, 2, 0),
      });

      expect(state).toEqual(selection);
      expect(actions).toEqual([]);
    });

    it('tapping a locked match with a tray match selected does not swap', () => {
      const selection = traySelected(30);
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-match',
        match: lockedRef(10, 1, 0),
      });

      expect(state).toEqual(selection);
      expect(actions).toEqual([]);
    });
  });

  describe('with the action sheet open', () => {
    const selection = sheetOpen(ref(10, 1, 2));

    it('dismissing the sheet returns to the selected state', () => {
      const { state, actions } = selectionReducer(selection, { type: 'dismiss-action-sheet' });

      expect(state).toEqual(selected(ref(10, 1, 2)));
      expect(actions).toEqual([]);
    });

    it('dismissing the sheet of a locked match returns to idle, since it was never selectable', () => {
      const { state, actions } = selectionReducer(sheetOpen(lockedRef(10, 1, 0)), {
        type: 'dismiss-action-sheet',
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });

    it('cancel clears the whole selection', () => {
      const { state, actions } = selectionReducer(selection, { type: 'cancel' });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([]);
    });

    it('unschedule sends the match to the tray and clears the selection', () => {
      const { state, actions } = selectionReducer(selection, { type: 'unschedule' });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([{ type: 'unschedule', matchId: 10 }]);
    });

    it('grid taps are ignored while the sheet is open', () => {
      const events = [
        { type: 'tap-match', match: ref(20, 2, 1) },
        { type: 'tap-tray-match', matchId: 30 },
        { type: 'tap-insertion-line', courtId: 2, index: 1 },
      ] as const;

      for (const event of events) {
        const { state, actions } = selectionReducer(selection, event);
        expect(state).toEqual(selection);
        expect(actions).toEqual([]);
      }
    });

    it('move-anyway is a no-op for a match that was never locked', () => {
      const { state, actions } = selectionReducer(selection, { type: 'move-anyway' });

      expect(state).toEqual(selected({ ...ref(10, 1, 2), locked: false }));
      expect(actions).toEqual([]);
    });
  });

  describe('the move-anyway override', () => {
    const lockedSheet = sheetOpen(lockedRef(10, 1, 0));

    it('selects the locked match for placement with the lock lifted', () => {
      const { state, actions } = selectionReducer(lockedSheet, { type: 'move-anyway' });

      expect(state).toEqual(selected({ ...lockedRef(10, 1, 0), locked: false }));
      expect(actions).toEqual([]);
    });

    it('an overridden match can then be placed on an insertion line', () => {
      const { state: overridden } = selectionReducer(lockedSheet, { type: 'move-anyway' });
      const { state, actions } = selectionReducer(overridden, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 3,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([
        {
          type: 'reschedule',
          matchId: 10,
          body: { old_court_id: 1, old_position: 0, new_court_id: 2, new_position: 3 },
        },
      ]);
    });

    it('an overridden match can swap with an unlocked match', () => {
      const { state: overridden } = selectionReducer(lockedSheet, { type: 'move-anyway' });
      const { state, actions } = selectionReducer(overridden, {
        type: 'tap-match',
        match: ref(20, 2, 1),
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(actions).toEqual([{ type: 'swap', matchId1: 10, matchId2: 20 }]);
    });

    it('the override is one-shot: cancelling drops it, and re-tapping reopens the sheet', () => {
      const { state: overridden } = selectionReducer(lockedSheet, { type: 'move-anyway' });
      const { state: cancelled } = selectionReducer(overridden, { type: 'cancel' });
      expect(cancelled).toEqual(IDLE_SELECTION);

      const { state } = selectionReducer(cancelled, {
        type: 'tap-match',
        match: lockedRef(10, 1, 0),
      });
      expect(state).toEqual(sheetOpen(lockedRef(10, 1, 0)));
    });
  });

  describe('events that only apply to the action sheet', () => {
    it.each([
      ['idle', IDLE_SELECTION],
      ['match-selected', selected(ref(10, 1, 2))],
      ['tray-match-selected', traySelected(30)],
    ] as const)('dismiss-action-sheet and move-anyway are ignored at %s', (_kind, selection) => {
      for (const type of ['dismiss-action-sheet', 'move-anyway'] as const) {
        const { state, actions } = selectionReducer(selection, { type });
        expect(state).toEqual(selection);
        expect(actions).toEqual([]);
      }
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

    it('never triggers actions or focuses without an anchor', () => {
      const transition = plannerReducer(planner('compact', selected(ref(10, 1, 2))), {
        type: 'zoom-out',
      });
      expect(transition.actions).toEqual([]);
      expect(transition.focus).toBeNull();
    });

    it('keeps the anchored region in focus when zooming with an anchor', () => {
      const anchor = { courtId: 6, fraction: 0.8 };

      const zoomedIn = plannerReducer(planner('overview'), { type: 'zoom-in', anchor });
      expect(zoomedIn.state.zoom).toBe('compact');
      expect(zoomedIn.focus).toEqual(anchor);

      const zoomedOut = plannerReducer(planner('compact'), { type: 'zoom-out', anchor });
      expect(zoomedOut.state.zoom).toBe('overview');
      expect(zoomedOut.focus).toEqual(anchor);
    });

    it('does not focus when the zoom level is already at its end', () => {
      const anchor = { courtId: 6, fraction: 0.8 };
      const transition = plannerReducer(planner('agenda'), { type: 'zoom-in', anchor });

      expect(transition.state.zoom).toBe('agenda');
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
      const { state, actions } = plannerReducer(planner(zoom), {
        type: 'tap-match',
        match: ref(10, 1, 0),
      });

      expect(state).toEqual(planner(zoom, selected(ref(10, 1, 0))));
      expect(actions).toEqual([]);
    });

    it.each(['agenda', 'compact'] as ZoomLevel[])(
      'places the selected match on an insertion line at %s',
      (zoom) => {
        const { state, actions } = plannerReducer(planner(zoom, selected(ref(10, 1, 2))), {
          type: 'tap-insertion-line',
          courtId: 2,
          index: 1,
        });

        expect(state).toEqual(planner(zoom));
        expect(actions).toEqual([
          {
            type: 'reschedule',
            matchId: 10,
            body: { old_court_id: 1, old_position: 2, new_court_id: 2, new_position: 1 },
          },
        ]);
      }
    );

    it('opens the action sheet instead of selecting a locked (played) match', () => {
      const { state, actions } = plannerReducer(planner('compact'), {
        type: 'tap-match',
        match: lockedRef(10, 1, 0),
      });

      expect(state).toEqual(planner('compact', sheetOpen(lockedRef(10, 1, 0))));
      expect(actions).toEqual([]);
    });

    it('opens the action sheet on a second tap of the selected match', () => {
      const { state, actions } = plannerReducer(planner('agenda', selected(ref(10, 1, 2))), {
        type: 'tap-match',
        match: ref(10, 1, 2),
      });

      expect(state).toEqual(planner('agenda', sheetOpen(ref(10, 1, 2))));
      expect(actions).toEqual([]);
    });

    it('swaps two matches on a card tap', () => {
      const { state, actions } = plannerReducer(planner('compact', selected(ref(10, 1, 2))), {
        type: 'tap-match',
        match: ref(20, 2, 1),
      });

      expect(state).toEqual(planner('compact'));
      expect(actions).toEqual([{ type: 'swap', matchId1: 10, matchId2: 20 }]);
    });

    it('ignores overview taps', () => {
      const start = planner('compact', selected(ref(10, 1, 2)));
      const transition = plannerReducer(start, {
        type: 'tap-overview',
        courtId: 2,
        fraction: 0.5,
      });

      expect(transition.state).toEqual(start);
      expect(transition.actions).toEqual([]);
      expect(transition.focus).toBeNull();
    });

    it.each(['agenda', 'compact'] as ZoomLevel[])(
      'emits a resize-break action without touching the selection at %s',
      (zoom) => {
        const start = planner(zoom, selected(ref(10, 1, 2)));
        const { state, actions } = plannerReducer(start, {
          type: 'resize-break',
          matchId: 20,
          newDurationMinutes: 15,
        });

        expect(state).toEqual(start);
        expect(actions).toEqual([{ type: 'resize-break', matchId: 20, newDurationMinutes: 15 }]);
      }
    );
  });

  describe('at overview zoom', () => {
    it('a tap on a match never selects, swaps or places', () => {
      const idleTap = plannerReducer(planner('overview'), {
        type: 'tap-match',
        match: ref(10, 1, 0),
      });
      expect(idleTap.state).toEqual(planner('overview'));
      expect(idleTap.actions).toEqual([]);

      const selectedTap = plannerReducer(planner('overview', selected(ref(10, 1, 2))), {
        type: 'tap-match',
        match: ref(20, 2, 1),
      });
      expect(selectedTap.state).toEqual(planner('overview', selected(ref(10, 1, 2))));
      expect(selectedTap.actions).toEqual([]);
    });

    it('a tap on an insertion line never places, even with an active selection', () => {
      const start = planner('overview', selected(ref(10, 1, 2)));
      const transition = plannerReducer(start, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 1,
      });

      expect(transition.state).toEqual(start);
      expect(transition.actions).toEqual([]);
    });

    it('ignores a resize-break dispatched at overview zoom', () => {
      const start = planner('overview', selected(ref(10, 1, 2)));
      const transition = plannerReducer(start, {
        type: 'resize-break',
        matchId: 20,
        newDurationMinutes: 15,
      });

      expect(transition.state).toEqual(start);
      expect(transition.actions).toEqual([]);
    });

    it('a tray tap from idle selects, enabling the orient-then-place flow', () => {
      const { state, actions } = plannerReducer(planner('overview'), {
        type: 'tap-tray-match',
        matchId: 30,
      });

      expect(state).toEqual(planner('overview', traySelected(30)));
      expect(actions).toEqual([]);
    });

    it('a tray tap with an active selection never swaps', () => {
      const start = planner('overview', selected(ref(10, 1, 2)));
      const transition = plannerReducer(start, { type: 'tap-tray-match', matchId: 30 });

      expect(transition.state).toEqual(start);
      expect(transition.actions).toEqual([]);
    });

    it('the unschedule button still works', () => {
      const { state, actions } = plannerReducer(planner('overview', selected(ref(10, 1, 2))), {
        type: 'unschedule',
      });

      expect(state).toEqual(planner('overview'));
      expect(actions).toEqual([{ type: 'unschedule', matchId: 10 }]);
    });

    it('a tap on a locked match never opens the action sheet', () => {
      const { state, actions } = plannerReducer(planner('overview'), {
        type: 'tap-match',
        match: lockedRef(10, 1, 0),
      });

      expect(state).toEqual(planner('overview'));
      expect(actions).toEqual([]);
    });

    it('the action sheet buttons still work, like the other explicit buttons', () => {
      const sheet = planner('overview', sheetOpen(lockedRef(10, 1, 0)));

      const dismissed = plannerReducer(sheet, { type: 'dismiss-action-sheet' });
      expect(dismissed.state).toEqual(planner('overview'));

      const overridden = plannerReducer(sheet, { type: 'move-anyway' });
      expect(overridden.state).toEqual(
        planner('overview', selected({ ...lockedRef(10, 1, 0), locked: false }))
      );
      expect(overridden.actions).toEqual([]);
    });

    it('a tap on the grid zooms in toward the tapped court/time region', () => {
      const { state, actions, focus } = plannerReducer(planner('overview'), {
        type: 'tap-overview',
        courtId: 3,
        fraction: 0.25,
      });

      expect(state.zoom).toBe('compact');
      expect(focus).toEqual({ courtId: 3, fraction: 0.25 });
      expect(actions).toEqual([]);
    });

    it('zooming in via a tap keeps the active selection for placement at compact', () => {
      const start = planner('overview', traySelected(30));

      const navigated = plannerReducer(start, {
        type: 'tap-overview',
        courtId: 2,
        fraction: 0.1,
      });
      expect(navigated.state).toEqual(planner('compact', traySelected(30)));

      const placed = plannerReducer(navigated.state, {
        type: 'tap-insertion-line',
        courtId: 2,
        index: 0,
      });
      expect(placed.actions).toEqual([
        {
          type: 'reschedule',
          matchId: 30,
          body: { old_court_id: null, old_position: null, new_court_id: 2, new_position: 0 },
        },
      ]);
    });

    it('cancel still clears the selection', () => {
      const { state } = plannerReducer(planner('overview', selected(ref(10, 1, 2))), {
        type: 'cancel',
      });
      expect(state).toEqual(planner('overview'));
    });
  });
});
