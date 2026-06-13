/**
 * Schedule colour scheme: a match's colour encodes its place in the tournament
 * hierarchy, so the planner reads as grouped at a glance.
 *
 *   level  → hue        (the level's app-wide colour, so it matches other views)
 *   stage  → hue cluster (tight fan of hues around the level's base hue)
 *   item   → shade       (capped-light tint steps, darkest stage item first)
 *
 * The same colour is used in every schedule view (agenda, compact, overview) so
 * a match keeps its identity when zooming. Tints are mixed over a mode-aware
 * surface (`FILL_SURFACE`): white in light mode, a *lifted* dark surface in dark
 * mode. Mixing over the near-black body directly crushed the hue out of the
 * lightest steps in dark mode, so the surface floor is raised just enough to keep
 * the hue legible while the theme's default text colour stays readable on top.
 *
 * The base hue is taken from the same Mantine colour the rest of the app paints a
 * level with (`stringToColour('level-<id>')`), so a level reads as the same hue
 * here as on the stages/levels/teams views. Tournaments without levels collapse
 * to one synthetic family, with stages fanned and items shaded.
 */

import type { LevelResponse, StageWithStageItems } from '@openapi';
import { stringToColour } from '../string_to_colour';

export interface StageItemColour {
  /** Capped-light tint for the card/overview background; identical across views. */
  fill: string;
  /** Saturated hue for the card's left border and the overview status glyph. */
  accent: string;
}

/** Stages without a level in a levelled tournament fall back to neutral grey. */
const NEUTRAL: StageItemColour = {
  fill: 'var(--mantine-color-gray-light)',
  accent: 'var(--mantine-color-gray-filled)',
};

/** Approximate hue (deg) of each Mantine colour `stringToColour` can return, so
 * an app-wide level colour maps onto this engine's HSL fan/shade. */
const MANTINE_HUE: Record<string, number> = {
  red: 4,
  orange: 27,
  yellow: 47,
  lime: 85,
  green: 131,
  teal: 168,
  cyan: 189,
  blue: 217,
  indigo: 228,
  violet: 255,
  grape: 288,
  pink: 339,
};

/** Base hue for a synthetic (no-levels) family. */
const SYNTHETIC_BASE_HUE = MANTINE_HUE.blue;
/** Half-spread of a level's stage hues around its base hue. */
const STAGE_FAN_DEGREES = 18;
const SATURATION = 70;
const FILL_LIGHTNESS = 50;
const ACCENT_LIGHTNESS = 42;
/**
 * Capped-light mix range (percent of hue mixed into `FILL_SURFACE`). Even the
 * darkest stage item stays light enough in light mode (dark enough in dark mode)
 * for the default text colour to stay readable on it.
 */
const MIX_DARKEST = 46;
const MIX_LIGHTEST = 18;
/**
 * Surface the hue is tinted over. White in light mode; a lifted dark surface
 * (`dark-5`, not the near-black body) in dark mode, so even the lightest tint
 * keeps enough lightness for its hue to read. Resolved per scheme by
 * `light-dark()`, which keys off Mantine's `color-scheme` CSS property. Nudge the
 * dark stop (dark-6 subtler, dark-4 bolder) to tune dark-mode vividness.
 */
const FILL_SURFACE = 'light-dark(var(--mantine-color-white), var(--mantine-color-dark-5))';

/** The Mantine colour the whole app paints a level with. */
export function levelMantineColour(levelId: number): string {
  return stringToColour(`level-${levelId}`);
}

/** Base hue for a level, taken from its app-wide Mantine colour. */
export function levelBaseHue(levelId: number): number {
  return MANTINE_HUE[levelMantineColour(levelId)] ?? SYNTHETIC_BASE_HUE;
}

function hslColour(hue: number, lightness: number): string {
  // Stage fanning can push a hue below 0° or past 360°; wrap it back into range.
  const wrapped = ((hue % 360) + 360) % 360;
  return `hsl(${Math.round(wrapped)} ${SATURATION}% ${lightness}%)`;
}

/** Legend swatch: the level's exact app-wide Mantine colour, so the key matches
 * the level badges shown on the other views. */
export function levelSwatchColour(levelId: number): string {
  return levelMantineColour(levelId);
}

/**
 * Map every stage item id to its `fill`/`accent` colours from the level → stage →
 * item hierarchy. Stage and stage-item order follow the order they appear in the
 * stages tree (the planner's canonical ordering).
 */
export function computeStageItemColours(
  stages: StageWithStageItems[],
  levels: LevelResponse[]
): Record<number, StageItemColour> {
  const result: Record<number, StageItemColour> = {};
  const hasLevels = levels.length > 0;

  // Group stages under their level id (preserving tree order). No-levels
  // tournaments collapse every stage into one synthetic family.
  const groups = new Map<number | 'synthetic', StageWithStageItems[]>();
  for (const stage of stages) {
    const key = hasLevels ? stage.level_id : 'synthetic';
    if (key == null) continue; // null-level stage in a levelled tournament → neutral
    const bucket = groups.get(key);
    if (bucket == null) groups.set(key, [stage]);
    else bucket.push(stage);
  }

  groups.forEach((levelStages, key) => {
    const baseHue = key === 'synthetic' ? SYNTHETIC_BASE_HUE : levelBaseHue(key);
    const stageCount = levelStages.length;
    levelStages.forEach((stage, stageIndex) => {
      // Fan the level's stages tightly around its base hue; a lone stage sits
      // exactly on it, so a single-stage level reads as one solid hue family.
      const stageHue =
        stageCount <= 1
          ? baseHue
          : baseHue + (stageIndex / (stageCount - 1) - 0.5) * 2 * STAGE_FAN_DEGREES;
      const items = stage.stage_items;
      const itemCount = items.length;
      items.forEach((item, itemIndex) => {
        const shade = itemCount <= 1 ? 0 : itemIndex / (itemCount - 1);
        const mix = MIX_DARKEST - shade * (MIX_DARKEST - MIX_LIGHTEST);
        result[item.id] = {
          fill: `color-mix(in srgb, ${FILL_SURFACE}, ${hslColour(stageHue, FILL_LIGHTNESS)} ${mix.toFixed(1)}%)`,
          accent: hslColour(stageHue, ACCENT_LIGHTNESS),
        };
      });
    });
  });

  // Stage items left uncoloured (a null-level stage in a levelled tournament).
  for (const stage of stages) {
    for (const item of stage.stage_items) {
      if (!(item.id in result)) result[item.id] = NEUTRAL;
    }
  }
  return result;
}

export { NEUTRAL as NEUTRAL_STAGE_ITEM_COLOUR };
