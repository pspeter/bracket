/**
 * Pure helpers for the planning grid's semantic zoom.
 *
 * The grid snaps between three discrete levels, each with its own card
 * rendering: `agenda` (one court, full detail), `compact` (3–4 courts,
 * abbreviated cards) and `overview` (all courts, colored blocks without text).
 * Placement is gated to agenda/compact by the planner reducer in selection.ts.
 */

export type ZoomLevel = 'agenda' | 'compact' | 'overview';

/** Ordered from most detailed to most zoomed out. */
export const ZOOM_LEVELS: readonly ZoomLevel[] = ['agenda', 'compact', 'overview'];

export function zoomIn(level: ZoomLevel): ZoomLevel {
  return ZOOM_LEVELS[Math.max(ZOOM_LEVELS.indexOf(level) - 1, 0)];
}

export function zoomOut(level: ZoomLevel): ZoomLevel {
  return ZOOM_LEVELS[Math.min(ZOOM_LEVELS.indexOf(level) + 1, ZOOM_LEVELS.length - 1)];
}

/**
 * Device-appropriate level for the first paint: agenda on phones, compact on
 * anything wider (compact already widens its columns on large screens).
 */
export function defaultZoomLevel(viewportWidthPx: number): ZoomLevel {
  return viewportWidthPx < 768 ? 'agenda' : 'compact';
}

/** Vertical scale per zoom level: one minute of schedule time in pixels. */
export const ZOOM_PX_PER_MINUTE: Record<ZoomLevel, number> = {
  agenda: 5,
  compact: 3,
  overview: 1.25,
};

/** Ruler tick spacing per zoom level, in minutes. */
export const ZOOM_TICK_INTERVAL_MINUTES: Record<ZoomLevel, number> = {
  agenda: 30,
  compact: 30,
  overview: 60,
};

const isNumeric = (word: string) => /^\d+$/.test(word);

/**
 * Shorten a team name for the compact zoom level: keep the first word and
 * shrink the rest to initials, preserving squad numbers ("TSV Musterstadt 2"
 * → "TSV M. 2"). Falls back to bare initials, then to truncation.
 */
export function abbreviateTeamName(name: string, maxLength: number = 12): string {
  const collapsed = name.trim().replace(/\s+/g, ' ');
  if (collapsed.length <= maxLength) return collapsed;

  const words = collapsed.split(' ');
  if (words.length > 1) {
    const abbreviated = [
      words[0],
      ...words.slice(1).map((word) => (isNumeric(word) ? word : `${word[0]}.`)),
    ].join(' ');
    if (abbreviated.length <= maxLength) return abbreviated;

    const initials = words.map((word) => (isNumeric(word) ? word : word[0].toUpperCase())).join('');
    if (initials.length <= maxLength) return initials;
    return `${initials.slice(0, maxLength - 1)}…`;
  }

  return `${collapsed.slice(0, maxLength - 1)}…`;
}

/**
 * Shorten a stage-item name for a cramped badge: a trailing letter/number wins
 * ("Group C" → "C", "Group 10" → "10"); otherwise initials of the words, or a
 * truncated prefix for a single long word.
 */
export function abbreviateStageItem(name: string): string {
  const words = name
    .trim()
    .split(/\s+/)
    .filter((word) => word.length > 0);
  if (words.length === 0) return '';
  const last = words[words.length - 1];
  if (words.length > 1 && last.length <= 3) return last;
  if (words.length > 1) {
    return words
      .map((word) => word[0].toUpperCase())
      .join('')
      .slice(0, 3);
  }
  return name.length <= 4 ? name : `${name.slice(0, 3)}`;
}

/**
 * Squeeze a court name into the few pixels of an overview column header:
 * trailing number if the court is numbered, otherwise initials or a prefix.
 */
export function shortCourtLabel(name: string): string {
  const trimmed = name.trim();
  const numbered = trimmed.match(/(\d+)\s*$/);
  if (numbered) return numbered[1];

  const words = trimmed.split(/\s+/).filter((word) => word.length > 0);
  if (words.length > 1) {
    return words
      .slice(0, 2)
      .map((word) => word[0].toUpperCase())
      .join('');
  }
  return trimmed.slice(0, 2);
}
