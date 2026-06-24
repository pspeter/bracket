import { describe, expect, it } from 'vitest';

import { computeConflictPreview, insertionLineKey } from './conflict_preview';
import { ConflictMatch, ConflictStage } from './conflicts';
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
  referee = null,
  durationMinutes = 90,
  winnerFromMatch1 = null,
  winnerFromMatch2 = null,
}: {
  id: number;
  courtId: number | null;
  startMinutes: number | null;
  input1: number;
  input2: number;
  referee?: number | null;
  durationMinutes?: number;
  winnerFromMatch1?: number | null;
  winnerFromMatch2?: number | null;
}): ConflictMatch {
  return {
    id,
    court_id: courtId,
    start_time: startMinutes == null ? null : minutesAfterStart(startMinutes),
    duration_minutes: durationMinutes,
    stage_item_input1: null,
    stage_item_input2: null,
    stage_item_input1_id: input1,
    stage_item_input2_id: input2,
    stage_item_input1_winner_from_match_id: winnerFromMatch1,
    stage_item_input2_winner_from_match_id: winnerFromMatch2,
    referee_stage_item_input_id: referee,
    referee: null,
  };
}

function stagesWith(matches: ConflictMatch[]): ConflictStage[] {
  return [
    {
      stage_items: [
        { id: 1, type: 'SINGLE_ELIMINATION', inputs: [], rounds: [{ id: 1, matches }] },
      ],
    },
  ];
}

describe('computeConflictPreview', () => {
  it('flags insertion lines that would create a selected-match team overlap', () => {
    // Match 1 starts at minute 200, so it does not overlap its slot-10 twin (match
    // 4) where it currently sits; inserting it into court 2 reseeds it to minute 0,
    // where it would collide with match 4.
    const matches = [
      match({ id: 1, courtId: 1, startMinutes: 200, input1: 10, input2: 20 }),
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
      tournamentStartTime: START,
      refereesEnabled: true,
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
      tournamentStartTime: START,
      refereesEnabled: true,
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
      tournamentStartTime: START,
      refereesEnabled: true,
    });

    expect([...preview.insertionLines]).toContain(insertionLineKey(1, 0));
    expect([...preview.insertionLines]).not.toContain(insertionLineKey(1, 2));
  });

  it('flags insertion lines that would create a winner-of precedence conflict', () => {
    // Match 2 is fed by match 1's winner. Match 1 plays [0, 90) on court 1. Placed
    // ahead of court 2's existing match, the dependent reseeds to minute 0 and would
    // start before its feeder finishes — a precedence conflict the team-overlap-only
    // preview never saw, since the two share no playing slot.
    const matches = [
      match({ id: 1, courtId: 1, startMinutes: 0, input1: 10, input2: 20 }),
      match({
        id: 2,
        courtId: null,
        startMinutes: null,
        input1: 60,
        input2: 70,
        winnerFromMatch1: 1,
      }),
      match({ id: 3, courtId: 2, startMinutes: 0, input1: 40, input2: 50 }),
    ];
    const layout = computeScheduleLayout({
      courts: [
        { id: 1, name: 'Court 1' },
        { id: 2, name: 'Court 2' },
      ],
      matchesByCourtId: { 1: [matches[0]], 2: [matches[2]] },
      tournamentStartTime: START,
      defaultBreakMinutes: 10,
    });

    const preview = computeConflictPreview({
      stages: stagesWith(matches),
      layout,
      selection: { kind: 'tray-match-selected', matchId: 2 },
      tournamentStartTime: START,
      refereesEnabled: true,
    });

    expect([...preview.insertionLines]).toContain(insertionLineKey(2, 0));
    expect([...preview.insertionLines]).not.toContain(insertionLineKey(2, 1));
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
      tournamentStartTime: START,
      refereesEnabled: true,
    });

    expect([...preview.swapTargets]).toContain(2);
    expect([...preview.swapTargets]).not.toContain(3);
  });

  it('flags scheduled-match swap targets after simulating the traded slots', () => {
    // Match 1 sits at minute 200, clear of its slot-10 twin (match 3 at minute 0).
    // Swapping it into match 2's minute-0 slot would drop it onto match 3.
    const matches = [
      match({ id: 1, courtId: 1, startMinutes: 200, input1: 10, input2: 20 }),
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
      tournamentStartTime: START,
      refereesEnabled: true,
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
      tournamentStartTime: START,
      refereesEnabled: true,
    });

    expect([...preview.swapTargets]).toContain(4);
    expect([...preview.swapTargets]).not.toContain(2);
  });

  it('flags swap targets that would create a short-break conflict', () => {
    // Court 1 packs match 1 [0, 20) then match 3 [30, 50) — a clean 10-minute break.
    // Court 2's match 2 runs 40 minutes. Swapping match 2 into match 1's slot lands a
    // [0, 40) block in front of match 3, leaving a negative break: a short-break
    // conflict between matches that share no playing slot.
    const matches = [
      match({ id: 1, courtId: 1, startMinutes: 0, input1: 10, input2: 20, durationMinutes: 20 }),
      match({ id: 2, courtId: 2, startMinutes: 0, input1: 40, input2: 41, durationMinutes: 40 }),
      match({ id: 3, courtId: 1, startMinutes: 30, input1: 30, input2: 31, durationMinutes: 20 }),
    ];
    const layout = computeScheduleLayout({
      courts: [
        { id: 1, name: 'Court 1' },
        { id: 2, name: 'Court 2' },
      ],
      matchesByCourtId: { 1: [matches[0], matches[2]], 2: [matches[1]] },
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
      tournamentStartTime: START,
      refereesEnabled: true,
    });

    expect([...preview.swapTargets]).toContain(2);
    expect([...preview.swapTargets]).not.toContain(3);
  });

  it('flags a swap target whose slot would double-book the selected match referee', () => {
    // Tray match 1 referees team 60. Swapping it into match 2's slot (court 1, start
    // 0) puts it in the same window as match 3, which plays team 60 on court 2 — a
    // referee conflict the preview must surface even though no playing input is shared.
    const matches = [
      match({ id: 1, courtId: null, startMinutes: null, input1: 10, input2: 20, referee: 60 }),
      match({ id: 2, courtId: 1, startMinutes: 0, input1: 40, input2: 50 }),
      match({ id: 3, courtId: 2, startMinutes: 0, input1: 60, input2: 30 }),
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
      tournamentStartTime: START,
      refereesEnabled: true,
    });

    expect([...preview.swapTargets]).toContain(2);
    expect([...preview.swapTargets]).not.toContain(3);
  });
});
