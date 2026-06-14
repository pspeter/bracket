/**
 * The single source of truth for every colour the app paints, so an entity reads
 * as the same colour everywhere and the colours of different things stay far
 * enough apart to tell apart at a glance.
 *
 * Three families live here:
 *
 *   1. `stringToColour`  — a deterministic Mantine palette colour for an
 *      arbitrary key (team, stage item, …). Used where any stable-but-distinct
 *      colour will do.
 *
 *   2. Level colours      — a level's colour is generated in OKLCH and spread by
 *      the level's *position* in the tournament, so the levels actually present
 *      land as far apart on the hue wheel as the count allows. `levelColour`
 *      returns the badge colour shown on every view; the planner derives its
 *      stage/item shades from the same hue (`levelHue`), so a level keeps its
 *      identity from a badge to a schedule card.
 *
 *   3. Score colours      — win / draw / loss (and live / pending) chip colours,
 *      shared by the results, dashboard, score-tracking and schedule views.
 *
 * Why OKLCH for levels: OKLCH is perceptually uniform, so equal hue steps look
 * equally different and a fixed lightness reads as equally light across every
 * hue. That makes "spread the levels evenly around the wheel" actually look even,
 * and keeps the within-level shade steps from blurring into the next level — the
 * failure mode of the old HSL scheme, where e.g. blue (217°) and indigo (228°)
 * were numerically distinct but visually identical. OKLCH and `color-mix(in
 * oklch)` are Baseline-supported in every browser this app targets.
 */

import type { LevelResponse, MatchWithDetails, StageWithStageItems } from '@openapi';

/**
 * Deterministic Mantine colour for an arbitrary key (team, stage item, …), so
 * the same entity is painted the same colour everywhere. Pure and
 * dependency-free so logic, services and their unit tests can share it.
 */
export function stringToColour(input: string): string {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    // eslint-disable-next-line no-bitwise
    hash = input.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = [
    'pink',
    'violet',
    'green',
    'blue',
    'red',
    'grape',
    'indigo',
    'cyan',
    'orange',
    'yellow',
    'teal',
  ];
  return colors[Math.abs(hash) % colors.length];
}

// ── Level colours (OKLCH) ───────────────────────────────────────────────────

/** Hue the first level (and a tournament without levels) anchors on. */
const LEVEL_BASE_HUE = 250;
/** Lightness/chroma of a level's badge + planner accent. Tuned so the colour
 * reads as text on its own light tint (the `variant="light"` badge) and as a
 * border/glyph in the planner, identically across every hue. */
const LEVEL_LIGHTNESS = 0.55;
const LEVEL_CHROMA = 0.15;

function oklch(lightness: number, chroma: number, hue: number): string {
  const wrapped = ((hue % 360) + 360) % 360;
  return `oklch(${lightness.toFixed(3)} ${chroma.toFixed(3)} ${wrapped.toFixed(1)})`;
}

/** Levels in a canonical order (by position, then id) so a level gets the same
 * index — and therefore the same colour — regardless of array order or which
 * view is asking. */
function orderedLevels(levels: LevelResponse[]): LevelResponse[] {
  return [...levels].sort((a, b) => a.position - b.position || a.id - b.id);
}

/**
 * Base hue (deg) for a level, spread evenly around the wheel by the level's
 * position among all levels — so N levels are as far apart as N points can be.
 *
 * Trade-off: because the spread divides the wheel by the level *count*, adding
 * or removing a level re-spaces the others. We accept that (levels are set up
 * once and rarely change) in exchange for maximal separation, which is the whole
 * point of the scheme. Unknown levels fall back to the base hue.
 */
export function levelHue(levelId: number, levels: LevelResponse[]): number {
  const ordered = orderedLevels(levels);
  const index = ordered.findIndex((level) => level.id === levelId);
  if (index < 0) return LEVEL_BASE_HUE;
  const count = Math.max(ordered.length, 1);
  return (LEVEL_BASE_HUE + (360 * index) / count) % 360;
}

/** A level's app-wide colour: the same hue every view paints it with. Pass it
 * straight to a Mantine `<Badge color={...} variant="light">`. */
export function levelColour(levelId: number, levels: LevelResponse[]): string {
  return oklch(LEVEL_LIGHTNESS, LEVEL_CHROMA, levelHue(levelId, levels));
}

/** Legend swatch in the planner: a level's exact app-wide colour, so the key
 * matches the level badges shown on the other views. */
export function levelSwatchColour(levelId: number, levels: LevelResponse[]): string {
  return levelColour(levelId, levels);
}

// ── Schedule / planner colours ──────────────────────────────────────────────

export interface StageItemColour {
  /** Tint for the card/overview background; identical across schedule views. */
  fill: string;
  /** Saturated hue for the card's left border and the overview status glyph. */
  accent: string;
}

/** Stages without a level in a levelled tournament fall back to neutral grey. */
const NEUTRAL: StageItemColour = {
  fill: 'var(--mantine-color-gray-light)',
  accent: 'var(--mantine-color-gray-filled)',
};

