/**
 * Pure, headless layout computation for the time-proportional schedule grid.
 *
 * Mirrors the backend packing rule (`reschedule_matches_in_db`): per court, scheduled
 * matches are sorted by `position_in_schedule` and packed sequentially, gapless, from
 * the tournament start time, each occupying `duration_minutes + margin_minutes`.
 * All positions are expressed in minutes from the tournament start; rendering converts
 * minutes to pixels.
 */

export interface LayoutCourt {
  id: number;
  name: string;
}

export interface LayoutMatch {
  id: number;
  duration_minutes: number;
  margin_minutes: number;
  position_in_schedule: number | null;
  start_time: string | null;
}

export interface MatchBlock<M extends LayoutMatch = LayoutMatch> {
  match: M;
  /** Offset of the match start from the tournament start. */
  startMinutes: number;
  /** Playing time (the backend already folds custom durations into this). */
  durationMinutes: number;
  /** Pause after the match, rendered as a gap between this card and the next. */
  marginMinutes: number;
  /** `startMinutes + durationMinutes + marginMinutes`. */
  endMinutes: number;
  /** Absolute computed start time. */
  startTime: Date;
}

export interface CourtTimeline<
  C extends LayoutCourt = LayoutCourt,
  M extends LayoutMatch = LayoutMatch,
> {
  court: C;
  blocks: MatchBlock<M>[];
}

export interface RulerTick {
  offsetMinutes: number;
  time: Date;
}

export interface ScheduleGridLayout<
  C extends LayoutCourt = LayoutCourt,
  M extends LayoutMatch = LayoutMatch,
> {
  courts: CourtTimeline<C, M>[];
  /** Height of the grid in minutes: the longest court, rounded up to a whole tick. */
  totalMinutes: number;
  ticks: RulerTick[];
}

export interface ScheduleLayoutInput<C extends LayoutCourt, M extends LayoutMatch> {
  courts: C[];
  matchesByCourtId: Record<number, M[]>;
  tournamentStartTime: string | Date;
  tickIntervalMinutes?: number;
  minTotalMinutes?: number;
}

const DEFAULT_TICK_INTERVAL_MINUTES = 30;
const DEFAULT_MIN_TOTAL_MINUTES = 60;

function addMinutes(date: Date, minutes: number): Date {
  return new Date(date.getTime() + minutes * 60_000);
}

export function computeScheduleLayout<C extends LayoutCourt, M extends LayoutMatch>({
  courts,
  matchesByCourtId,
  tournamentStartTime,
  tickIntervalMinutes = DEFAULT_TICK_INTERVAL_MINUTES,
  minTotalMinutes = DEFAULT_MIN_TOTAL_MINUTES,
}: ScheduleLayoutInput<C, M>): ScheduleGridLayout<C, M> {
  const startTime =
    tournamentStartTime instanceof Date ? tournamentStartTime : new Date(tournamentStartTime);

  const courtTimelines = courts.map((c) => {
    const scheduled = (matchesByCourtId[c.id] ?? [])
      .filter((m) => m.start_time != null)
      .sort((m1, m2) => (m1.position_in_schedule ?? 0) - (m2.position_in_schedule ?? 0));

    const blocks: MatchBlock<M>[] = [];
    let currentMinutes = 0;
    for (const m of scheduled) {
      const endMinutes = currentMinutes + m.duration_minutes + m.margin_minutes;
      blocks.push({
        match: m,
        startMinutes: currentMinutes,
        durationMinutes: m.duration_minutes,
        marginMinutes: m.margin_minutes,
        endMinutes,
        startTime: addMinutes(startTime, currentMinutes),
      });
      currentMinutes = endMinutes;
    }
    return { court: c, blocks };
  });

  const maxEndMinutes = Math.max(
    minTotalMinutes,
    ...courtTimelines.map(
      (timeline) => timeline.blocks[timeline.blocks.length - 1]?.endMinutes ?? 0
    )
  );
  const totalMinutes = Math.ceil(maxEndMinutes / tickIntervalMinutes) * tickIntervalMinutes;

  const ticks: RulerTick[] = [];
  for (let offset = 0; offset <= totalMinutes; offset += tickIntervalMinutes) {
    ticks.push({ offsetMinutes: offset, time: addMinutes(startTime, offset) });
  }

  return { courts: courtTimelines, totalMinutes, ticks };
}
