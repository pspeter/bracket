import { describe, expect, it } from 'vitest';

import type { ScoringType } from '@openapi';

import { formatDifference, getWinsColumnKey } from './standings';

describe('formatDifference', () => {
  it('prefixes positive values with +', () => {
    expect(formatDifference(5)).toBe('+5');
  });

  it('passes through negative values unchanged', () => {
    expect(formatDifference(-3)).toBe('-3');
  });

  it('prefixes zero with +', () => {
    expect(formatDifference(0)).toBe('+0');
  });
});

describe('getWinsColumnKey', () => {
  it('returns matches_won_label for MATCH_POINTS', () => {
    expect(getWinsColumnKey('MATCH_POINTS')).toBe('matches_won_label');
  });

  it('returns sets_won_label for SET_POINTS', () => {
    expect(getWinsColumnKey('SET_POINTS')).toBe('sets_won_label');
  });

  it('returns sets_won_label for SET_POINTS_WITH_MATCH_BONUS', () => {
    expect(getWinsColumnKey('SET_POINTS_WITH_MATCH_BONUS')).toBe('sets_won_label');
  });

  it('defaults to matches_won_label when scoring_type is null', () => {
    expect(getWinsColumnKey(null)).toBe('matches_won_label');
  });
});
