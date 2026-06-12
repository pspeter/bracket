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
  startMinutes,
  input1,
  input2,
  durationMinutes = 90,
}: {
  id: number;
  courtId: number | null;
  startMinutes: number | null;
  input1: number;
  input2: number;
  durationMinutes?: number;
}): ConflictPreviewMatch {
  return {
    id,
    court_id: courtId,
    start_time: startMinutes == null ? null : minutesAfterStart(startMinutes),
    duration_minutes: durationMinutes,
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
      match({ id: 1, courtId: 1, startMinutes: 0, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 2, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 3, startMinutes: 0, input1: 10, input2: 30 }),
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

  it('applies the default break when repacking, pushing the moved match into a team overlap', () => {
    // Inserted after match 2, match 1 lands at 20 (end) + 10 break = 30, playing
    // [30, 50). With no break it would sit at [20, 40) and clear match 3 at [45, 65).
    const stages = stagesWith([
      match({ id: 1, courtId: 1, startMinutes: 0, input1: 10, input2: 20, durationMinutes: 20 }),
      match({ id: 2, courtId: 2, startMinutes: 0, input1: 40, input2: 50, durationMinutes: 20 }),
      match({ id: 3, courtId: 3, startMinutes: 45, input1: 10, input2: 30, durationMinutes: 20 }),
    ]);

    expect(
      actionCreatesSelectedConflict({
        stages,
        selectedMatchId: 1,
        tournamentStartTime: START,
        defaultBreakMinutes: 10,
        action: {
          type: 'reschedule',
          matchId: 1,
          body: {
            old_court_id: 1,
            old_position: 0,
            new_court_id: 2,
            new_position: 1,
          },
        },
      })
    ).toBe(true);
  });
});

describe('computeConflictPreview', () => {
  it('flags insertion lines that would create a selected-match team overlap', () => {
    const matches = [
      match({ id: 1, courtId: 1, startMinutes: 0, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 2, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 2, startMinutes: PACKED_SLOT_MINUTES, input1: 40, input2: 50 }),
      match({ id: 4, courtId: 3, startMinutes: 0, input1: 10, input2: 30 }),
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
      match({ id: 1, courtId: null, startMinutes: null, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 1, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 2, startMinutes: 0, input1: 10, input2: 30 }),
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

  it('flags insertion lines that push a later match into a team overlap', () => {
    const matches = [
      match({
        id: 1,
        courtId: null,
        startMinutes: null,
        input1: 100,
        input2: 101,
        durationMinutes: 20,
      }),
      match({ id: 2, courtId: 1, startMinutes: 0, input1: 200, input2: 201, durationMinutes: 20 }),
      match({ id: 3, courtId: 1, startMinutes: 30, input1: 10, input2: 11, durationMinutes: 20 }),
      match({ id: 4, courtId: 2, startMinutes: 0, input1: 300, input2: 301, durationMinutes: 20 }),
      match({ id: 5, courtId: 2, startMinutes: 30, input1: 302, input2: 303, durationMinutes: 20 }),
      match({ id: 6, courtId: 2, startMinutes: 60, input1: 10, input2: 12, durationMinutes: 20 }),
    ];
    const layout = computeScheduleLayout({
      courts: [
        { id: 1, name: 'Court 1' },
        { id: 2, name: 'Court 2' },
      ],
      matchesByCourtId: { 1: [matches[1], matches[2]], 2: [matches[3], matches[4], matches[5]] },
      tournamentStartTime: START,
      defaultBreakMinutes: 10,
    });

    const preview = computeConflictPreview({
      stages: stagesWith(matches),
      layout,
      selection: { kind: 'tray-match-selected', matchId: 1 },
    });

    expect([...preview.insertionLines]).toContain(insertionLineKey(1, 0));
    expect([...preview.insertionLines]).not.toContain(insertionLineKey(1, 2));
  });

  it('flags swap targets that would put the selected match into a conflicting slot', () => {
    const matches = [
      match({ id: 1, courtId: null, startMinutes: null, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 1, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 2, startMinutes: 0, input1: 10, input2: 30 }),
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
      match({ id: 1, courtId: 1, startMinutes: 0, input1: 10, input2: 20 }),
      match({ id: 2, courtId: 2, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 3, startMinutes: 0, input1: 10, input2: 30 }),
      match({ id: 4, courtId: 2, startMinutes: PACKED_SLOT_MINUTES, input1: 60, input2: 70 }),
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

  it('flags swap targets when the other swapped match conflicts in the selected slot', () => {
    const matches = [
      match({ id: 1, courtId: 1, startMinutes: 0, input1: 100, input2: 101, durationMinutes: 20 }),
      match({ id: 2, courtId: 2, startMinutes: 0, input1: 200, input2: 201, durationMinutes: 20 }),
      match({ id: 3, courtId: 2, startMinutes: 30, input1: 202, input2: 203, durationMinutes: 20 }),
      match({ id: 4, courtId: 2, startMinutes: 60, input1: 10, input2: 11, durationMinutes: 20 }),
      match({ id: 5, courtId: 3, startMinutes: 0, input1: 10, input2: 12, durationMinutes: 20 }),
    ];
    const layout = computeScheduleLayout({
      courts: [
        { id: 1, name: 'Court 1' },
        { id: 2, name: 'Court 2' },
        { id: 3, name: 'Court 3' },
      ],
      matchesByCourtId: {
        1: [matches[0]],
        2: [matches[1], matches[2], matches[3]],
        3: [matches[4]],
      },
      tournamentStartTime: START,
      defaultBreakMinutes: 10,
    });

    const preview = computeConflictPreview({
      stages: stagesWith(matches),
      layout,
      selection: {
        kind: 'match-selected',
        match: { matchId: 1, courtId: 1, position: 0 },
      },
    });

    expect([...preview.swapTargets]).toContain(4);
    expect([...preview.swapTargets]).not.toContain(2);
  });
});
