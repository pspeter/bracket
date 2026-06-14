/**
 * Resolves screen coordinates to a planner focus anchor (court + fraction of
 * the schedule), so zoom gestures can keep the region under the pointer or
 * pinch in view. DOM-based on purpose: the gesture handlers live outside the
 * grid and must measure the pre-zoom layout at the moment of the gesture.
 */

import { FocusTarget } from '@logic/planning/selection';

/** Marks the grid's scroll container; used to anchor button zooms to its center. */
export const PLANNER_GRID_ATTRIBUTE = 'data-planner-grid';
/** Marks each court column's time area (the box spanning the whole schedule). */
export const COURT_CONTENT_ATTRIBUTE = 'data-court-content';
/** Marks planner UI surfaces whose clicks should not count as page-empty deselects. */
export const PLANNER_DESELECT_IGNORE_ATTRIBUTE = 'data-planner-deselect-ignore';

/**
 * Anchor for the court/time region at a point on screen. Points left or right
 * of the courts (e.g. on the time ruler) resolve to the nearest court; points
 * above or below the schedule clamp to its edges. Null when no grid is shown.
 */
export function resolvePlannerAnchor(clientX: number, clientY: number): FocusTarget | null {
  const contents = Array.from(
    document.querySelectorAll<HTMLElement>(`[${COURT_CONTENT_ATTRIBUTE}]`)
  );
  let nearest: HTMLElement | null = null;
  let nearestDistance = Infinity;
  for (const content of contents) {
    const rect = content.getBoundingClientRect();
    const distance =
      clientX < rect.left ? rect.left - clientX : clientX > rect.right ? clientX - rect.right : 0;
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearest = content;
    }
  }
  if (nearest == null) return null;

  const courtId = Number(nearest.getAttribute(COURT_CONTENT_ATTRIBUTE));
  const rect = nearest.getBoundingClientRect();
  if (!Number.isFinite(courtId) || rect.height === 0) return null;
  const fraction = Math.min(Math.max((clientY - rect.top) / rect.height, 0), 1);
  return { courtId, fraction };
}

/** Anchor for whatever is currently centered in the grid's viewport. */
export function resolveGridCenterAnchor(): FocusTarget | null {
  const grid = document.querySelector<HTMLElement>(`[${PLANNER_GRID_ATTRIBUTE}]`);
  if (grid == null) return null;
  const rect = grid.getBoundingClientRect();
  return resolvePlannerAnchor(rect.left + rect.width / 2, rect.top + rect.height / 2);
}
