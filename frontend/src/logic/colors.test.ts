import { describe, expect, it } from 'vitest';

import type { LevelResponse, StageItemWithRounds, StageWithStageItems } from '@openapi';
import {
  computeStageItemColours,
  levelColour,
  levelHue,
  levelSwatchColour,
  stringToColour,
} from './colors';

function level(id: number, name: string, position: number): LevelResponse {
  return { id, name, position };
}

function stageItem(id: number, name: string): StageItemWithRounds {
  return { id, name } as StageItemWithRounds;
}

function stage(
  id: number,
  levelId: number | null,
  stageItems: StageItemWithRounds[]
): StageWithStageItems {
  return {
    id,
    name: `Stage ${id}`,
    level_id: levelId,
    stage_items: stageItems,
  } as StageWithStageItems;
}

/** Pull the hue out of an `oklch(<l> <c> <h>)` string. */
function oklchHue(colour: string): number {
  const match = colour.match(/oklch\([\d.]+ [\d.]+ ([\d.]+)\)/);
  if (match == null) throw new Error(`not an oklch colour: ${colour}`);
  return Number(match[1]);
}

/** Pull the lightness out of the *light-mode* stop of a `light-dark(...)` fill. */
function lightModeLightness(fill: string): number {
  const match = fill.match(/light-dark\(oklch\(([\d.]+) /);
  if (match == null) throw new Error(`not a light-dark fill: ${fill}`);
  return Number(match[1]);
}

/** Shortest distance between two hues around the 360° wheel. */
function hueDistance(a: number, b: number): number {
  const delta = Math.abs(a - b) % 360;
  return Math.min(delta, 360 - delta);
}

describe('levelHue', () => {
  it('spreads levels evenly around the wheel by position', () => {
    const levels = [level(1, 'A', 0), level(2, 'B', 1), level(3, 'C', 2)];
    const hues = levels.map((l) => levelHue(l.id, levels));
    // Three levels → 120° apart, the maximal separation three points allow.
    expect(hueDistance(hues[0], hues[1])).toBeCloseTo(120);
    expect(hueDistance(hues[1], hues[2])).toBeCloseTo(120);
    expect(hueDistance(hues[0], hues[2])).toBeCloseTo(120);
  });

  it('orders by position, not array order, so colour is stable', () => {
    const ordered = [level(1, 'A', 0), level(2, 'B', 1)];
    const shuffled = [level(2, 'B', 1), level(1, 'A', 0)];
    expect(levelHue(1, ordered)).toBe(levelHue(1, shuffled));
    expect(levelHue(2, ordered)).toBe(levelHue(2, shuffled));
  });
});

describe('levelColour', () => {
  it('returns an oklch colour on the level’s hue', () => {
    const levels = [level(1, 'A', 0), level(2, 'B', 1)];
    expect(levelColour(2, levels)).toMatch(/^oklch\(/);
    expect(oklchHue(levelColour(2, levels))).toBeCloseTo(levelHue(2, levels));
  });
});

describe('computeStageItemColours', () => {
  it('darkens the first stage item of a stage and lightens later ones', () => {
    const colours = computeStageItemColours(
      [stage(1, null, [stageItem(10, 'Group A'), stageItem(11, 'Group B')])],
      []
    );
    // Darkest stage item first → lower light-mode lightness than later items.
    expect(lightModeLightness(colours[10].fill)).toBeLessThan(lightModeLightness(colours[11].fill));
  });

  it('treats a tournament without levels as one hue family on its first stage', () => {
    const colours = computeStageItemColours([stage(1, null, [stageItem(10, 'Group A')])], []);
    expect(colours[10].accent).toMatch(/^oklch\(/);
  });

  it('uses each level’s app-wide hue so the schedule matches the other views', () => {
    const levels = [level(1, 'Beginner', 0), level(2, 'Advanced', 1)];
    const colours = computeStageItemColours(
      [stage(100, 1, [stageItem(10, 'Group A')]), stage(200, 2, [stageItem(20, 'Group A')])],
      levels
    );
    // A single-stage level sits exactly on its base hue.
    expect(oklchHue(colours[10].accent)).toBeCloseTo(levelHue(1, levels));
    expect(oklchHue(colours[20].accent)).toBeCloseTo(levelHue(2, levels));
  });

  it('fans a level’s stages into a tight hue cluster around its base', () => {
    const levels = [level(1, 'Beginner', 0)];
    const colours = computeStageItemColours(
      [stage(100, 1, [stageItem(10, 'Groups')]), stage(101, 1, [stageItem(11, 'Knockout')])],
      levels
    );
    const base = levelHue(1, levels);
    const first = oklchHue(colours[10].accent);
    const second = oklchHue(colours[11].accent);
    expect(first).not.toBe(second);
    // Both stay within the fan half-spread (10°) of the level's base hue.
    expect(hueDistance(first, base)).toBeLessThanOrEqual(10);
    expect(hueDistance(second, base)).toBeLessThanOrEqual(10);
  });

  it('falls back to neutral grey for a stage with no level in a levelled tournament', () => {
    const colours = computeStageItemColours(
      [stage(100, null, [stageItem(10, 'Orphan')])],
      [level(1, 'Beginner', 0)]
    );
    expect(colours[10].fill).toBe('var(--mantine-color-gray-light)');
  });
});

describe('levelSwatchColour', () => {
  it('returns the level’s exact app-wide colour for the legend', () => {
    const levels = [level(1, 'A', 0), level(2, 'B', 1)];
    expect(levelSwatchColour(2, levels)).toBe(levelColour(2, levels));
  });
});

describe('stringToColour', () => {
  it('is deterministic for a given key', () => {
    expect(stringToColour('team-5')).toBe(stringToColour('team-5'));
  });
});
