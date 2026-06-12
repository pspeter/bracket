/**
 * Optimistic application of planning actions to the cached stages payload.
 *
 * Mirrors the backend's packing rules (`reorder_all_matches`) so the grid can
 * render the outcome of a tap immediately, before the request round-trips: per
 * court, scheduled matches are sorted by (fractional) position and re-packed
 * contiguously (0..n-1) with gapless start times from the tournament start.
 */
import { PlanningAction } from './selection';

export interface OptimisticMatch {
  id: number;
  court_id: number | null;
  start_time: string | null;
  position_in_schedule: number | null;
  duration_minutes: number;
  margin_minutes: number;
}

export interface OptimisticStage {
  stage_items: { rounds: { matches: OptimisticMatch[] }[] }[];
}

export function applyPlanningActions<S extends OptimisticStage>(
  stages: S[],
  actions: PlanningAction[],
  tournamentStartTime: string | Date
): S[] {
  const next = structuredClone(stages);
  const allMatches = next.flatMap((stage) =>
    stage.stage_items.flatMap((stageItem) => stageItem.rounds.flatMap((round) => round.matches))
  );
  const matchesById = new Map(allMatches.map((match) => [match.id, match]));

  // Fractional sort keys per scheduled match, mirroring the backend's ±0.5
  // insertion trick; the re-pack below turns them back into integers.
  const sortPositions = new Map<number, number>();
  for (const match of allMatches) {
    if (match.start_time != null && match.position_in_schedule != null) {
      sortPositions.set(match.id, match.position_in_schedule);
    }
  }

  for (const action of actions) {
    switch (action.type) {
      case 'swap': {
        const match1 = matchesById.get(action.matchId1);
        const match2 = matchesById.get(action.matchId2);
        if (match1 == null || match2 == null) {
          break;
        }
        const scheduled1 = sortPositions.has(match1.id);
        const scheduled2 = sortPositions.has(match2.id);
        if (scheduled1 && scheduled2) {
          const position1 = sortPositions.get(match1.id)!;
          sortPositions.set(match1.id, sortPositions.get(match2.id)!);
          sortPositions.set(match2.id, position1);
          const courtId = match1.court_id;
          match1.court_id = match2.court_id;
          match2.court_id = courtId;
        } else if (scheduled1 !== scheduled2) {
          // Mixed swap: the tray match takes over the scheduled match's slot,
          // and the scheduled match goes back to the tray.
          const vacating = scheduled1 ? match1 : match2;
          const incoming = scheduled1 ? match2 : match1;
          incoming.court_id = vacating.court_id;
          sortPositions.set(incoming.id, sortPositions.get(vacating.id)!);
          vacating.court_id = null;
          vacating.start_time = null;
          vacating.position_in_schedule = null;
          sortPositions.delete(vacating.id);
        }
        break;
      }
      case 'reschedule': {
        const match = matchesById.get(action.matchId);
        if (match == null) {
          break;
        }
        const { old_court_id, old_position, new_court_id, new_position } = action.body;
        const insertBefore =
          old_court_id == null ||
          new_court_id !== old_court_id ||
          old_position == null ||
          new_position < old_position;
        match.court_id = new_court_id;
        sortPositions.set(match.id, new_position + (insertBefore ? -0.5 : 0.5));
        break;
      }
      case 'unschedule': {
        const match = matchesById.get(action.matchId);
        if (match == null) {
          break;
        }
        match.court_id = null;
        match.start_time = null;
        match.position_in_schedule = null;
        sortPositions.delete(match.id);
        break;
      }
      default:
        break;
    }
  }

  const matchesByCourt = new Map<number, OptimisticMatch[]>();
  for (const match of allMatches) {
    if (match.court_id != null && sortPositions.has(match.id)) {
      const courtMatches = matchesByCourt.get(match.court_id) ?? [];
      courtMatches.push(match);
      matchesByCourt.set(match.court_id, courtMatches);
    }
  }

  const startMillis = (
    tournamentStartTime instanceof Date ? tournamentStartTime : new Date(tournamentStartTime)
  ).getTime();
  for (const courtMatches of matchesByCourt.values()) {
    courtMatches.sort((m1, m2) => sortPositions.get(m1.id)! - sortPositions.get(m2.id)!);
    let offsetMinutes = 0;
    courtMatches.forEach((match, index) => {
      match.position_in_schedule = index;
      match.start_time = new Date(startMillis + offsetMinutes * 60_000).toISOString();
      offsetMinutes += match.duration_minutes + match.margin_minutes;
    });
  }

  return next;
}
