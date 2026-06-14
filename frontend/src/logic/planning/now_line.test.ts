import { describe, expect, it } from 'vitest';

import { currentTimeOffsetMinutes } from './now_line';

describe('currentTimeOffsetMinutes', () => {
  const tournamentStartTime = '2026-06-10T09:00:00Z';

  it('returns the minute offset when now falls inside the schedule span', () => {
    expect(
      currentTimeOffsetMinutes({
        tournamentStartTime,
        totalMinutes: 120,
        now: new Date('2026-06-10T09:45:00Z'),
      })
    ).toBe(45);
  });

  it('renders at both schedule boundaries', () => {
    expect(
      currentTimeOffsetMinutes({
        tournamentStartTime,
        totalMinutes: 120,
        now: new Date('2026-06-10T09:00:00Z'),
      })
    ).toBe(0);
    expect(
      currentTimeOffsetMinutes({
        tournamentStartTime,
        totalMinutes: 120,
        now: new Date('2026-06-10T11:00:00Z'),
      })
    ).toBe(120);
  });

  it('returns null when now is outside the schedule span', () => {
    expect(
      currentTimeOffsetMinutes({
        tournamentStartTime,
        totalMinutes: 120,
        now: new Date('2026-06-10T08:59:00Z'),
      })
    ).toBeNull();
    expect(
      currentTimeOffsetMinutes({
        tournamentStartTime,
        totalMinutes: 120,
        now: new Date('2026-06-10T11:01:00Z'),
      })
    ).toBeNull();
  });
});
