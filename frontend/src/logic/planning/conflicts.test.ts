import { describe, expect, it } from 'vitest';

import { ConflictInput, ConflictMatch, ConflictStage, computeConflictFlags } from './conflicts';

// A fixed tournament start; all match times are expressed as minute offsets from it.
const START = '2026-06-10T09:00:00.000Z';

function minutesAfterStart(minutes: number): string {
  return new Date(new Date(START).getTime() + minutes * 60_000).toISOString();
}

let nextInputId = 1;

/** A resolved (team-backed) playing/referee slot. */
function teamInput(teamId: number, id: number = nextInputId++): ConflictInput {
  return { id, team_id: teamId, winner_from_stage_item_id: null };
}

/** A placeholder ("winner of …") slot with no resolved team yet. */
function tentativeInput(
  winnerFromStageItemId: number | null = null,
  id: number = nextInputId++
): ConflictInput {
  return { id, team_id: null, winner_from_stage_item_id: winnerFromStageItemId };
}

function makeMatch({
  id,
  startMinutes,
  durationMinutes = 90,
  courtId = null,
  input1 = null,
  input2 = null,
  referee = null,
  input1WinnerFromMatchId = null,
  input2WinnerFromMatchId = null,
}: {
  id: number;
  startMinutes: number | null;
  durationMinutes?: number;
  courtId?: number | null;
  input1?: ConflictInput | null;
  input2?: ConflictInput | null;
  referee?: ConflictInput | null;
  input1WinnerFromMatchId?: number | null;
  input2WinnerFromMatchId?: number | null;
}): ConflictMatch {
  return {
    id,
    start_time: startMinutes == null ? null : minutesAfterStart(startMinutes),
    duration_minutes: durationMinutes,
    court_id: courtId,
    stage_item_input1: input1,
    stage_item_input2: input2,
    stage_item_input1_id: input1?.id ?? null,
    stage_item_input2_id: input2?.id ?? null,
    stage_item_input1_winner_from_match_id: input1WinnerFromMatchId,
    stage_item_input2_winner_from_match_id: input2WinnerFromMatchId,
    referee_stage_item_input_id: referee?.id ?? null,
    referee,
  };
}

function makeRound(id: number, matches: ConflictMatch[]) {
  return { id, matches };
}

function makeStageItem({
  id = -10,
  type = 'SINGLE_ELIMINATION' as ConflictStage['stage_items'][number]['type'],
  inputs = [] as ConflictInput[],
  rounds,
}: {
  id?: number;
  type?: ConflictStage['stage_items'][number]['type'];
  inputs?: ConflictInput[];
  rounds: ReturnType<typeof makeRound>[];
}) {
  return { id, type, inputs, rounds };
}

function stageOf(stageItems: ReturnType<typeof makeStageItem>[]): ConflictStage {
  return { stage_items: stageItems };
}

/** Single stage item, single round, two definitive matches. */
function twoMatchStage(match1: ConflictMatch, match2: ConflictMatch): ConflictStage {
  return stageOf([makeStageItem({ rounds: [makeRound(-3, [match1, match2])] })]);
}

// ---------------------------------------------------------------------------
// Team double-booking (stage_item_input conflicts)
// ---------------------------------------------------------------------------

