import { describe, expect, it } from 'vitest';

import { MatchSet, MatchWithDetails } from '@openapi';

import {
  getDisplayScores,
  getNextMatchOnCourt,
  getScoreTrackingViewState,
  isEndSetDisabled,
  nextScoresAfterAdjust,
} from './score_tracking';

function makeSet(overrides: Partial<MatchSet> & Pick<MatchSet, 'set_number' | 'state'>): MatchSet {
  return {
    id: overrides.set_number,
    match_id: 1,
    stage_item_input1_score: overrides.stage_item_input1_score ?? 0,
    stage_item_input2_score: overrides.stage_item_input2_score ?? 0,
    ...overrides,
  };
}

describe('getScoreTrackingViewState', () => {
  it('returns not_started when all sets are NOT_STARTED', () => {
    const sets = [makeSet({ set_number: 1, state: 'NOT_STARTED' })];
    expect(getScoreTrackingViewState(sets)).toEqual({ kind: 'not_started' });
  });

  it('returns playing with the IN_PROGRESS set', () => {
    const set = makeSet({ set_number: 1, state: 'IN_PROGRESS' });
    const result = getScoreTrackingViewState([set]);
    expect(result).toEqual({ kind: 'playing', set });
  });

  it('returns playing with the second set when first is COMPLETED and second is IN_PROGRESS', () => {
    const set1 = makeSet({ set_number: 1, state: 'COMPLETED' });
    const set2 = makeSet({ set_number: 2, state: 'IN_PROGRESS' });
    const result = getScoreTrackingViewState([set1, set2]);
    expect(result).toEqual({ kind: 'playing', set: set2 });
  });

  it('returns between_sets when there is a completed set and a next not-started set', () => {
    const set1 = makeSet({ set_number: 1, state: 'COMPLETED' });
    const set2 = makeSet({ set_number: 2, state: 'NOT_STARTED' });
    const result = getScoreTrackingViewState([set1, set2]);
    expect(result).toEqual({
      kind: 'between_sets',
      completed: set1,
      next: set2,
      allSets: [set1, set2],
    });
  });

  it('returns between_sets with last completed set when multiple are done', () => {
    const set1 = makeSet({ set_number: 1, state: 'COMPLETED' });
    const set2 = makeSet({ set_number: 2, state: 'COMPLETED' });
    const set3 = makeSet({ set_number: 3, state: 'NOT_STARTED' });
    const result = getScoreTrackingViewState([set1, set2, set3]);
    expect(result).toEqual({
      kind: 'between_sets',
      completed: set2,
      next: set3,
      allSets: [set1, set2, set3],
    });
  });

  it('returns completed when all sets are COMPLETED', () => {
    const sets = [
      makeSet({ set_number: 1, state: 'COMPLETED' }),
      makeSet({ set_number: 2, state: 'COMPLETED' }),
      makeSet({ set_number: 3, state: 'COMPLETED' }),
    ];
    expect(getScoreTrackingViewState(sets)).toEqual({ kind: 'completed' });
  });

  it('returns completed for single set COMPLETED', () => {
    const sets = [makeSet({ set_number: 1, state: 'COMPLETED' })];
    expect(getScoreTrackingViewState(sets)).toEqual({ kind: 'completed' });
  });
});

function makeMatch(
  overrides: Pick<MatchWithDetails, 'id'> &
    Partial<Pick<MatchWithDetails, 'court_id' | 'start_time' | 'state'>>
): MatchWithDetails {
  return {
    court_id: null,
    start_time: null,
    state: 'NOT_STARTED',
    ...overrides,
  } as MatchWithDetails;
}

