import { describe, expect, it } from 'vitest';

import { formatDifference } from './standings';

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
