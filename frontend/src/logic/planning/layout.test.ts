import { describe, expect, it } from 'vitest';

import {
  LayoutCourt,
  LayoutMatch,
  LayoutMatchState,
  computeInsertionLines,
  computeScheduleLayout,
} from './layout';

const TOURNAMENT_START = '2026-06-10T09:00:00Z';

function court(id: number): LayoutCourt {
  return { id, name: `Court ${id}` };
}

function match(
  id: number,
  startMinutes: number | null = 0,
  durationMinutes = 15,
  startTime: string | null = minutesAfterStart(startMinutes)
): LayoutMatch {
  return {
    id,
    duration_minutes: durationMinutes,
    start_time: startTime,
  };
}

function minutesAfterStart(minutes: number | null): string | null {
  if (minutes == null) return null;
  return new Date(new Date(TOURNAMENT_START).getTime() + minutes * 60_000).toISOString();
}

function playedMatch(
  id: number,
  startMinutes = 0,
  state: LayoutMatchState = 'COMPLETED',
  durationMinutes = 15
): LayoutMatch {
  return { ...match(id, startMinutes, durationMinutes), state };
}

describe('computeScheduleLayout', () => {
  it('uses actual start times and duration-only block sizes', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0, 15), match(11, 20, 30)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(layout.courts).toHaveLength(1);
    const blocks = layout.courts[0].blocks;
    expect(blocks.map((b) => b.match.id)).toEqual([10, 11]);

    expect(blocks[0].startMinutes).toBe(0);
    expect(blocks[0].durationMinutes).toBe(15);
    expect(blocks[0].endMinutes).toBe(15);
    expect(blocks[0].startTime).toEqual(new Date('2026-06-10T09:00:00Z'));

    expect(blocks[1].startMinutes).toBe(20);
    expect(blocks[1].durationMinutes).toBe(30);
    expect(blocks[1].endMinutes).toBe(50);
    expect(blocks[1].startTime).toEqual(new Date('2026-06-10T09:20:00Z'));
  });

  it('orders matches by start time regardless of input order', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(12, 40), match(10, 0), match(11, 20)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(layout.courts[0].blocks.map((b) => b.match.id)).toEqual([10, 11, 12]);
    expect(layout.courts[0].blocks.map((b) => b.startMinutes)).toEqual([0, 20, 40]);
  });

  it('lays out each court independently with varying durations and gaps', () => {
    const layout = computeScheduleLayout({
      courts: [court(1), court(2), court(3)],
      matchesByCourtId: {
        1: [match(10, 0, 15), match(11, 20, 15)],
        2: [match(20, 0, 45), match(21, 45, 10)],
      },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(layout.courts.map((c) => c.court.id)).toEqual([1, 2, 3]);

    const [c1, c2, c3] = layout.courts;
    expect(c1.blocks.map((b) => [b.startMinutes, b.endMinutes])).toEqual([
      [0, 15],
      [20, 35],
    ]);
    expect(c2.blocks.map((b) => [b.startMinutes, b.endMinutes])).toEqual([
      [0, 45],
      [45, 55],
    ]);
    expect(c3.blocks).toEqual([]);
  });

  it('excludes unscheduled matches (no start time)', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10), match(11, null, 15, null)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(layout.courts[0].blocks.map((b) => b.match.id)).toEqual([10]);
  });

  it('rounds the total height up to a whole tick interval covering the longest court', () => {
    const layout = computeScheduleLayout({
      courts: [court(1), court(2)],
      matchesByCourtId: {
        1: [match(10, 0, 15)],
        2: [match(20, 0, 60)],
      },
      tournamentStartTime: TOURNAMENT_START,
      tickIntervalMinutes: 30,
    });

    expect(layout.totalMinutes).toBe(60);
  });

  it('uses a minimum total height for an empty schedule', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: {},
      tournamentStartTime: TOURNAMENT_START,
      tickIntervalMinutes: 30,
      minTotalMinutes: 60,
    });

    expect(layout.totalMinutes).toBe(60);
    expect(layout.courts[0].blocks).toEqual([]);
  });

  it('generates ruler ticks at the given interval, including both ends', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0, 50)] },
      tournamentStartTime: TOURNAMENT_START,
      tickIntervalMinutes: 30,
    });

    expect(layout.totalMinutes).toBe(60);
    expect(layout.ticks.map((tick) => tick.offsetMinutes)).toEqual([0, 30, 60]);
    expect(layout.ticks.map((tick) => tick.time)).toEqual([
      new Date('2026-06-10T09:00:00Z'),
      new Date('2026-06-10T09:30:00Z'),
      new Date('2026-06-10T10:00:00Z'),
    ]);
  });

  it('reflects custom (already-resolved) durations in block sizes', () => {
    // The backend folds custom durations into duration_minutes, so the layout only
    // needs to honour the effective value.
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0, 90), match(11, 92, 5)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    const blocks = layout.courts[0].blocks;
    expect(blocks[0].endMinutes - blocks[0].startMinutes).toBe(90);
    expect(blocks[1].startMinutes).toBe(92);
    expect(blocks[1].endMinutes).toBe(97);
  });
});

