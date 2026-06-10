import { describe, expect, it } from 'vitest';

import { GridMatchRef, IDLE_SELECTION, SelectionState, selectionReducer } from './selection';

function ref(matchId: number, courtId: number, position: number): GridMatchRef {
  return { matchId, courtId, position };
}

function selected(match: GridMatchRef): SelectionState {
  return { kind: 'match-selected', match };
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