describe('getNextMatchOnCourt', () => {
  it('returns the next match on the same court by start time', () => {
    const current = makeMatch({ id: 1, court_id: 5, start_time: '2026-07-04T10:00:00Z' });
    const next = makeMatch({ id: 2, court_id: 5, start_time: '2026-07-04T10:30:00Z' });
    const matches = [current, next];
    expect(getNextMatchOnCourt(matches, current)).toBe(next);
  });

  it('ignores matches on other courts', () => {
    const current = makeMatch({ id: 1, court_id: 5, start_time: '2026-07-04T10:00:00Z' });
    const otherCourt = makeMatch({ id: 2, court_id: 6, start_time: '2026-07-04T10:15:00Z' });
    const sameCourt = makeMatch({ id: 3, court_id: 5, start_time: '2026-07-04T10:30:00Z' });
    expect(getNextMatchOnCourt([current, otherCourt, sameCourt], current)).toBe(sameCourt);
  });

  it('skips already-completed matches and returns the next unplayed one', () => {
    const current = makeMatch({ id: 1, court_id: 5, start_time: '2026-07-04T10:00:00Z' });
    const completedNext = makeMatch({
      id: 2,
      court_id: 5,
      start_time: '2026-07-04T10:30:00Z',
      state: 'COMPLETED',
    });
    const unplayed = makeMatch({ id: 3, court_id: 5, start_time: '2026-07-04T11:00:00Z' });
    expect(getNextMatchOnCourt([current, completedNext, unplayed], current)).toBe(unplayed);
  });

  it('returns null when it is the last match on the court', () => {
    const earlier = makeMatch({ id: 1, court_id: 5, start_time: '2026-07-04T10:00:00Z' });
    const current = makeMatch({ id: 2, court_id: 5, start_time: '2026-07-04T10:30:00Z' });
    expect(getNextMatchOnCourt([earlier, current], current)).toBeNull();
  });

  it('returns null when every later match on the court is completed', () => {
    const current = makeMatch({ id: 1, court_id: 5, start_time: '2026-07-04T10:00:00Z' });
    const laterCompleted = makeMatch({
      id: 2,
      court_id: 5,
      start_time: '2026-07-04T10:30:00Z',
      state: 'COMPLETED',
    });
    expect(getNextMatchOnCourt([current, laterCompleted], current)).toBeNull();
  });

  it('returns null when the current match has no court assigned', () => {
    const current = makeMatch({ id: 1, court_id: null, start_time: '2026-07-04T10:00:00Z' });
    const other = makeMatch({ id: 2, court_id: null, start_time: '2026-07-04T10:30:00Z' });
    expect(getNextMatchOnCourt([current, other], current)).toBeNull();
  });

  it('breaks start-time ties by id', () => {
    const current = makeMatch({ id: 5, court_id: 5, start_time: '2026-07-04T10:00:00Z' });
    const sameTimeLowerId = makeMatch({ id: 3, court_id: 5, start_time: '2026-07-04T10:00:00Z' });
    const sameTimeHigherId = makeMatch({ id: 7, court_id: 5, start_time: '2026-07-04T10:00:00Z' });
    expect(getNextMatchOnCourt([current, sameTimeLowerId, sameTimeHigherId], current)).toBe(
      sameTimeHigherId
    );
  });
});

