import { describe, expect, it } from 'vitest';

import type { MatchSet } from '@openapi';
import { SCORE_DRAW_COLOUR, SCORE_LOSE_COLOUR, SCORE_WIN_COLOUR } from '../logic/colors';
import { getSetScoreColors, getSetsWon } from './match_sets';

const SCORE_LIVE_COLOUR = '#74c0fc';
const SCORE_PENDING_COLOUR = '#868e96';

function set(state: MatchSet['state'], score1: number, score2: number): MatchSet {
  return {
    id: 1,
    match_id: 1,
    set_number: 1,
    stage_item_input1_score: score1,
    stage_item_input2_score: score2,
    state,
  };
}

describe('getSetsWon', () => {
  it('returns 0–0 for an empty sets array', () => {
    expect(getSetsWon([])).toEqual({ input1: 0, input2: 0 });
  });

  it('counts COMPLETED sets where input1 won', () => {
    const sets = [set('COMPLETED', 21, 18), set('COMPLETED', 19, 21)];
    expect(getSetsWon(sets)).toEqual({ input1: 1, input2: 1 });
  });

  it('ignores NOT_STARTED sets', () => {
    const sets = [set('COMPLETED', 21, 18), set('NOT_STARTED', 0, 0)];
    expect(getSetsWon(sets)).toEqual({ input1: 1, input2: 0 });
  });

  it('ignores IN_PROGRESS sets', () => {
    const sets = [set('COMPLETED', 21, 18), set('IN_PROGRESS', 10, 8)];
    expect(getSetsWon(sets)).toEqual({ input1: 1, input2: 0 });
  });

  it('does not count COMPLETED draws for either side', () => {
    const sets = [set('COMPLETED', 21, 21)];
    expect(getSetsWon(sets)).toEqual({ input1: 0, input2: 0 });
  });

  it('counts all three completed sets in a 2–1 scenario', () => {
    const sets = [set('COMPLETED', 21, 18), set('COMPLETED', 18, 21), set('COMPLETED', 21, 15)];
    expect(getSetsWon(sets)).toEqual({ input1: 2, input2: 1 });
  });
});

describe('getSetScoreColors', () => {
  it('returns the pending colour for both sides when NOT_STARTED', () => {
    const colors = getSetScoreColors(set('NOT_STARTED', 0, 0));
    expect(colors.s1).toBe(SCORE_PENDING_COLOUR);
    expect(colors.s2).toBe(SCORE_PENDING_COLOUR);
  });

  it('returns the live colour for both sides when IN_PROGRESS', () => {
    const colors = getSetScoreColors(set('IN_PROGRESS', 10, 8));
    expect(colors.s1).toBe(SCORE_LIVE_COLOUR);
    expect(colors.s2).toBe(SCORE_LIVE_COLOUR);
  });

  it('assigns win/loss colours for a COMPLETED set where input1 won', () => {
    const colors = getSetScoreColors(set('COMPLETED', 21, 18));
    expect(colors.s1).toBe(SCORE_WIN_COLOUR);
    expect(colors.s2).toBe(SCORE_LOSE_COLOUR);
  });

  it('assigns win/loss colours for a COMPLETED set where input2 won', () => {
    const colors = getSetScoreColors(set('COMPLETED', 18, 21));
    expect(colors.s1).toBe(SCORE_LOSE_COLOUR);
    expect(colors.s2).toBe(SCORE_WIN_COLOUR);
  });

  it('assigns draw colour for both sides when COMPLETED with equal scores', () => {
    const colors = getSetScoreColors(set('COMPLETED', 21, 21));
    expect(colors.s1).toBe(SCORE_DRAW_COLOUR);
    expect(colors.s2).toBe(SCORE_DRAW_COLOUR);
  });
});