describe('computeInsertionLines', () => {
  it('returns a single line at the top for an empty court', () => {
    expect(computeInsertionLines([])).toEqual([{ index: 0, offsetMinutes: 0 }]);
  });

  it('puts lines before the first match, centered in gaps, and after the last match', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0, 15), match(11, 20, 30)] },
      tournamentStartTime: TOURNAMENT_START,
      defaultBreakMinutes: 5,
    });

    expect(computeInsertionLines(layout.courts[0].blocks)).toEqual([
      { index: 0, offsetMinutes: 0 },
      // Centered in the 15..20 gap between the two cards.
      { index: 1, offsetMinutes: 17.5 },
      { index: 2, offsetMinutes: 52.5 },
    ]);
  });

  it('places lines on the card boundary when there is no margin', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0, 20), match(11, 20, 20)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(computeInsertionLines(layout.courts[0].blocks)).toEqual([
      { index: 0, offsetMinutes: 0 },
      { index: 1, offsetMinutes: 20 },
      { index: 2, offsetMinutes: 40 },
    ]);
  });
});

describe('locked blocks for played matches', () => {
  function blocksFor(matches: LayoutMatch[]) {
    return computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: matches },
      tournamentStartTime: TOURNAMENT_START,
    }).courts[0].blocks;
  }

  it('locks nothing on a court with only upcoming matches', () => {
    const blocks = blocksFor([match(10, 0), match(11, 20)]);

    expect(blocks.map((b) => b.locked)).toEqual([false, false]);
  });

  it('locks completed and in-progress matches', () => {
    const blocks = blocksFor([
      playedMatch(10, 0, 'COMPLETED'),
      playedMatch(11, 20, 'IN_PROGRESS'),
      match(12, 40),
    ]);

    expect(blocks.map((b) => b.locked)).toEqual([true, true, false]);
  });

  it('treats matches without a state as upcoming', () => {
    const blocks = blocksFor([match(10, 0), { ...match(11, 20), state: 'NOT_STARTED' }]);

    expect(blocks.map((b) => b.locked)).toEqual([false, false]);
  });

  it('locks an upcoming match sitting above a played one, freezing the whole past', () => {
    // Moving the sandwiched upcoming match would shift the recorded start time
    // of the completed match below it, so it is part of the frozen past.
    const blocks = blocksFor([match(10, 0), playedMatch(11, 20, 'COMPLETED'), match(12, 40)]);

    expect(blocks.map((b) => b.locked)).toEqual([true, true, false]);
  });
});

describe('computeInsertionLines with played matches', () => {
  function blocksFor(matches: LayoutMatch[]) {
    return computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: matches },
      tournamentStartTime: TOURNAMENT_START,
      defaultBreakMinutes: 5,
    }).courts[0].blocks;
  }

  it('offers all positions on a court with no played matches', () => {
    const lines = computeInsertionLines(blocksFor([match(10, 0), match(11, 20)]));

    expect(lines.map((line) => line.index)).toEqual([0, 1, 2]);
  });

  it('hides lines above the last completed match', () => {
    const lines = computeInsertionLines(
      blocksFor([
        playedMatch(10, 0, 'COMPLETED'),
        playedMatch(11, 20, 'COMPLETED'),
        match(12, 40),
        match(13, 60),
      ])
    );

    expect(lines).toEqual([
      // Centered in the 35..40 gap after the last completed match.
      { index: 2, offsetMinutes: 37.5 },
      { index: 3, offsetMinutes: 57.5 },
      { index: 4, offsetMinutes: 77.5 },
    ]);
  });

  it('treats an in-progress match like a completed one', () => {
    const lines = computeInsertionLines(
      blocksFor([playedMatch(10, 0, 'IN_PROGRESS'), match(11, 20)])
    );

    expect(lines.map((line) => line.index)).toEqual([1, 2]);
  });

  it('offers only the end-of-court line when every match is played', () => {
    const lines = computeInsertionLines(
      blocksFor([playedMatch(10, 0, 'COMPLETED'), playedMatch(11, 20, 'IN_PROGRESS')])
    );

    expect(lines.map((line) => line.index)).toEqual([2]);
  });

  it('hides lines around an upcoming match sandwiched between played ones', () => {
    const lines = computeInsertionLines(
      blocksFor([
        playedMatch(10, 0, 'COMPLETED'),
        match(11, 20),
        playedMatch(12, 40, 'COMPLETED'),
        match(13, 60),
      ])
    );

    expect(lines.map((line) => line.index)).toEqual([3, 4]);
  });

  it('still offers the single top line on an empty court', () => {
    expect(computeInsertionLines([])).toEqual([{ index: 0, offsetMinutes: 0 }]);
  });
});