describe('isEndSetDisabled', () => {
  const baseMatch = {
    two_point_advantage: false,
    max_points: 21,
    last_set_max_points: null as number | null,
    num_sets: 3,
  };

  it('is disabled when no score has reached the limit', () => {
    const set = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 20,
      stage_item_input2_score: 15,
    });
    expect(isEndSetDisabled(set, baseMatch, false)).toBe(true);
  });

  it('is enabled when one score reaches limit with no two_point_advantage', () => {
    const set = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 21,
      stage_item_input2_score: 15,
    });
    expect(isEndSetDisabled(set, baseMatch, false)).toBe(false);
  });

  it('is disabled when two_point_advantage=true and margin < 2', () => {
    const set = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 21,
      stage_item_input2_score: 20,
    });
    expect(isEndSetDisabled(set, { ...baseMatch, two_point_advantage: true }, false)).toBe(true);
  });

  it('is enabled when two_point_advantage=true and margin >= 2', () => {
    const set = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 22,
      stage_item_input2_score: 20,
    });
    expect(isEndSetDisabled(set, { ...baseMatch, two_point_advantage: true }, false)).toBe(false);
  });

  it('uses last_set_max_points for the last set', () => {
    const matchWithLastSet = { ...baseMatch, last_set_max_points: 15, num_sets: 3 };
    // score 15-10: reaches last_set limit (15), no two_point_advantage
    const set = makeSet({
      set_number: 3,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 15,
      stage_item_input2_score: 10,
    });
    expect(isEndSetDisabled(set, matchWithLastSet, false)).toBe(false);
  });

  it('uses max_points for non-last sets even when last_set_max_points is set', () => {
    const matchWithLastSet = { ...baseMatch, last_set_max_points: 15, num_sets: 3 };
    // score 15-10 for set 1: does NOT reach max_points (21)
    const set = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 15,
      stage_item_input2_score: 10,
    });
    expect(isEndSetDisabled(set, matchWithLastSet, false)).toBe(true);
  });

  it('respects isSwapped by swapping score slots', () => {
    // With swapped=false: s1=21, s2=15 → enabled (21 >= 21)
    // With swapped=true: s1=15, s2=21 → enabled (21 >= 21, treating input2 as s1)
    const set = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 21,
      stage_item_input2_score: 15,
    });
    expect(isEndSetDisabled(set, baseMatch, false)).toBe(false);
    expect(isEndSetDisabled(set, baseMatch, true)).toBe(false);
  });

  it('is disabled at exact limit with two_point_advantage when tied', () => {
    const set = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 21,
      stage_item_input2_score: 21,
    });
    expect(isEndSetDisabled(set, { ...baseMatch, two_point_advantage: true }, false)).toBe(true);
  });
});

describe('getDisplayScores', () => {
  it('returns scores in original order when not swapped', () => {
    const set = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 11,
      stage_item_input2_score: 7,
    });
    expect(getDisplayScores(set, false)).toEqual({ first: 11, second: 7 });
  });

  it('swaps which score is shown first when isSwapped is true', () => {
    // The team names swap sides too, so the score must move with its team:
    // whichever side now shows input2's team must show input2's score.
    const set = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 11,
      stage_item_input2_score: 7,
    });
    expect(getDisplayScores(set, true)).toEqual({ first: 7, second: 11 });
  });
});

describe('nextScoresAfterAdjust', () => {
  const set = makeSet({
    set_number: 1,
    state: 'IN_PROGRESS',
    stage_item_input1_score: 5,
    stage_item_input2_score: 3,
  });

  it('adjusts input1_score when slot is 1', () => {
    expect(nextScoresAfterAdjust(set, 1, 1)).toEqual({
      stage_item_input1_score: 6,
      stage_item_input2_score: 3,
    });
  });

  it('adjusts input2_score when slot is 2', () => {
    expect(nextScoresAfterAdjust(set, 2, 1)).toEqual({
      stage_item_input1_score: 5,
      stage_item_input2_score: 4,
    });
  });

  it('adjusts the score belonging to the given slot regardless of side switching', () => {
    // The slot passed in is always the team's real (unswapped) slot, since that's
    // what identifies whose score is being changed — a "switch sides" toggle only
    // affects display order, not which slot a team's score lives in.
    expect(nextScoresAfterAdjust(set, 2, -1)).toEqual({
      stage_item_input1_score: 5,
      stage_item_input2_score: 2,
    });
  });

  it('clamps scores at 0', () => {
    const zeroSet = makeSet({
      set_number: 1,
      state: 'IN_PROGRESS',
      stage_item_input1_score: 0,
      stage_item_input2_score: 0,
    });
    expect(nextScoresAfterAdjust(zeroSet, 1, -1)).toEqual({
      stage_item_input1_score: 0,
      stage_item_input2_score: 0,
    });
  });
});
