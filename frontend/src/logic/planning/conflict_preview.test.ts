import { describe, expect, it } from 'vitest';

import {
  ConflictPreviewMatch,
  actionCreatesSelectedConflict,
  computeConflictPreview,
  insertionLineKey,
} from './conflict_preview';
import { computeScheduleLayout } from './layout';

const START = '2026-06-10T09:00:00.000Z';
const PACKED_SLOT_MINUTES = 105;

function minutesAfterStart(minutes: number): string {
  return new Date(new Date(START).getTime() + minutes * 60_000).toISOString();
}

function match({
  id,
  courtId,
  position,
  startMinutes,
  input1,
  input2,
  durationMinutes = 90,
  marginMinutes = 15,
}: {
  id: number;
  courtId: number | null;
  position: number | null;
  startMinutes: number | null;
  input1: number;
  input2: number;
  durationMinutes?: number;
  marginMinutes?: number;
}): ConflictPreviewMatch {
  return {
    id,
    court_id: courtId,
    position_in_schedule: position,
    start_time: startMinutes == null ? null : minutesAfterStart(startMinutes),
    duration_minutes: durationMinutes,
    margin_minutes: marginMinutes,
    stage_item_input1_id: input1,
    stage_item_input2_id: input2,
  };
}

function stagesWith(matches: ConflictPreviewMatch[]) {
  return [{ stage_items: [{ rounds: [{ matches }] }] }];
}

describe('actionCreatesSelectedConflict', () => {
  it('detects a selected-match team overlap after a simulated insertion repacks courts', () => {
    const stages = stagesWith([
      match({ id: 1, courtId: 1, position: 0, startMinutes: 0, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 2, position: 0, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 3, position: 0, startMinutes: 0, input1: 10, input2: 30 }),
    ]);

    expect(
      actionCreatesSelectedConflict({
        stages,
        selectedMatchId: 1,
        tournamentStartTime: START,
        action: {
          type: 'reschedule',
          matchId: 1,
          body: {
            old_court_id: 1,
            old_position: 0,
            new_court_id: 2,
            new_position: 0,
          },
        },
      })
    ).toBe(true);
  });

  it('does not count the selected match post-match margin as team overlap', () => {
    const stages = stagesWith([
      match({ id: 1, courtId: 1, position: 0, startMinutes: 0, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 2, position: 0, startMinutes: 0, input1: 40, input2: 50 }),
      match({
        id: 3,
        courtId: 3,
        position: 0,
        startMinutes: 0,
        input1: 40,
        input2: 50,
        marginMinutes: 0,
      }),
      match({ id: 4, courtId: 3, position: 1, startMinutes: 90, input1: 10, input2: 30 }),
    ]);

    expect(
      actionCreatesSelectedConflict({
        stages,
        selectedMatchId: 1,
        tournamentStartTime: START,
        action: {
          type: 'reschedule',
          matchId: 1,
          body: {
            old_court_id: 1,
            old_position: 0,
            new_court_id: 2,
            new_position: 0,
          },
        },
      })
    ).toBe(false);
  });
});

describe('computeConflictPreview', () => {
  it('flags insertion lines that would create a selected-match team overlap', () => {
    const matches = [
      match({ id: 1, courtId: 1, position: 0, startMinutes: 0, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 2, position: 0, startMinutes: 0, input1: 40, input2: 50 }),
      match({
        id: 3,
        courtId: 2,
        position: 1,
        startMinutes: PACKED_SLOT_MINUTES,
        input1: 40,
        input2: 50,
      }),
      match({ id: 4, courtId: 3, position: 0, startMinutes: 0, input1: 10, input2: 30 }),
    ];
    const layout = computeScheduleLayout({
      courts: [
        { id: 1, name: 'Court 1' },
        { id: 2, name: 'Court 2' },
        { id: 3, name: 'Court 3' },
      ],
      matchesByCourtId: { 1: [matches[0]], 2: [matches[1], matches[2]], 3: [matches[3]] },
      tournamentStartTime: START,
    });

    const preview = computeConflictPreview({
      stages: stagesWith(matches),
      layout,
      selection: {
        kind: 'match-selected',
        match: { matchId: 1, courtId: 1, position: 0 },
      },
    });

    expect([...preview.insertionLines]).toContain(insertionLineKey(2, 0));
    expect([...preview.insertionLines]).not.toContain(insertionLineKey(2, 2));
  });

  it('flags tray-initiated insertion lines using the unscheduled match teams', () => {
    const matches = [
      match({ id: 1, courtId: null, position: null, startMinutes: null, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 1, position: 0, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 2, position: 0, startMinutes: 0, input1: 10, input2: 30 }),
    ];
    const layout = computeScheduleLayout({
      courts: [
        { id: 1, name: 'Court 1' },
        { id: 2, name: 'Court 2' },
      ],
      matchesByCourtId: { 1: [matches[1]], 2: [matches[2]] },
      tournamentStartTime: START,
    });

    const preview = computeConflictPreview({
      stages: stagesWith(matches),
      layout,
      selection: { kind: 'tray-match-selected', matchId: 1 },
    });

    expect([...preview.insertionLines]).toContain(insertionLineKey(1, 0));
    expect([...preview.insertionLines]).not.toContain(insertionLineKey(1, 1));
  });

  it('flags swap targets that would put the selected match into a conflicting slot', () => {
    const matches = [
      match({ id: 1, courtId: null, position: null, startMinutes: null, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 1, position: 0, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 2, position: 0, startMinutes: 0, input1: 10, input2: 30 }),
    ];
    const layout = computeScheduleLayout({
      courts: [
        { id: 1, name: 'Court 1' },
        { id: 2, name: 'Court 2' },
      ],
      matchesByCourtId: { 1: [matches[1]], 2: [matches[2]] },
      tournamentStartTime: START,
    });

    const preview = computeConflictPreview({
      stages: stagesWith(matches),
      layout,
      selection: { kind: 'tray-match-selected', matchId: 1 },
    });

    expect([...preview.swapTargets]).toContain(2);
    expect([...preview.swapTargets]).not.toContain(3);
  });

  it('flags scheduled-match swap targets after simulating the traded slots', () => {
    const matches = [
      match({ id: 1, courtId: 1, position: 0, startMinutes: 0, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 2, position: 0, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 3, position: 0, startMinutes: 0, input1: 10, input2: 30 }),
      match({
        id: 4,
        courtId: 2,
        position: 1,
        startMinutes: PACKED_SLOT_MINUTES,
        input1: 60,
        input2: 70,
      }),
    ];
    const layout = computeScheduleLayout({
      courts: [
        { id: 1, name: 'Court 1' },
        { id: 2, name: 'Court 2' },
        { id: 3, name: 'Court 3' },
      ],
      matchesByCourtId: { 1: [matches[0]], 2: [matches[1], matches[3]], 3: [matches[2]] },
      tournamentStartTime: START,
    });

    const preview = computeConflictPreview({
      stages: stagesWith(matches),
      layout,
      selection: {
        kind: 'match-selected',
        match: { matchId: 1, courtId: 1, position: 0 },
      },
    });

    expect([...preview.swapTargets]).toContain(2);
    expect([...preview.swapTargets]).not.toContain(4);
  });
});
