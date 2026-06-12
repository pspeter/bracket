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
  position: number | null,
  durationMinutes = 15,
  marginMinutes = 5,
  startTime: string | null = TOURNAMENT_START
): LayoutMatch {
  return {
    id,
    position_in_schedule: position,
    duration_minutes: durationMinutes,
    margin_minutes: marginMinutes,
    start_time: startTime,
  };
}

function playedMatch(
  id: number,
  position: number,
  state: LayoutMatchState = 'COMPLETED',
  durationMinutes = 15,
  marginMinutes = 5
): LayoutMatch {
  return { ...match(id, position, durationMinutes, marginMinutes), state };
}

describe('computeScheduleLayout', () => {
  it('packs matches sequentially from the tournament start time', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0, 15, 5), match(11, 1, 30, 10)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(layout.courts).toHaveLength(1);
    const blocks = layout.courts[0].blocks;
    expect(blocks.map((b) => b.match.id)).toEqual([10, 11]);

    expect(blocks[0].startMinutes).toBe(0);
    expect(blocks[0].durationMinutes).toBe(15);
    expect(blocks[0].marginMinutes).toBe(5);
    expect(blocks[0].endMinutes).toBe(20);
    expect(blocks[0].startTime).toEqual(new Date('2026-06-10T09:00:00Z'));

    expect(blocks[1].startMinutes).toBe(20);
    expect(blocks[1].durationMinutes).toBe(30);
    expect(blocks[1].marginMinutes).toBe(10);
    expect(blocks[1].endMinutes).toBe(60);
    expect(blocks[1].startTime).toEqual(new Date('2026-06-10T09:20:00Z'));
  });

  it('orders matches by position_in_schedule regardless of input order', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(12, 2), match(10, 0), match(11, 1)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(layout.courts[0].blocks.map((b) => b.match.id)).toEqual([10, 11, 12]);
    expect(layout.courts[0].blocks.map((b) => b.startMinutes)).toEqual([0, 20, 40]);
  });

  it('packs each court independently with varying durations and margins', () => {
    const layout = computeScheduleLayout({
      courts: [court(1), court(2), court(3)],
      matchesByCourtId: {
        1: [match(10, 0, 15, 5), match(11, 1, 15, 5)],
        2: [match(20, 0, 45, 0), match(21, 1, 10, 20)],
      },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(layout.courts.map((c) => c.court.id)).toEqual([1, 2, 3]);

    const [c1, c2, c3] = layout.courts;
    expect(c1.blocks.map((b) => [b.startMinutes, b.endMinutes])).toEqual([
      [0, 20],
      [20, 40],
    ]);
    expect(c2.blocks.map((b) => [b.startMinutes, b.endMinutes])).toEqual([
      [0, 45],
      [45, 75],
    ]);
    expect(c3.blocks).toEqual([]);
  });

  it('excludes unscheduled matches (no start time)', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0), match(11, null, 15, 5, null)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(layout.courts[0].blocks.map((b) => b.match.id)).toEqual([10]);
  });

  it('rounds the total height up to a whole tick interval covering the longest court', () => {
    const layout = computeScheduleLayout({
      courts: [court(1), court(2)],
      matchesByCourtId: {
        1: [match(10, 0, 15, 5)],
        2: [match(20, 0, 60, 10)],
      },
      tournamentStartTime: TOURNAMENT_START,
      tickIntervalMinutes: 30,
    });

    // Longest court ends at 70 minutes -> rounded up to 90.
    expect(layout.totalMinutes).toBe(90);
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
      matchesByCourtId: { 1: [match(10, 0, 50, 10)] },
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
    // The backend folds custom durations/margins into duration_minutes/margin_minutes,
    // so the layout only needs to honour the effective values.
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0, 90, 2), match(11, 1, 5, 0)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    const blocks = layout.courts[0].blocks;
    expect(blocks[0].endMinutes - blocks[0].startMinutes).toBe(92);
    expect(blocks[1].startMinutes).toBe(92);
    expect(blocks[1].endMinutes).toBe(97);
  });
});

