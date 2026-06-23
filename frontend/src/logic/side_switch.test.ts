import { describe, expect, it } from 'vitest';

import { shouldShowSideSwitchReminder } from './side_switch';

describe('shouldShowSideSwitchReminder', () => {
  it('returns false when n is null', () => {
    expect(shouldShowSideSwitchReminder(7, null)).toBe(false);
  });

  it('returns false at combined score 0', () => {
    expect(shouldShowSideSwitchReminder(0, 7)).toBe(false);
  });

  it('returns true when combined score hits threshold', () => {
    expect(shouldShowSideSwitchReminder(7, 7)).toBe(true);
  });

  it('returns false between thresholds', () => {
    expect(shouldShowSideSwitchReminder(8, 7)).toBe(false);
  });

  it('returns true at multiples of threshold', () => {
    expect(shouldShowSideSwitchReminder(14, 7)).toBe(true);
  });
});

import { computeSideSwitchState } from './side_switch';

describe('computeSideSwitchState', () => {
  it('shows reminder when score first hits threshold', () => {
    expect(computeSideSwitchState(7, 6, 7, false, null)).toEqual({
      showReminder: true,
      dismissedThreshold: null,
    });
  });

  it('does not show reminder when already dismissed at this threshold', () => {
    // dismissed at combined=7, still at 7
    expect(computeSideSwitchState(7, 7, 7, false, 7)).toEqual({
      showReminder: false,
      dismissedThreshold: 7,
    });
  });

  it('clears dismissal and shows reminder at next threshold', () => {
    // dismissed at 7, now score reaches 14
    expect(computeSideSwitchState(14, 13, 7, false, 7)).toEqual({
      showReminder: true,
      dismissedThreshold: null,
    });
  });

  it('does not re-show if score corrected backward through threshold then forward again', () => {
    // was at 7 (dismissed), score corrected to 6, then back to 7 again
    // previous combined was 6 (going up), dismissed was at 7 (but now we're approaching 7 again)
    // The dismissedThreshold=7 still holds — no re-trigger
    expect(computeSideSwitchState(7, 6, 7, false, 7)).toEqual({
      showReminder: false,
      dismissedThreshold: 7,
    });
  });
});
