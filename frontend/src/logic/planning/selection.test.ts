import { describe, expect, it } from 'vitest';

import { GridMatchRef, IDLE_SELECTION, SelectionState, selectionReducer } from './selection';

function ref(matchId: number, courtId: number, position: number): GridMatchRef {
  return { matchId, courtId, position };
}

function selected(match: GridMatchRef): SelectionState {
  return { kind: 'match-selected', match };
}

function traySelected(matchId: number): SelectionState {
  return { kind: 'tray-match-selected', matchId };
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

    it('tapping the selected match again deselects it', () => {
      const { state, actions } = selectionReducer(selection, {
        type: 'tap-match',
        match: ref(10, 1, 2),
      });

      expect(state).toEqual(IDLE_SELECTION);
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
});
