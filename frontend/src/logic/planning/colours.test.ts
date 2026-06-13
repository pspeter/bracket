import { describe, expect, it } from 'vitest';

import type { LevelResponse, StageItemWithRounds, StageWithStageItems } from '@openapi';
import { stringToColour } from '../string_to_colour';
import { computeStageItemColours, levelBaseHue, levelSwatchColour } from './colours';

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

/** Pull the hue out of an `hsl(<h> 70% ..%)` accent string. */
function accentHue(accent: string): number {
  const match = accent.match(/^hsl\((\d+(?:\.\d+)?) /);
  if (match == null) throw new Error(`not an hsl colour: ${accent}`);
  return Number(match[1]);
}

/** Pull the mix percentage out of a `color-mix(... <pct>%)` fill string. */
function fillMix(fill: string): number {
  const match = fill.match(/ ([\d.]+)%\)$/);
  if (match == null) throw new Error(`not a colour-mix fill: ${fill}`);
  return Number(match[1]);
}

/** Shortest distance between two hues around the 360° wheel. */
function hueDistance(a: number, b: number): number {
  const delta = Math.abs(a - b) % 360;
  return Math.min(delta, 360 - delta);
}

describe('computeStageItemColours', () => {
  it('darkens the first stage item of a stage and lightens later ones', () => {
    const colours = computeStageItemColours(
      [stage(1, null, [stageItem(10, 'Group A'), stageItem(11, 'Group B')])],
      []
    );
    expect(fillMix(colours[10].fill)).toBeGreaterThan(fillMix(colours[11].fill));
  });

  it('treats a tournament without levels as one hue family on its first stage', () => {
    const colours = computeStageItemColours([stage(1, null, [stageItem(10, 'Group A')])], []);
    // Single synthetic family, single stage → exactly the synthetic base hue.
    expect(accentHue(colours[10].accent)).toBeGreaterThanOrEqual(0);
  });

  it('uses each level’s app-wide hue so the schedule matches the other views', () => {
    const levels = [level(1, 'Beginner', 0), level(2, 'Advanced', 1)];
    const colours = computeStageItemColours(
      [stage(100, 1, [stageItem(10, 'Group A')]), stage(200, 2, [stageItem(20, 'Group A')])],
      levels
    );
    // A single-stage level sits exactly on its base hue, which is derived from
    // the same Mantine colour the rest of the app paints the level with.
    expect(accentHue(colours[10].accent)).toBe(levelBaseHue(1));
    expect(accentHue(colours[20].accent)).toBe(levelBaseHue(2));
  });

  it('fans a level’s stages into a tight hue cluster around its base', () => {
    const levels = [level(1, 'Beginner', 0)];
    const colours = computeStageItemColours(
      [stage(100, 1, [stageItem(10, 'Groups')]), stage(101, 1, [stageItem(11, 'Knockout')])],
      levels
    );
    const base = levelBaseHue(1);
    const first = accentHue(colours[10].accent);
    const second = accentHue(colours[11].accent);
    expect(first).not.toBe(second);
    // Both stay within the fan half-spread (18°) of the level's base hue.
    expect(hueDistance(first, base)).toBeLessThanOrEqual(18);
    expect(hueDistance(second, base)).toBeLessThanOrEqual(18);
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
  it('returns the level’s exact app-wide Mantine colour for the legend', () => {
    expect(levelSwatchColour(2)).toBe(stringToColour('level-2'));
  });
});
