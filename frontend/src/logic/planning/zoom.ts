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
  agenda: 8,
  compact: 4,
  overview: 2,
};

/** Ruler tick spacing per zoom level, in minutes. */
export const ZOOM_TICK_INTERVAL_MINUTES: Record<ZoomLevel, number> = {
  agenda: 30,
  compact: 30,
  overview: 60,
};
