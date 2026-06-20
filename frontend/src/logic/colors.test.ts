import { describe, expect, it } from 'vitest';

import type { LevelResponse, StageItemWithRounds, StageWithStageItems } from '@openapi';
import {
  computeStageItemColours,
  levelColour,
  levelHue,
  levelSwatchColour,
  SCORE_DRAW_COLOUR,
  SCORE_LOSE_COLOUR,
  SCORE_WIN_COLOUR,
  scoreColour,
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

/** Pull the lightness out of an `oklch(<l> <c> <h>)` string. */
function oklchLightness(colour: string): number {
  const match = colour.match(/oklch\(([\d.]+) /);
  if (match == null) throw new Error(`not an oklch colour: ${colour}`);
  return Number(match[1]);
}

// ── Colour-vision-deficiency (CVD) simulation, so the tests can assert what the
// header promises: every level stays distinguishable for deuter-/protanopes. The
// maths is self-contained (no deps): OKLCH → linear sRGB → Machado-2009 dichromat
// simulation → CIELab, then ΔE76 between the simulated colours. ────────────────

type RGB = [number, number, number];
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

/** OKLCH string → linear sRGB (Björn Ottosson's OKLab matrices). */
function oklchToLinearRGB(colour: string): RGB {
  const match = colour.match(/oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)/);
  if (match == null) throw new Error(`not an oklch colour: ${colour}`);
  const [L, C, h] = [Number(match[1]), Number(match[2]), (Number(match[3]) * Math.PI) / 180];
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

/** Machado-2009 severity-1.0 dichromat matrices, applied in linear sRGB. */
const DEUTERANOPIA = [
  0.367322, 0.860646, -0.227968, 0.280085, 0.672501, 0.047413, -0.01182, 0.04294, 0.968881,
];
const PROTANOPIA = [
  0.152286, 1.052583, -0.204868, 0.114503, 0.786281, 0.099216, -0.003882, -0.048116, 1.051998,
];
const NORMAL_VISION = [1, 0, 0, 0, 1, 0, 0, 0, 1];

function applyMatrix(m: number[], [r, g, b]: RGB): RGB {
  return [
    m[0] * r + m[1] * g + m[2] * b,
    m[3] * r + m[4] * g + m[5] * b,
    m[6] * r + m[7] * g + m[8] * b,
  ];
}

/** Simulated colour as CIELab (D65), for a perceptual ΔE comparison. */
function labUnderVision(colour: string, vision: number[]): [number, number, number] {
  const [r, g, b] = applyMatrix(vision, oklchToLinearRGB(colour).map(clamp01) as RGB).map(clamp01);
  const X = 0.4124 * r + 0.3576 * g + 0.1805 * b;
  const Y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const Z = 0.0193 * r + 0.1192 * g + 0.9505 * b;
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const [fx, fy, fz] = [f(X / 0.95047), f(Y), f(Z / 1.08883)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function deltaE76(a: number[], b: number[]): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/** Smallest pairwise ΔE76 between N level colours, as seen under `vision`. */
function minLevelSeparation(count: number, vision: number[]): number {
  const levels = Array.from({ length: count }, (_, i) => level(i + 1, `L${i}`, i));
  const labs = levels.map((l) => labUnderVision(levelColour(l.id, levels), vision));
  let min = Infinity;
  for (let i = 0; i < labs.length; i += 1) {
    for (let j = i + 1; j < labs.length; j += 1) {
      min = Math.min(min, deltaE76(labs[i], labs[j]));
    }
  }
  return min;
}

describe('levelColour / levelHue (colourblind-safe palette)', () => {
  it('orders by position, not array order, so a level’s colour is stable', () => {
    const ordered = [level(1, 'A', 0), level(2, 'B', 1)];
    const shuffled = [level(2, 'B', 1), level(1, 'A', 0)];
    expect(levelColour(1, ordered)).toBe(levelColour(1, shuffled));
    expect(levelColour(2, ordered)).toBe(levelColour(2, shuffled));
    expect(levelHue(1, ordered)).toBe(levelHue(1, shuffled));
  });

  it('draws the first level from the palette anchor (blue, 250°)', () => {
    const levels = [level(1, 'A', 0)];
    expect(levelHue(1, levels)).toBeCloseTo(250);
    expect(levelColour(1, levels)).toBe('oklch(0.500 0.130 250.0)');
  });

  it('keeps levelColour and levelHue on the same hue', () => {
    const levels = [level(1, 'A', 0), level(2, 'B', 1), level(3, 'C', 2)];
    for (const l of levels) {
      expect(levelColour(l.id, levels)).toMatch(/^oklch\(/);
      expect(oklchHue(levelColour(l.id, levels))).toBeCloseTo(levelHue(l.id, levels));
    }
  });

  it('varies lightness between consecutive levels — the cue every CVD type keeps', () => {
    const levels = Array.from({ length: 5 }, (_, i) => level(i + 1, `L${i}`, i));
    const lightnesses = levels.map((l) => oklchLightness(levelColour(l.id, levels)));
    for (let i = 1; i < lightnesses.length; i += 1) {
      expect(Math.abs(lightnesses[i] - lightnesses[i - 1])).toBeGreaterThan(0.04);
    }
  });

  it('falls back to the even hue spread past the palette length', () => {
    // Nine levels: the first seven come from the palette, the last two land on the
    // even-spread fallback at the fixed level lightness (0.55).
    const levels = Array.from({ length: 9 }, (_, i) => level(i + 1, `L${i}`, i));
    expect(oklchLightness(levelColour(8, levels))).toBeCloseTo(0.55);
    expect(oklchLightness(levelColour(9, levels))).toBeCloseTo(0.55);
  });

  it('keeps every level distinguishable under deuteranopia and protanopia', () => {
    for (const count of [3, 5, 7]) {
      expect(minLevelSeparation(count, DEUTERANOPIA)).toBeGreaterThan(12);
      expect(minLevelSeparation(count, PROTANOPIA)).toBeGreaterThan(12);
    }
  });

  it('stays clearly distinct for normal colour vision', () => {
    expect(minLevelSeparation(5, NORMAL_VISION)).toBeGreaterThan(20);
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

describe('scoreColour', () => {
  it('maps higher / lower / equal scores to win / loss / draw', () => {
    expect(scoreColour(2, 1)).toBe(SCORE_WIN_COLOUR);
    expect(scoreColour(1, 2)).toBe(SCORE_LOSE_COLOUR);
    expect(scoreColour(1, 1)).toBe(SCORE_DRAW_COLOUR);
  });

  it('uses a colourblind-safe win/loss pair, not a pure red/green one', () => {
    // The three outcomes must be mutually distinct…
    const colours = [SCORE_WIN_COLOUR, SCORE_LOSE_COLOUR, SCORE_DRAW_COLOUR];
    expect(new Set(colours).size).toBe(3);
    // …and win/loss are the Okabe-Ito bluish-green / vermillion pair, chosen to
    // stay apart under red–green colour-vision deficiency.
    expect(SCORE_WIN_COLOUR).toBe('#009e73');
    expect(SCORE_LOSE_COLOUR).toBe('#d55e00');
  });
});