/** Base hue for a synthetic (no-levels) family. */
const SYNTHETIC_BASE_HUE = LEVEL_BASE_HUE;
/** Half-spread (deg) of a level's stage hues around its base hue. Kept well
 * below the gap between levels so a level's stages still read as one family. */
const STAGE_FAN_DEGREES = 10;

/** Saturated accent (border / overview glyph). */
const ACCENT_CHROMA = LEVEL_CHROMA;
const ACCENT_LIGHTNESS = LEVEL_LIGHTNESS;

/**
 * Card-fill tint, resolved per colour scheme by `light-dark()`. The hue is the
 * same in both modes; only lightness/chroma flip. The item shade walks the
 * lightness within each mode (darkest stage item first), evenly in OKLCH so the
 * steps read as even and never collapse into one another.
 */
const FILL_CHROMA = 0.045;
const FILL_LIGHT_DARKEST = 0.9;
const FILL_LIGHT_LIGHTEST = 0.965;
const FILL_DARK_DARKEST = 0.38;
const FILL_DARK_LIGHTEST = 0.3;

function fillColour(hue: number, shade: number): string {
  const light = oklch(
    FILL_LIGHT_DARKEST + shade * (FILL_LIGHT_LIGHTEST - FILL_LIGHT_DARKEST),
    FILL_CHROMA,
    hue
  );
  const dark = oklch(
    FILL_DARK_DARKEST + shade * (FILL_DARK_LIGHTEST - FILL_DARK_DARKEST),
    FILL_CHROMA,
    hue
  );
  return `light-dark(${light}, ${dark})`;
}

/**
 * Map every stage item id to its `fill`/`accent` colours from the level → stage
 * → item hierarchy:
 *
 *   level → base hue        (the level's app-wide hue, so it matches other views)
 *   stage → hue cluster      (tight fan around the level hue)
 *   item  → lightness shade  (even OKLCH steps, darkest stage item first)
 *
 * Stage and stage-item order follow the stages tree (the planner's canonical
 * ordering). Tournaments without levels collapse to one synthetic family.
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
    const baseHue = key === 'synthetic' ? SYNTHETIC_BASE_HUE : levelHue(key, levels);
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
        result[item.id] = {
          fill: fillColour(stageHue, shade),
          accent: oklch(ACCENT_LIGHTNESS, ACCENT_CHROMA, stageHue),
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

// ── Score colours ───────────────────────────────────────────────────────────

/**
 * Winner / draw / loser score colours, used as solid chip backgrounds with
 * white text so the score keeps strong contrast on top of any stage-item tint.
 *
 * Colourblind-safe by construction: win/loss are the Okabe-Ito bluish-green and
 * vermillion, a pair designed to stay distinct under deuteranopia/protanopia
 * (red–green deficiency, ~8% of men) while still reading as "green-ish good /
 * red-ish bad" to everyone. We deliberately avoid a pure red/green pair, which
 * collapses to near-identical khaki under those deficiencies. Draw stays a
 * neutral grey that is darker than both, so it separates by lightness (the cue
 * every CVD type keeps) as well as by chroma. Colour is never the only signal —
 * the score number sits inside the chip — so this only sharpens the at-a-glance
 * read; it isn't load-bearing for correctness.
 */
export const SCORE_WIN_COLOUR = '#009e73';
export const SCORE_DRAW_COLOUR = '#656565';
export const SCORE_LOSE_COLOUR = '#d55e00';
/** Live (in-progress) and pending (not-started) score chip backgrounds. */
const SCORE_LIVE_COLOUR = '#74c0fc';
const SCORE_PENDING_COLOUR = '#868e96';

/** Score colour from one side's perspective: own score vs the other side's. */
export function scoreColour(own: number, other: number): string {
  if (own > other) return SCORE_WIN_COLOUR;
  if (own < other) return SCORE_LOSE_COLOUR;
  return SCORE_DRAW_COLOUR;
}

/**
 * State-aware score chip colours for both sides of a match: blue while live,
 * grey while pending, win/draw/loss once played.
 */
export function getScoreColors(match: MatchWithDetails) {
  if (match.state === 'IN_PROGRESS') {
    return {
      stage_item_input1_score: SCORE_LIVE_COLOUR,
      stage_item_input2_score: SCORE_LIVE_COLOUR,
      textColor: '#1c1c1c',
    };
  }

  if (match.state === 'NOT_STARTED') {
    return {
      stage_item_input1_score: SCORE_PENDING_COLOUR,
      stage_item_input2_score: SCORE_PENDING_COLOUR,
      textColor: 'white',
    };
  }

  return {
    stage_item_input1_score: scoreColour(
      match.stage_item_input1_score,
      match.stage_item_input2_score
    ),
    stage_item_input2_score: scoreColour(
      match.stage_item_input2_score,
      match.stage_item_input1_score
    ),
    textColor: 'white',
  };
}
