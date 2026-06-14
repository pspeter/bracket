/**
 * Multi-device sync policy for the planning grid.
 *
 * The schedule revalidates periodically so a co-organizer's moves and score
 * entries appear without a manual refresh. Polling is suspended whenever a
 * selection is active (match selected, tray match selected, or confirmation
 * pending) so the grid never shifts under the user's finger mid-placement,
 * and resumes — with an immediate refresh — once the selection clears.
 *
 * A placement can still race a move made on another device while polling is
 * paused; the backend rejects such stale writes with 409 Conflict, which
 * `isStaleScheduleError` recognizes so the UI can refetch and ask the user to
 * pick again.
 */

import { SelectionState } from './selection';

export const SCHEDULE_POLL_INTERVAL_MS = 10_000;

export function pollingPaused(selection: SelectionState): boolean {
  return selection.kind !== 'idle';
}

/**
 * The SWR `refreshInterval` for the schedule data: the polling interval, or 0
 * (disabled) while a selection holds the grid still.
 */
export function scheduleRefreshInterval(selection: SelectionState): number {
  return pollingPaused(selection) ? 0 : SCHEDULE_POLL_INTERVAL_MS;
}

/**
 * Whether clearing/changing the selection should trigger an immediate
 * revalidation: exactly when a pause ends, so changes that piled up while the
 * grid was held still appear right away instead of after a full interval.
 */
export function shouldRefreshOnSelectionChange(
  previous: SelectionState,
  next: SelectionState
): boolean {
  return pollingPaused(previous) && !pollingPaused(next);
}

/**
 * The backend's optimistic-concurrency rejection: a reschedule whose old
 * court/position no longer matches because someone else moved the match in
 * between is refused with 409 Conflict.
 */
export function isStaleScheduleError(error: unknown): boolean {
  if (typeof error !== 'object' || error == null) {
    return false;
  }
  const response = (error as { response?: { status?: number } }).response;
  return response?.status === 409;
}
