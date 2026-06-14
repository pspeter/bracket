import { describe, expect, it } from 'vitest';

import {
  SCHEDULE_POLL_INTERVAL_MS,
  isStaleScheduleError,
  pollingPaused,
  scheduleRefreshInterval,
  shouldRefreshOnSelectionChange,
} from './polling';
import { GridMatchRef, IDLE_SELECTION, SelectionState } from './selection';

const MATCH: GridMatchRef = { matchId: 10, courtId: 1, position: 2 };

const MATCH_SELECTED: SelectionState = { kind: 'match-selected', match: MATCH };
const TRAY_SELECTED: SelectionState = { kind: 'tray-match-selected', matchId: 10 };
const CONFIRM_MOVE: SelectionState = {
  kind: 'confirm-move',
  previous: MATCH_SELECTED,
  action: { type: 'swap', matchId1: 10, matchId2: 20 },
};

describe('pollingPaused', () => {
  it('polls while idle', () => {
    expect(pollingPaused(IDLE_SELECTION)).toBe(false);
  });

  it('pauses while a grid match is selected', () => {
    expect(pollingPaused(MATCH_SELECTED)).toBe(true);
  });

  it('pauses while a tray match is selected', () => {
    expect(pollingPaused(TRAY_SELECTED)).toBe(true);
  });

  it('pauses while move confirmation is pending', () => {
    expect(pollingPaused(CONFIRM_MOVE)).toBe(true);
  });
});

describe('scheduleRefreshInterval', () => {
  it('returns the polling interval while idle', () => {
    expect(scheduleRefreshInterval(IDLE_SELECTION)).toBe(SCHEDULE_POLL_INTERVAL_MS);
  });

  it('disables polling while a selection is active', () => {
    expect(scheduleRefreshInterval(MATCH_SELECTED)).toBe(0);
    expect(scheduleRefreshInterval(TRAY_SELECTED)).toBe(0);
    expect(scheduleRefreshInterval(CONFIRM_MOVE)).toBe(0);
  });
});

describe('shouldRefreshOnSelectionChange', () => {
  it('refreshes when a selection clears', () => {
    expect(shouldRefreshOnSelectionChange(MATCH_SELECTED, IDLE_SELECTION)).toBe(true);
    expect(shouldRefreshOnSelectionChange(TRAY_SELECTED, IDLE_SELECTION)).toBe(true);
    expect(shouldRefreshOnSelectionChange(CONFIRM_MOVE, IDLE_SELECTION)).toBe(true);
  });

  it('does not refresh while idle stays idle', () => {
    expect(shouldRefreshOnSelectionChange(IDLE_SELECTION, IDLE_SELECTION)).toBe(false);
  });

  it('does not refresh when a selection starts', () => {
    expect(shouldRefreshOnSelectionChange(IDLE_SELECTION, MATCH_SELECTED)).toBe(false);
  });

  it('does not refresh while the pause continues across selection changes', () => {
    // E.g. selected match -> confirmation, or switching tray selections.
    expect(shouldRefreshOnSelectionChange(MATCH_SELECTED, CONFIRM_MOVE)).toBe(false);
    expect(shouldRefreshOnSelectionChange(CONFIRM_MOVE, MATCH_SELECTED)).toBe(false);
    expect(shouldRefreshOnSelectionChange(TRAY_SELECTED, TRAY_SELECTED)).toBe(false);
  });
});

describe('isStaleScheduleError', () => {
  it('recognizes the 409 stale-write rejection', () => {
    expect(isStaleScheduleError({ response: { status: 409 } })).toBe(true);
  });

  it('rejects other HTTP errors', () => {
    expect(isStaleScheduleError({ response: { status: 400 } })).toBe(false);
    expect(isStaleScheduleError({ response: { status: 500 } })).toBe(false);
  });

  it('rejects network errors without a response', () => {
    expect(isStaleScheduleError({ code: 'ERR_NETWORK' })).toBe(false);
    expect(isStaleScheduleError(new Error('boom'))).toBe(false);
  });

  it('rejects non-object errors', () => {
    expect(isStaleScheduleError(null)).toBe(false);
    expect(isStaleScheduleError(undefined)).toBe(false);
    expect(isStaleScheduleError('409')).toBe(false);
  });
});
