/**
 * Optimistic application of planning actions to the cached stages payload.
 *
 * Mirrors the backend's packing rules (`reorder_all_matches`) so the grid can
 * render the outcome of a tap immediately, before the request round-trips: per
 * court, scheduled matches are ordered by start time and shifted only when the
 * previous occupied interval plus the default break would overlap them.
 */
import { PlanningAction } from './selection';

export interface OptimisticMatch {
  id: number;
  court_id: number | null;
  start_time: string | null;
  duration_minutes: number;
}

export interface OptimisticStage {
  stage_items: { rounds: { matches: OptimisticMatch[] }[] }[];
}

export function applyPlanningActions<S extends OptimisticStage>(
  stages: S[],
  actions: PlanningAction[],
  tournamentStartTime: string | Date,
  defaultBreakMinutes: number
): S[] {
  const next = structuredClone(stages);
  const allMatches = next.flatMap((stage) =>
    stage.stage_items.flatMap((stageItem) => stageItem.rounds.flatMap((round) => round.matches))
  );
  const matchesById = new Map(allMatches.map((match) => [match.id, match]));
  const startMillis = (
    tournamentStartTime instanceof Date ? tournamentStartTime : new Date(tournamentStartTime)
  ).getTime();

  function minutesAfterStart(minutes: number): string {
    return new Date(startMillis + minutes * 60_000).toISOString();
  }

  function startMinutes(match: OptimisticMatch): number {
    return (new Date(match.start_time!).getTime() - startMillis) / 60_000;
  }

  function scheduledOnCourt(courtId: number, excludeMatchId?: number): OptimisticMatch[] {
    return allMatches
      .filter(
        (match) =>
          match.court_id === courtId && match.start_time != null && match.id !== excludeMatchId
      )
      .sort((match1, match2) => startMinutes(match1) - startMinutes(match2));
  }

  function rewriteCourt(courtId: number, orderedMatches: OptimisticMatch[]): void {
    let previousEnd: number | null = null;
    for (const match of orderedMatches) {
      let currentStart = match.start_time == null ? 0 : startMinutes(match);
      if (previousEnd != null) {
        currentStart = Math.max(currentStart, previousEnd + defaultBreakMinutes);
      }
      match.court_id = courtId;
      match.start_time = minutesAfterStart(currentStart);
      previousEnd = currentStart + match.duration_minutes;
    }
  }

  function insertMatchAt(
    courtId: number,
    match: OptimisticMatch,
    position: number,
    excludeMatchId?: number
  ): void {
    const courtMatches = scheduledOnCourt(courtId, excludeMatchId);
    const index = Math.min(Math.max(position, 0), courtMatches.length);
    match.court_id = courtId;
    match.start_time = null;
    rewriteCourt(courtId, [...courtMatches.slice(0, index), match, ...courtMatches.slice(index)]);
  }

  for (const action of actions) {
    switch (action.type) {
      case 'swap': {
        const match1 = matchesById.get(action.matchId1);
        const match2 = matchesById.get(action.matchId2);
        if (match1 == null || match2 == null) {
          break;
        }
        const scheduled1 = match1.court_id != null && match1.start_time != null;
        const scheduled2 = match2.court_id != null && match2.start_time != null;
        if (scheduled1 && scheduled2) {
          const courtId = match1.court_id;
          const startTime = match1.start_time;
          match1.court_id = match2.court_id;
          match1.start_time = match2.start_time;
          match2.court_id = courtId;
          match2.start_time = startTime;
        } else if (scheduled1 !== scheduled2) {
          // Mixed swap: the tray match takes over the scheduled match's slot,
          // and the scheduled match goes back to the tray.
          const vacating = scheduled1 ? match1 : match2;
          const incoming = scheduled1 ? match2 : match1;
          incoming.court_id = vacating.court_id;
          incoming.start_time = vacating.start_time;
          vacating.court_id = null;
          vacating.start_time = null;
        }
        break;
      }
      case 'reschedule': {
        const match = matchesById.get(action.matchId);
        if (match == null) {
          break;
        }
        insertMatchAt(action.body.new_court_id, match, action.body.new_position, match.id);
        break;
      }
      case 'unschedule': {
        const match = matchesById.get(action.matchId);
        if (match == null) {
          break;
        }
        match.court_id = null;
        match.start_time = null;
        break;
      }
      default:
        break;
    }
  }

  return next;
}