describe('computeConflictFlags — team double-booking', () => {
  it('flags both matches on their shared input side for identical start times', () => {
    // Same team -1 plays input1 of both matches, both starting at minute 0.
    const team1a = teamInput(-1);
    const team1b = teamInput(-1);
    const match1 = makeMatch({ id: -1, startMinutes: 0, input1: team1a, input2: teamInput(-2) });
    const match2 = makeMatch({ id: -2, startMinutes: 0, input1: team1b, input2: teamInput(-4) });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0);

    expect(flags.get(-1)!.stage_item_input1_conflict).toBe(true);
    expect(flags.get(-1)!.stage_item_input2_conflict).toBe(false);
    expect(flags.get(-2)!.stage_item_input1_conflict).toBe(true);
    expect(flags.get(-2)!.stage_item_input2_conflict).toBe(false);
  });

  it('detects partial overlap (issue #64 staggered-start scenario)', () => {
    // match1: 0 → 105, match2: 60 → 165 (45-minute overlap).
    const team = teamInput(-1);
    const match1 = makeMatch({
      id: -1,
      startMinutes: 0,
      durationMinutes: 105,
      input1: team,
      input2: teamInput(-2),
    });
    const match2 = makeMatch({
      id: -2,
      startMinutes: 60,
      durationMinutes: 105,
      input1: teamInput(-1),
      input2: teamInput(-4),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0);

    expect(flags.get(-1)!.stage_item_input1_conflict).toBe(true);
    expect(flags.get(-2)!.stage_item_input1_conflict).toBe(true);
  });

  it('does not flag matches separated by more than their duration', () => {
    // Each 90 min; a 120-min gap between starts means no overlap.
    const match1 = makeMatch({
      id: -1,
      startMinutes: 0,
      input1: teamInput(-1),
      input2: teamInput(-2),
    });
    const match2 = makeMatch({
      id: -2,
      startMinutes: 120,
      input1: teamInput(-1),
      input2: teamInput(-4),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0);

    expect(flags.get(-1)!.stage_item_input1_conflict).toBe(false);
    expect(flags.get(-2)!.stage_item_input1_conflict).toBe(false);
  });

  it('does not flag back-to-back matches (half-open intervals, end1 == start2)', () => {
    const match1 = makeMatch({
      id: -1,
      startMinutes: 0,
      input1: teamInput(-1),
      input2: teamInput(-2),
    });
    const match2 = makeMatch({
      id: -2,
      startMinutes: 90,
      input1: teamInput(-1),
      input2: teamInput(-4),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0);

    expect(flags.get(-1)!.stage_item_input1_conflict).toBe(false);
    expect(flags.get(-2)!.stage_item_input1_conflict).toBe(false);
  });

  it('resolves double-booking by team_id, not raw input id', () => {
    // The same team -5 occupies input1 of match1 (slot id 1) and input2 of match2 (slot id 99):
    // different slot ids, same team. A raw-id check would miss this; a team-id check flags it.
    const match1 = makeMatch({
      id: -1,
      startMinutes: 0,
      input1: teamInput(-5, 1),
      input2: teamInput(-6, 2),
    });
    const match2 = makeMatch({
      id: -2,
      startMinutes: 0,
      input1: teamInput(-7, 3),
      input2: teamInput(-5, 99),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0);

    expect(flags.get(-1)!.stage_item_input1_conflict).toBe(true);
    expect(flags.get(-1)!.stage_item_input2_conflict).toBe(false);
    expect(flags.get(-2)!.stage_item_input2_conflict).toBe(true);
    expect(flags.get(-2)!.stage_item_input1_conflict).toBe(false);
  });

  it('honors the definitive-match restriction (a half-resolved match is not team-double-booked)', () => {
    // match1 is definitive (both inputs resolved); match2 has only input1 resolved.
    // They share team -5 but on different slot ids, so only the team-id path could flag them —
    // and that path is restricted to definitive matches, so neither is flagged.
    const match1 = makeMatch({
      id: -1,
      startMinutes: 0,
      input1: teamInput(-5, 1),
      input2: teamInput(-6, 2),
    });
    const match2 = makeMatch({
      id: -2,
      startMinutes: 0,
      input1: teamInput(-5, 99),
      input2: null,
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0);

    expect(flags.get(-1)!.stage_item_input1_conflict).toBe(false);
    expect(flags.get(-2)!.stage_item_input1_conflict).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Winner-of precedence
// ---------------------------------------------------------------------------

describe('computeConflictFlags — winner-of precedence', () => {
  it('flags a match starting before one of its winner-of feeders ends, on both sides', () => {
    // Feeders run 0 → 90; the final starts at 30 while both are still running.
    const feeder1 = makeMatch({
      id: -1,
      startMinutes: 0,
      input1: teamInput(-1),
      input2: teamInput(-2),
    });
    const feeder2 = makeMatch({
      id: -2,
      startMinutes: 0,
      input1: teamInput(-3),
      input2: teamInput(-4),
    });
    const final = makeMatch({
      id: -3,
      startMinutes: 30,
      input1WinnerFromMatchId: -1,
      input2WinnerFromMatchId: -2,
    });
    const stage = stageOf([
      makeStageItem({
        rounds: [makeRound(-3, [feeder1, feeder2]), makeRound(-2, [final])],
      }),
    ]);

    const flags = computeConflictFlags([stage], 5);

    expect(flags.get(-3)!.precedence_conflict).toBe(true);
    expect(flags.get(-1)!.feeder_precedence_conflict).toBe(true);
    expect(flags.get(-2)!.feeder_precedence_conflict).toBe(true);
  });

  it('does not flag a winner-of feeder that finishes before its dependent starts', () => {
    // Feeders run 0 → 90; the final starts at 90 (back-to-back).
    const feeder1 = makeMatch({
      id: -1,
      startMinutes: 0,
      input1: teamInput(-1),
      input2: teamInput(-2),
    });
    const feeder2 = makeMatch({
      id: -2,
      startMinutes: 0,
      input1: teamInput(-3),
      input2: teamInput(-4),
    });
    const final = makeMatch({
      id: -3,
      startMinutes: 90,
      input1WinnerFromMatchId: -1,
      input2WinnerFromMatchId: -2,
    });
    const stage = stageOf([
      makeStageItem({
        rounds: [makeRound(-3, [feeder1, feeder2]), makeRound(-2, [final])],
      }),
    ]);

    const flags = computeConflictFlags([stage], 5);

    expect(flags.get(-3)!.precedence_conflict).toBe(false);
    expect(flags.get(-1)!.feeder_precedence_conflict).toBe(false);
    expect(flags.get(-2)!.feeder_precedence_conflict).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Cross-stage precedence (winner_from_stage_item_id)
// ---------------------------------------------------------------------------

describe('computeConflictFlags — cross-stage precedence', () => {
  const SOURCE_STAGE_ITEM_ID = -1;
  const TARGET_STAGE_ITEM_ID = -2;

  function crossStage(targetStartMinutes: number): ConflictStage {
    // Source group: match1 0 → 10, match2 10 → 20 (group ends at minute 20).
    const sourceMatch1 = makeMatch({
      id: -1,
      startMinutes: 0,
      durationMinutes: 10,
      input1: teamInput(-1),
      input2: teamInput(-2),
    });
    const sourceMatch2 = makeMatch({
      id: -2,
      startMinutes: 10,
      durationMinutes: 10,
      input1: teamInput(-3),
      input2: teamInput(-4),
    });
    const sourceItem = makeStageItem({
      id: SOURCE_STAGE_ITEM_ID,
      rounds: [makeRound(-3, [sourceMatch1, sourceMatch2])],
    });

    const dependentInput = tentativeInput(SOURCE_STAGE_ITEM_ID);
    const targetMatch = makeMatch({
      id: -3,
      startMinutes: targetStartMinutes,
      durationMinutes: 10,
      input1: dependentInput,
      input2: teamInput(-2),
    });
    const targetItem = makeStageItem({
      id: TARGET_STAGE_ITEM_ID,
      inputs: [dependentInput],
      rounds: [makeRound(-4, [targetMatch])],
    });

    return stageOf([sourceItem, targetItem]);
  }

  it('flags a dependent match starting before the feeding group has finished', () => {
    // Target starts at minute 15, before the source group's last match ends (minute 20).
    const flags = computeConflictFlags([crossStage(15)], 5);

    expect(flags.get(-3)!.precedence_conflict).toBe(true);
    // source match1 (0 → 10) finished before the target started, so it is not flagged.
    expect(flags.get(-1)!.feeder_precedence_conflict).toBe(false);
    // source match2 (10 → 20) is still running when the target starts at 15, so it is flagged.
    expect(flags.get(-2)!.feeder_precedence_conflict).toBe(true);
  });

  it('does not flag when the feeding group fully finishes before the dependent starts', () => {
    // Target starts at minute 20, exactly when the source group ends (back-to-back).
    const flags = computeConflictFlags([crossStage(20)], 5);

    expect(flags.get(-3)!.precedence_conflict).toBe(false);
    expect(flags.get(-1)!.feeder_precedence_conflict).toBe(false);
    expect(flags.get(-2)!.feeder_precedence_conflict).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Short break
// ---------------------------------------------------------------------------

describe('computeConflictFlags — short break', () => {
  it('flags only the later match when a court gap is shorter than the default break', () => {
    // Both on court -1: match1 0 → 10, match2 starts at 12 (2-min gap < 5-min default).
    const court = -1;
    const match1 = makeMatch({
      id: -1,
      startMinutes: 0,
      durationMinutes: 10,
      courtId: court,
      input1: teamInput(-1),
      input2: teamInput(-2),
    });
    const match2 = makeMatch({
      id: -2,
      startMinutes: 12,
      durationMinutes: 10,
      courtId: court,
      input1: teamInput(-3),
      input2: teamInput(-4),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 5);

    expect(flags.get(-1)!.short_break_conflict).toBe(false);
    expect(flags.get(-2)!.short_break_conflict).toBe(true);
  });

  it('does not flag a court gap at least as long as the default break', () => {
    const court = -1;
    const match1 = makeMatch({
      id: -1,
      startMinutes: 0,
      durationMinutes: 10,
      courtId: court,
      input1: teamInput(-1),
      input2: teamInput(-2),
    });
    const match2 = makeMatch({
      id: -2,
      startMinutes: 15,
      durationMinutes: 10,
      courtId: court,
      input1: teamInput(-3),
      input2: teamInput(-4),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 5);

    expect(flags.get(-2)!.short_break_conflict).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Referee conflicts (team-backed referee)
// ---------------------------------------------------------------------------

describe('computeConflictFlags — referee', () => {
  it('flags both sides when a team plays and referees in overlapping windows', () => {
    // Team -20 plays input1 of the playing match and referees the other, overlapping match.
    const team20 = teamInput(-20);
    const playingMatch = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: team20,
      input2: teamInput(-21),
    });
    const refereeingMatch = makeMatch({
      id: -21,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -2,
      input1: teamInput(-22),
      input2: teamInput(-23),
      referee: teamInput(-20),
    });

    const flags = computeConflictFlags([twoMatchStage(playingMatch, refereeingMatch)], 0);

    expect(flags.get(-21)!.referee_conflict).toBe(true);
    expect(flags.get(-20)!.stage_item_input1_conflict).toBe(true);
    expect(flags.get(-20)!.stage_item_input2_conflict).toBe(false);
    expect(flags.get(-20)!.referee_conflict).toBe(false);
  });

  it('never flags a free-text referee (no team_id)', () => {
    const playingMatch = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: teamInput(-20),
      input2: teamInput(-21),
    });
    const refereeingMatch = makeMatch({
      id: -21,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -2,
      input1: teamInput(-22),
      input2: teamInput(-23),
      referee: null,
    });

    const flags = computeConflictFlags([twoMatchStage(playingMatch, refereeingMatch)], 0);

    expect(flags.get(-21)!.referee_conflict).toBe(false);
    expect(flags.get(-20)!.stage_item_input1_conflict).toBe(false);
  });

  it('does not flag non-overlapping playing and refereeing windows', () => {
    const playingMatch = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: teamInput(-20),
      input2: teamInput(-21),
    });
    const refereeingMatch = makeMatch({
      id: -21,
      startMinutes: 120,
      durationMinutes: 60,
      courtId: -2,
      input1: teamInput(-22),
      input2: teamInput(-23),
      referee: teamInput(-20),
    });

    const flags = computeConflictFlags([twoMatchStage(playingMatch, refereeingMatch)], 0);

    expect(flags.get(-21)!.referee_conflict).toBe(false);
    expect(flags.get(-20)!.stage_item_input1_conflict).toBe(false);
  });

  it('flags both matches when a team referees two overlapping matches', () => {
    const team20 = teamInput(-20);
    const refMatch1 = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: teamInput(-21),
      input2: teamInput(-22),
      referee: team20,
    });
    const refMatch2 = makeMatch({
      id: -21,
      startMinutes: 30,
      durationMinutes: 60,
      courtId: -2,
      input1: teamInput(-21),
      input2: teamInput(-23),
      referee: teamInput(-20),
    });

    const flags = computeConflictFlags([twoMatchStage(refMatch1, refMatch2)], 0);

    expect(flags.get(-20)!.referee_conflict).toBe(true);
    expect(flags.get(-21)!.referee_conflict).toBe(true);
  });

  it('does not flag a team refereeing two non-overlapping matches', () => {
    const refMatch1 = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: teamInput(-21),
      input2: teamInput(-22),
      referee: teamInput(-20),
    });
    const refMatch2 = makeMatch({
      id: -21,
      startMinutes: 120,
      durationMinutes: 60,
      courtId: -2,
      input1: teamInput(-21),
      input2: teamInput(-23),
      referee: teamInput(-20),
    });

    const flags = computeConflictFlags([twoMatchStage(refMatch1, refMatch2)], 0);

    expect(flags.get(-20)!.referee_conflict).toBe(false);
    expect(flags.get(-21)!.referee_conflict).toBe(false);
  });

  it('flags a team that plays and referees the same match', () => {
    const team20 = teamInput(-20);
    const match = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: team20,
      input2: teamInput(-21),
      referee: teamInput(-20),
    });
    const stage = stageOf([makeStageItem({ rounds: [makeRound(-10, [match])] })]);

    const flags = computeConflictFlags([stage], 0);

    expect(flags.get(-20)!.referee_conflict).toBe(true);
    expect(flags.get(-20)!.stage_item_input1_conflict).toBe(true);
    expect(flags.get(-20)!.stage_item_input2_conflict).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Placeholder (tentative/empty) slot conflicts (issue #132, slot-id based)
// ---------------------------------------------------------------------------

describe('computeConflictFlags — placeholder slot overlap', () => {
  it('flags a tentative slot that referees one match and plays in an overlapping one', () => {
    // Inputs [A, B, C(tentative), D]: match1 is A vs B refereed by C; match2 is C vs D overlapping.
    const tentativeC = tentativeInput(null, -30);
    const refereeMatch = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: teamInput(-20),
      input2: teamInput(-21),
      referee: tentativeC,
    });
    const playingMatch = makeMatch({
      id: -21,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -2,
      input1: tentativeInput(null, -30),
      input2: teamInput(-23),
    });

    const flags = computeConflictFlags([twoMatchStage(refereeMatch, playingMatch)], 0);

    expect(flags.get(-20)!.referee_conflict).toBe(true);
    expect(flags.get(-21)!.stage_item_input1_conflict).toBe(true);
    expect(flags.get(-21)!.stage_item_input2_conflict).toBe(false);
    expect(flags.get(-21)!.referee_conflict).toBe(false);
  });

  it('flags a tentative slot refereeing two overlapping matches', () => {
    const refMatch1 = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: teamInput(-20),
      input2: teamInput(-21),
      referee: tentativeInput(null, -30),
    });
    const refMatch2 = makeMatch({
      id: -21,
      startMinutes: 30,
      durationMinutes: 60,
      courtId: -2,
      input1: teamInput(-22),
      input2: teamInput(-23),
      referee: tentativeInput(null, -30),
    });

    const flags = computeConflictFlags([twoMatchStage(refMatch1, refMatch2)], 0);

    expect(flags.get(-20)!.referee_conflict).toBe(true);
    expect(flags.get(-21)!.referee_conflict).toBe(true);
  });

  it('flags two overlapping matches that share the same placeholder playing slot', () => {
    const match1 = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: tentativeInput(null, -30),
      input2: teamInput(-21),
    });
    const match2 = makeMatch({
      id: -21,
      startMinutes: 30,
      durationMinutes: 60,
      courtId: -2,
      input1: tentativeInput(null, -30),
      input2: teamInput(-23),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0);

    expect(flags.get(-20)!.stage_item_input1_conflict).toBe(true);
    expect(flags.get(-21)!.stage_item_input1_conflict).toBe(true);
    expect(flags.get(-20)!.stage_item_input2_conflict).toBe(false);
    expect(flags.get(-21)!.stage_item_input2_conflict).toBe(false);
  });

  it('does not flag the same placeholder playing slot across non-overlapping matches', () => {
    const match1 = makeMatch({
      id: -20,
      startMinutes: 0,
      durationMinutes: 60,
      courtId: -1,
      input1: tentativeInput(null, -30),
      input2: teamInput(-21),
    });
    const match2 = makeMatch({
      id: -21,
      startMinutes: 120,
      durationMinutes: 60,
      courtId: -2,
      input1: tentativeInput(null, -30),
      input2: teamInput(-23),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0);

    expect(flags.get(-20)!.stage_item_input1_conflict).toBe(false);
    expect(flags.get(-21)!.stage_item_input1_conflict).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Round order conflicts
// ---------------------------------------------------------------------------

describe('computeConflictFlags — round order', () => {
  function twoRoundStage(
    round1Start: number | null,
    round2Start: number | null,
    type: ConflictStage['stage_items'][number]['type'] = 'SINGLE_ELIMINATION'
  ): ConflictStage {
    // Round 1 has the lower id so it sorts first, mirroring DB insertion order.
    const r1Match = makeMatch({
      id: -41,
      startMinutes: round1Start,
      durationMinutes: 60,
      courtId: -1,
      input1: teamInput(-20),
      input2: teamInput(-21),
    });
    const r2Match = makeMatch({
      id: -40,
      startMinutes: round2Start,
      durationMinutes: 60,
      courtId: -2,
      input1: teamInput(-22),
      input2: teamInput(-23),
    });
    return stageOf([
      makeStageItem({
        id: -40,
        type,
        rounds: [makeRound(-41, [r1Match]), makeRound(-40, [r2Match])],
      }),
    ]);
  }

  it('flags a round-2 match starting before round 1 ends', () => {
    // Round 1: 0 → 60; round 2 starts at 30.
    const flags = computeConflictFlags([twoRoundStage(0, 30)], 0);

    expect(flags.get(-41)!.round_order_conflict).toBe(false);
    expect(flags.get(-40)!.round_order_conflict).toBe(true);
  });

  it('does not flag a round-2 match starting after round 1 ends', () => {
    const flags = computeConflictFlags([twoRoundStage(0, 90)], 0);

    expect(flags.get(-40)!.round_order_conflict).toBe(false);
  });

  it('does not flag back-to-back rounds (round 2 starts exactly when round 1 ends)', () => {
    const flags = computeConflictFlags([twoRoundStage(0, 60)], 0);

    expect(flags.get(-40)!.round_order_conflict).toBe(false);
  });

  it('skips rounds with no scheduled matches', () => {
    const flags = computeConflictFlags([twoRoundStage(null, 0)], 0);

    expect(flags.get(-40)!.round_order_conflict).toBe(false);
  });

  it('never flags round-robin stage items', () => {
    const flags = computeConflictFlags([twoRoundStage(0, 30, 'ROUND_ROBIN')], 0);

    expect(flags.get(-41)!.round_order_conflict).toBe(false);
    expect(flags.get(-40)!.round_order_conflict).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// "Matches of interest" filter
// ---------------------------------------------------------------------------

describe('computeConflictFlags — matches of interest', () => {
  it('returns a flag entry for every match when passed "all"', () => {
    const match1 = makeMatch({
      id: -1,
      startMinutes: 0,
      input1: teamInput(-1),
      input2: teamInput(-2),
    });
    const match2 = makeMatch({
      id: -2,
      startMinutes: 0,
      input1: teamInput(-1),
      input2: teamInput(-4),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0, 'all');

    expect(new Set(flags.keys())).toEqual(new Set([-1, -2]));
  });

  it('restricts the returned map to the matches of interest', () => {
    const match1 = makeMatch({
      id: -1,
      startMinutes: 0,
      input1: teamInput(-1),
      input2: teamInput(-2),
    });
    const match2 = makeMatch({
      id: -2,
      startMinutes: 0,
      input1: teamInput(-1),
      input2: teamInput(-4),
    });

    const flags = computeConflictFlags([twoMatchStage(match1, match2)], 0, new Set([-1]));

    expect(new Set(flags.keys())).toEqual(new Set([-1]));
    // The conflict is still detected using the full schedule, only the output is filtered.
    expect(flags.get(-1)!.stage_item_input1_conflict).toBe(true);
  });
});
