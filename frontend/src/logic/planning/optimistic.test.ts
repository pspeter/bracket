import { describe, expect, it } from 'vitest';

import { OptimisticMatch, applyPlanningActions } from './optimistic';
import { PlanningAction } from './selection';

const START = '2022-01-01T10:00:00.000Z';

function minutesAfterStart(minutes: number): string {
  return new Date(new Date(START).getTime() + minutes * 60_000).toISOString();
}

function match(
  id: number,
  courtId: number | null,
  position: number | null,
  startMinutes: number | null
): OptimisticMatch {
  return {
    id,
    court_id: courtId,
    position_in_schedule: position,
    start_time: startMinutes == null ? null : minutesAfterStart(startMinutes),
    duration_minutes: 10,
    margin_minutes: 5,
  };
}

function stagesWith(matches: OptimisticMatch[]) {
  return [{ stage_items: [{ rounds: [{ matches }] }] }];
}

function apply(matches: OptimisticMatch[], actions: PlanningAction[]) {
  const result = applyPlanningActions(stagesWith(matches), actions, START);
  const byId = new Map<number, OptimisticMatch>();
  for (const m of result[0].stage_items[0].rounds[0].matches) {
    byId.set(m.id, m);
  }
  return byId;
}

function slot(m: OptimisticMatch | undefined) {
  return {
    court_id: m?.court_id,
    position: m?.position_in_schedule,
    start_time: m?.start_time,
  };
}

describe('applyPlanningActions', () => {
  it('does not mutate the input stages', () => {
    const matches = [match(1, 1, 0, 0), match(2, 2, 0, 0)];
    const stages = stagesWith(matches);

    applyPlanningActions(stages, [{ type: 'swap', matchId1: 1, matchId2: 2 }], START);

    expect(matches[0].court_id).toEqual(1);
    expect(matches[1].court_id).toEqual(2);
  });

  it('swaps court and position of two matches on different courts', () => {
    // Court 1: 1, 2; court 2: 3, 4. Swap 2 (court 1, pos 1) with 3 (court 2, pos 0).
    const byId = apply(
      [match(1, 1, 0, 0), match(2, 1, 1, 15), match(3, 2, 0, 0), match(4, 2, 1, 15)],
      [{ type: 'swap', matchId1: 2, matchId2: 3 }]
    );

    expect(slot(byId.get(2))).toEqual({
      court_id: 2,
      position: 0,
      start_time: minutesAfterStart(0),
    });
    expect(slot(byId.get(3))).toEqual({
      court_id: 1,
      position: 1,
      start_time: minutesAfterStart(15),
    });
    expect(slot(byId.get(1))).toEqual({
      court_id: 1,
      position: 0,
      start_time: minutesAfterStart(0),
    });
    expect(slot(byId.get(4))).toEqual({
      court_id: 2,
      position: 1,
      start_time: minutesAfterStart(15),
    });
  });

  it('swaps two matches on the same court, leaving the one in between untouched', () => {
    const byId = apply(
      [match(1, 1, 0, 0), match(2, 1, 1, 15), match(3, 1, 2, 30)],
      [{ type: 'swap', matchId1: 1, matchId2: 3 }]
    );

    expect(slot(byId.get(1))).toEqual({
      court_id: 1,
      position: 2,
      start_time: minutesAfterStart(30),
    });
    expect(slot(byId.get(2))).toEqual({
      court_id: 1,
      position: 1,
      start_time: minutesAfterStart(15),
    });
    expect(slot(byId.get(3))).toEqual({
      court_id: 1,
      position: 0,
      start_time: minutesAfterStart(0),
    });
  });

  it('ignores a swap involving an unscheduled match', () => {
    const byId = apply(
      [match(1, 1, 0, 0), match(2, null, null, null)],
      [{ type: 'swap', matchId1: 1, matchId2: 2 }]
    );

    expect(slot(byId.get(1))).toEqual({
      court_id: 1,
      position: 0,
      start_time: minutesAfterStart(0),
    });
    expect(slot(byId.get(2))).toEqual({ court_id: null, position: null, start_time: null });
  });

  it('reschedules a match to another court, inserting before the occupant', () => {
    const byId = apply(
      [match(1, 1, 0, 0), match(2, 1, 1, 15), match(3, 2, 0, 0)],
      [
        {
          type: 'reschedule',
          matchId: 2,
          body: { old_court_id: 1, old_position: 1, new_court_id: 2, new_position: 0 },
        },
      ]
    );

    expect(slot(byId.get(2))).toEqual({
      court_id: 2,
      position: 0,
      start_time: minutesAfterStart(0),
    });
    expect(slot(byId.get(3))).toEqual({
      court_id: 2,
      position: 1,
      start_time: minutesAfterStart(15),
    });
    expect(slot(byId.get(1))).toEqual({
      court_id: 1,
      position: 0,
      start_time: minutesAfterStart(0),
    });
  });

  it('reschedules a match later on the same court, inserting after the occupant', () => {
    const byId = apply(
      [match(1, 1, 0, 0), match(2, 1, 1, 15), match(3, 1, 2, 30)],
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

    expect(slot(byId.get(2))).toEqual({
      court_id: 1,
      position: 0,
      start_time: minutesAfterStart(0),
    });
    expect(slot(byId.get(3))).toEqual({
      court_id: 1,
      position: 1,
      start_time: minutesAfterStart(15),
    });
    expect(slot(byId.get(1))).toEqual({
      court_id: 1,
      position: 2,
      start_time: minutesAfterStart(30),
    });
  });

  it('schedules a tray match onto a court', () => {
    const byId = apply(
      [match(1, 1, 0, 0), match(2, null, null, null)],
      [
        {
          type: 'reschedule',
          matchId: 2,
          body: { old_court_id: null, old_position: null, new_court_id: 1, new_position: 0 },
        },
      ]
    );

    expect(slot(byId.get(2))).toEqual({
      court_id: 1,
      position: 0,
      start_time: minutesAfterStart(0),
    });
    expect(slot(byId.get(1))).toEqual({
      court_id: 1,
      position: 1,
      start_time: minutesAfterStart(15),
    });
  });

  it('unschedules a match and re-packs the remaining ones', () => {
    const byId = apply(
      [match(1, 1, 0, 0), match(2, 1, 1, 15), match(3, 1, 2, 30)],
      [{ type: 'unschedule', matchId: 2 }]
    );

    expect(slot(byId.get(2))).toEqual({ court_id: null, position: null, start_time: null });
    expect(slot(byId.get(1))).toEqual({
      court_id: 1,
      position: 0,
      start_time: minutesAfterStart(0),
    });
    expect(slot(byId.get(3))).toEqual({
      court_id: 1,
      position: 1,
      start_time: minutesAfterStart(15),
    });
  });
});
