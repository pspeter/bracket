import { describe, expect, it } from 'vitest';

import { OptimisticMatch, applyPlanningActions } from './optimistic';
import { PlanningAction } from './selection';

const START = '2022-01-01T10:00:00.000Z';
const BREAK = 5;

function minutesAfterStart(minutes: number): string {
  return new Date(new Date(START).getTime() + minutes * 60_000).toISOString();
}

function match(id: number, courtId: number | null, startMinutes: number | null): OptimisticMatch {
  return {
    id,
    court_id: courtId,
    start_time: startMinutes == null ? null : minutesAfterStart(startMinutes),
    duration_minutes: 10,
  };
}

function stagesWith(matches: OptimisticMatch[]) {
  return [{ stage_items: [{ rounds: [{ matches }] }] }];
}

function apply(matches: OptimisticMatch[], actions: PlanningAction[]) {
  const result = applyPlanningActions(stagesWith(matches), actions, START, BREAK);
  const byId = new Map<number, OptimisticMatch>();
  for (const m of result[0].stage_items[0].rounds[0].matches) {
    byId.set(m.id, m);
  }
  return byId;
}

function slot(m: OptimisticMatch | undefined) {
  return {
    court_id: m?.court_id,
    start_time: m?.start_time,
  };
}

describe('applyPlanningActions', () => {
  it('does not mutate the input stages', () => {
    const matches = [match(1, 1, 0), match(2, 2, 0)];
    const stages = stagesWith(matches);

    applyPlanningActions(stages, [{ type: 'swap', matchId1: 1, matchId2: 2 }], START, BREAK);

    expect(matches[0].court_id).toEqual(1);
    expect(matches[1].court_id).toEqual(2);
  });

  it('swaps court and start time of two matches on different courts', () => {
    // Court 1: 1@0, 2@15; court 2: 3@0, 4@15. Swap 2 with 3.
    const byId = apply(
      [match(1, 1, 0), match(2, 1, 15), match(3, 2, 0), match(4, 2, 15)],
      [{ type: 'swap', matchId1: 2, matchId2: 3 }]
    );

    expect(slot(byId.get(2))).toEqual({ court_id: 2, start_time: minutesAfterStart(0) });
    expect(slot(byId.get(3))).toEqual({ court_id: 1, start_time: minutesAfterStart(15) });
    expect(slot(byId.get(1))).toEqual({ court_id: 1, start_time: minutesAfterStart(0) });
    expect(slot(byId.get(4))).toEqual({ court_id: 2, start_time: minutesAfterStart(15) });
  });

  it('swaps two matches on the same court, leaving the one in between untouched', () => {
    const byId = apply(
      [match(1, 1, 0), match(2, 1, 15), match(3, 1, 30)],
      [{ type: 'swap', matchId1: 1, matchId2: 3 }]
    );

    expect(slot(byId.get(1))).toEqual({ court_id: 1, start_time: minutesAfterStart(30) });
    expect(slot(byId.get(2))).toEqual({ court_id: 1, start_time: minutesAfterStart(15) });
    expect(slot(byId.get(3))).toEqual({ court_id: 1, start_time: minutesAfterStart(0) });
  });

  it('swaps a scheduled match with a tray match, trading slot for tray', () => {
    const byId = apply(
      [match(1, 1, 0), match(2, 1, 15), match(3, null, null)],
      [{ type: 'swap', matchId1: 1, matchId2: 3 }]
    );

    expect(slot(byId.get(3))).toEqual({ court_id: 1, start_time: minutesAfterStart(0) });
    expect(slot(byId.get(1))).toEqual({ court_id: null, start_time: null });
    expect(slot(byId.get(2))).toEqual({ court_id: 1, start_time: minutesAfterStart(15) });
  });

  it('swaps a tray match with a scheduled match regardless of argument order', () => {
    const byId = apply(
      [match(1, 1, 0), match(2, null, null)],
      [{ type: 'swap', matchId1: 2, matchId2: 1 }]
    );

    expect(slot(byId.get(2))).toEqual({ court_id: 1, start_time: minutesAfterStart(0) });
    expect(slot(byId.get(1))).toEqual({ court_id: null, start_time: null });
  });

  it('ignores a swap of two unscheduled matches', () => {
    const byId = apply(
      [match(1, null, null), match(2, null, null)],
      [{ type: 'swap', matchId1: 1, matchId2: 2 }]
    );

    expect(slot(byId.get(1))).toEqual({ court_id: null, start_time: null });
    expect(slot(byId.get(2))).toEqual({ court_id: null, start_time: null });
  });

  it('reschedules a match to another court, inserting before the occupant', () => {
    const byId = apply(
      [match(1, 1, 0), match(2, 1, 15), match(3, 2, 0)],
      [
        {
          type: 'reschedule',
          matchId: 2,
          body: { old_court_id: 1, old_position: 1, new_court_id: 2, new_position: 0 },
        },
      ]
    );

    expect(slot(byId.get(2))).toEqual({ court_id: 2, start_time: minutesAfterStart(0) });
    expect(slot(byId.get(3))).toEqual({ court_id: 2, start_time: minutesAfterStart(15) });
    expect(slot(byId.get(1))).toEqual({ court_id: 1, start_time: minutesAfterStart(0) });
  });

  it('reschedules a match later on the same court, leaving the vacated gap behind', () => {
    const byId = apply(
      [match(1, 1, 0), match(2, 1, 15), match(3, 1, 30)],
      [
        {
          type: 'reschedule',
          matchId: 1,
          // Same-court move later: the reducer already turned insertion index 3
          // into new_position 2 ("after the occupant of position 2").
          body: { old_court_id: 1, old_position: 0, new_court_id: 1, new_position: 2 },
        },
      ]
    );

    // The other matches keep their start times; only the moved match shifts to
    // after the last occupied interval (30 + 10 duration + 5 break = 45).
    expect(slot(byId.get(2))).toEqual({ court_id: 1, start_time: minutesAfterStart(15) });
    expect(slot(byId.get(3))).toEqual({ court_id: 1, start_time: minutesAfterStart(30) });
    expect(slot(byId.get(1))).toEqual({ court_id: 1, start_time: minutesAfterStart(45) });
  });

  it('schedules a tray match onto a court, shifting the occupant', () => {
    const byId = apply(
      [match(1, 1, 0), match(2, null, null)],
      [
        {
          type: 'reschedule',
          matchId: 2,
          body: { old_court_id: null, old_position: null, new_court_id: 1, new_position: 0 },
        },
      ]
    );

    expect(slot(byId.get(2))).toEqual({ court_id: 1, start_time: minutesAfterStart(0) });
    expect(slot(byId.get(1))).toEqual({ court_id: 1, start_time: minutesAfterStart(15) });
  });

  it('grows a break, shifting the match after it and all later ones by the delta', () => {
    // Court 1: 1@0..10, 2@15..25, 3@30..40 (default 5-minute breaks).
    const byId = apply(
      [match(1, 1, 0), match(2, 1, 15), match(3, 1, 30)],
      [{ type: 'resize-break', matchId: 2, newDurationMinutes: 20 }]
    );

    // Match 1 is before the break: untouched. Match 2 starts at 1's end (10) + 20.
    expect(slot(byId.get(1))).toEqual({ court_id: 1, start_time: minutesAfterStart(0) });
    expect(slot(byId.get(2))).toEqual({ court_id: 1, start_time: minutesAfterStart(30) });
    // Match 3 keeps its gap to 2 and shifts by the same +15 delta.
    expect(slot(byId.get(3))).toEqual({ court_id: 1, start_time: minutesAfterStart(45) });
  });

  it('shrinks a leftover pause to compact the court from that point', () => {
    // Court 1: 1@0..10, 2@50..60 (40-minute pause), 3@65..75.
    const byId = apply(
      [match(1, 1, 0), match(2, 1, 50), match(3, 1, 65)],
      [{ type: 'resize-break', matchId: 2, newDurationMinutes: BREAK }]
    );

    expect(slot(byId.get(1))).toEqual({ court_id: 1, start_time: minutesAfterStart(0) });
    // Compacted to the default break after 1's end: 10 + 5 = 15.
    expect(slot(byId.get(2))).toEqual({ court_id: 1, start_time: minutesAfterStart(15) });
    // Match 3 keeps its 5-minute gap to 2 and moves by the same -35 delta.
    expect(slot(byId.get(3))).toEqual({ court_id: 1, start_time: minutesAfterStart(30) });
  });

  it('delays the whole court when the leading break (before the first match) grows', () => {
    // Resizing the break before match 1 delays it from the tournament start by 20.
    const byId = apply(
      [match(1, 1, 0), match(2, 1, 15)],
      [{ type: 'resize-break', matchId: 1, newDurationMinutes: 20 }]
    );

    expect(slot(byId.get(1))).toEqual({ court_id: 1, start_time: minutesAfterStart(20) });
    // Match 2 keeps its gap to the first and shifts by the same +20 delta.
    expect(slot(byId.get(2))).toEqual({ court_id: 1, start_time: minutesAfterStart(35) });
  });

  it('unschedules a match and leaves a gap, not re-packing the remaining ones', () => {
    const byId = apply(
      [match(1, 1, 0), match(2, 1, 15), match(3, 1, 30)],
      [{ type: 'unschedule', matchId: 2 }]
    );

    expect(slot(byId.get(2))).toEqual({ court_id: null, start_time: null });
    expect(slot(byId.get(1))).toEqual({ court_id: 1, start_time: minutesAfterStart(0) });
    expect(slot(byId.get(3))).toEqual({ court_id: 1, start_time: minutesAfterStart(30) });
  });
});
