import { describe, expect, it } from 'vitest';

import { Ranking } from '@openapi';

import { Translator } from './types';

import { getPlayAllSetsDefault, getRankingTitle, isBestOfNMode } from './rankings';

const t = ((key: string) => (key === 'ranking_title' ? 'Ranking' : key)) as unknown as Translator;

function makeRanking(overrides: Partial<Ranking>): Ranking {
  return {
    id: 1,
    created: '2026-01-01T00:00:00Z',
    tournament_id: 1,
    position: 0,
    name: '',
    scoring_type: 'MATCH_POINTS',
    num_sets: 1,
    max_points: 21,
    last_set_max_points: null,
    two_point_advantage: true,
    level_id: null,
    side_switch_every_n_points: null,
    match_points: null,
    set_points_with_bonus: null,
    ...overrides,
  } as Ranking;
}

describe('getPlayAllSetsDefault', () => {
  // Mirrors the backend's per-scoring-type creation defaults: only "set points" scoring
  // gives every set intrinsic value, so only there do all sets play out by default.
  it('defaults to best-of behaviour for MATCH_POINTS', () => {
    expect(getPlayAllSetsDefault('MATCH_POINTS')).toBe(false);
  });

  it('defaults to playing out all sets for SET_POINTS', () => {
    expect(getPlayAllSetsDefault('SET_POINTS')).toBe(true);
  });

  it('defaults to best-of behaviour for SET_POINTS_WITH_MATCH_BONUS', () => {
    expect(getPlayAllSetsDefault('SET_POINTS_WITH_MATCH_BONUS')).toBe(false);
  });
});

describe('isBestOfNMode', () => {
  it('is inactive when play_all_sets is on, regardless of num_sets', () => {
    expect(isBestOfNMode(true, 1)).toBe(false);
    expect(isBestOfNMode(true, 3)).toBe(false);
  });

  it('is inactive for a single-set ranking, regardless of play_all_sets', () => {
    expect(isBestOfNMode(false, 1)).toBe(false);
    expect(isBestOfNMode(true, 1)).toBe(false);
  });

  it('is active when play_all_sets is off and num_sets is greater than one', () => {
    expect(isBestOfNMode(false, 3)).toBe(true);
    expect(isBestOfNMode(false, 2)).toBe(true);
  });
});

describe('getRankingTitle', () => {
  it('uses the custom name when one is set', () => {
    const ranking = makeRanking({ name: 'Fair play', position: 2 });
    expect(getRankingTitle(ranking, t)).toBe('Fair play');
  });

  it('falls back to "Ranking <position + 1>" when the name is empty', () => {
    const ranking = makeRanking({ name: '', position: 1 });
    expect(getRankingTitle(ranking, t)).toBe('Ranking 2');
  });

  it('falls back when the name is only whitespace', () => {
    const ranking = makeRanking({ name: '   ', position: 0 });
    expect(getRankingTitle(ranking, t)).toBe('Ranking 1');
  });
});
