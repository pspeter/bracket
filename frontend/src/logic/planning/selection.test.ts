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

    it('tap-tray-match enters tray-match-selected state', () => {
      const { state, reschedule, swap, unschedule } = selectionReducer(IDLE_SELECTION, {
        type: 'tap-tray-match',
        matchId: 99,
      });

      expect(state).toEqual(traySelected(99));
      expect(reschedule).toBeNull();
      expect(swap).toBeNull();
      expect(unschedule).toBeNull();
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

    it('tapping a different match on another court swaps the two', () => {
      const { state, reschedule, swap } = selectionReducer(selection, {
        type: 'tap-match',
        match: ref(20, 2, 0),
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toBeNull();
      // First step: move selected (match 10) to match 20's position
      expect(swap?.first).toEqual({
        matchId: 10,
        body: { old_court_id: 1, old_position: 2, new_court_id: 2, new_position: 0 },
      });
      // Second step: move match 20 to where match 10 was; after step 1 match 20
      // shifts from court2/0 to court2/1 (different courts → posB + 1)
      expect(swap?.second).toEqual({
        matchId: 20,
        body: { old_court_id: 2, old_position: 1, new_court_id: 1, new_position: 2 },
      });
    });

    it('swapping same-court match ahead of selected shifts it down by one', () => {
      // Court 1: [A(0), X(1), sel(2), B(3)] — swap sel(2) with B(3)
      const { swap } = selectionReducer(selected(ref(10, 1, 2)), {
        type: 'tap-match',
        match: ref(30, 1, 3),
      });

      // First step: move sel to pos 3 (B's position, same court, sel < B)
      expect(swap?.first).toEqual({
        matchId: 10,
        body: { old_court_id: 1, old_position: 2, new_court_id: 1, new_position: 3 },
      });
      // Second step: B was at 3, now at 3-1=2 (A before B on same court → posB-1)
      expect(swap?.second).toEqual({
        matchId: 30,
        body: { old_court_id: 1, old_position: 2, new_court_id: 1, new_position: 2 },
      });
    });

    it('swapping same-court match behind selected shifts it up by one', () => {
      // Court 1: [B(0), X(1), sel(2)] — swap sel(2) with B(0)
      const { swap } = selectionReducer(selected(ref(10, 1, 2)), {
        type: 'tap-match',
        match: ref(30, 1, 0),
      });

      // First step: move sel to pos 0 (B's position, same court, sel > B)
      expect(swap?.first).toEqual({
        matchId: 10,
        body: { old_court_id: 1, old_position: 2, new_court_id: 1, new_position: 0 },
      });
      // Second step: B was at 0, now at 0+1=1 (A after B on same court → posB+1)
      expect(swap?.second).toEqual({
        matchId: 30,
        body: { old_court_id: 1, old_position: 1, new_court_id: 1, new_position: 2 },
      });
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

    it('unschedule returns idle with unschedule request', () => {
      const { state, reschedule, swap, unschedule } = selectionReducer(selection, {
        type: 'unschedule',
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toBeNull();
      expect(swap).toBeNull();
      expect(unschedule).toEqual({ matchId: 10 });
    });
  });

  describe('with a tray match selected', () => {
    const selection = traySelected(99);

    it('cancel returns to idle', () => {
      const { state, reschedule, swap, unschedule } = selectionReducer(selection, {
        type: 'cancel',
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toBeNull();
      expect(swap).toBeNull();
      expect(unschedule).toBeNull();
    });

    it('tapping the same tray match again deselects it', () => {
      const { state, swap } = selectionReducer(selection, {
        type: 'tap-tray-match',
        matchId: 99,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(swap).toBeNull();
    });

    it('tapping a different tray match switches the selection', () => {
      const { state } = selectionReducer(selection, {
        type: 'tap-tray-match',
        matchId: 77,
      });

      expect(state).toEqual(traySelected(77));
    });

    it('tapping a grid match switches to match-selected', () => {
      const { state, reschedule, swap } = selectionReducer(selection, {
        type: 'tap-match',
        match: ref(20, 1, 0),
      });

      expect(state).toEqual(selected(ref(20, 1, 0)));
      expect(reschedule).toBeNull();
      expect(swap).toBeNull();
    });

    it('placing at an insertion line schedules the tray match with null old fields', () => {
      const { state, reschedule, swap, unschedule } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 3,
        index: 1,
      });

      expect(state).toEqual(IDLE_SELECTION);
      expect(reschedule).toEqual({
        matchId: 99,
        body: { old_court_id: null, old_position: null, new_court_id: 3, new_position: 1 },
      });
      expect(swap).toBeNull();
      expect(unschedule).toBeNull();
    });

    it('placing at the start of a court uses index 0 as new_position', () => {
      const { reschedule } = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: 3,
        index: 0,
      });

      expect(reschedule).toEqual({
        matchId: 99,
        body: { old_court_id: null, old_position: null, new_court_id: 3, new_position: 0 },
      });
    });
  });
});