describe('computeInsertionLines', () => {
  it('returns a single line at the top for an empty court', () => {
    expect(computeInsertionLines([])).toEqual([{ index: 0, offsetMinutes: 0 }]);
  });

  it('puts lines half a margin above the first match, centered in each margin gap, and after the last match', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0, 15, 5), match(11, 1, 30, 10)] },
      tournamentStartTime: TOURNAMENT_START,
    });

    expect(computeInsertionLines(layout.courts[0].blocks)).toEqual([
      // Half the first match's 5-minute margin above its start.
      { index: 0, offsetMinutes: -2.5 },
      // Centered in the 15..20 gap between the two cards.
      { index: 1, offsetMinutes: 17.5 },
      // Centered in the 50..60 gap after the last card.
      { index: 2, offsetMinutes: 55 },
    ]);
  });

  it('places lines on the card boundary when there is no margin', () => {
    const layout = computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: [match(10, 0, 20, 0), match(11, 1, 20, 0)] },
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
    const blocks = blocksFor([match(10, 0), match(11, 1)]);

    expect(blocks.map((b) => b.locked)).toEqual([false, false]);
  });

  it('locks completed and in-progress matches', () => {
    const blocks = blocksFor([
      playedMatch(10, 0, 'COMPLETED'),
      playedMatch(11, 1, 'IN_PROGRESS'),
      match(12, 2),
    ]);

    expect(blocks.map((b) => b.locked)).toEqual([true, true, false]);
  });

  it('treats matches without a state as upcoming', () => {
    const blocks = blocksFor([match(10, 0), { ...match(11, 1), state: 'NOT_STARTED' }]);

    expect(blocks.map((b) => b.locked)).toEqual([false, false]);
  });

  it('locks an upcoming match sitting above a played one, freezing the whole past', () => {
    // Moving the sandwiched upcoming match would shift the recorded start time
    // of the completed match below it, so it is part of the frozen past.
    const blocks = blocksFor([match(10, 0), playedMatch(11, 1, 'COMPLETED'), match(12, 2)]);

    expect(blocks.map((b) => b.locked)).toEqual([true, true, false]);
  });
});

describe('computeInsertionLines with played matches', () => {
  function blocksFor(matches: LayoutMatch[]) {
    return computeScheduleLayout({
      courts: [court(1)],
      matchesByCourtId: { 1: matches },
      tournamentStartTime: TOURNAMENT_START,
    }).courts[0].blocks;
  }

  it('offers all positions on a court with no played matches', () => {
    const lines = computeInsertionLines(blocksFor([match(10, 0), match(11, 1)]));

    expect(lines.map((line) => line.index)).toEqual([0, 1, 2]);
  });

  it('hides lines above the last completed match', () => {
    const lines = computeInsertionLines(
      blocksFor([
        playedMatch(10, 0, 'COMPLETED'),
        playedMatch(11, 1, 'COMPLETED'),
        match(12, 2),
        match(13, 3),
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
      blocksFor([playedMatch(10, 0, 'IN_PROGRESS'), match(11, 1)])
    );

    expect(lines.map((line) => line.index)).toEqual([1, 2]);
  });

  it('offers only the end-of-court line when every match is played', () => {
    const lines = computeInsertionLines(
      blocksFor([playedMatch(10, 0, 'COMPLETED'), playedMatch(11, 1, 'IN_PROGRESS')])
    );

    expect(lines.map((line) => line.index)).toEqual([2]);
  });

  it('hides lines around an upcoming match sandwiched between played ones', () => {
    const lines = computeInsertionLines(
      blocksFor([
        playedMatch(10, 0, 'COMPLETED'),
        match(11, 1),
        playedMatch(12, 2, 'COMPLETED'),
        match(13, 3),
      ])
    );

    expect(lines.map((line) => line.index)).toEqual([3, 4]);
  });

  it('still offers the single top line on an empty court', () => {
    expect(computeInsertionLines([])).toEqual([{ index: 0, offsetMinutes: 0 }]);
  });
});
