import { describe, expect, it } from 'vitest';

import { Ranking } from '@openapi';

import { Translator } from './types';

import { getRankingTitle } from './rankings';

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
