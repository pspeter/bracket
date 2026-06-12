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

/** Structural mirror of the generated `MatchState`; absent means upcoming. */
export type LayoutMatchState = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';

export interface LayoutMatch {
  id: number;
  duration_minutes: number;
  margin_minutes: number;
  position_in_schedule: number | null;
  start_time: string | null;
  state?: LayoutMatchState | null;
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
  /**
   * Inside the court's frozen past: at or before the court's last completed or
   * in-progress match. Moving any such match (even an upcoming one scored out
   * of order around) would repack the court and shift the recorded start times
   * of played matches, so locked matches are excluded from tap-to-place.
   */
  locked: boolean;
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

export interface InsertionLine {
  /** Insertion index: place before the match currently at this index (count = at the end). */
  index: number;
  /** Vertical position of the line, in minutes from the tournament start. */
  offsetMinutes: number;
}

function isPlayed(match: LayoutMatch): boolean {
  return match.state === 'COMPLETED' || match.state === 'IN_PROGRESS';
}

/**
 * Tap targets for placing a match on a court: one line half a margin above the
 * first match (mirroring the end-of-court line below the last one), one centered
 * in each margin gap between consecutive matches, and one in the gap after the
 * last match. An empty court gets a single line at the top.
 *
 * Only the future portion of the court accepts insertions: lines above the last
 * locked (completed/in-progress) match are omitted, so a repack can never shift
 * the recorded start times of already-played matches. Courts with no played
 * matches offer all positions.
 */
export function computeInsertionLines(blocks: MatchBlock[]): InsertionLine[] {
  if (blocks.length === 0) {
    return [{ index: 0, offsetMinutes: 0 }];
  }

  const lockedCount = blocks.filter((block) => block.locked).length;

  const first = blocks[0];
  const lines: InsertionLine[] = [
    { index: 0, offsetMinutes: first.startMinutes - first.marginMinutes / 2 },
  ];
  for (let i = 1; i <= blocks.length; i += 1) {
    const previous = blocks[i - 1];
    const gapStart = previous.startMinutes + previous.durationMinutes;
    lines.push({ index: i, offsetMinutes: (gapStart + previous.endMinutes) / 2 });
  }
  return lines.filter((line) => line.index >= lockedCount);
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

    // Everything up to the court's last played match is the frozen past.
    const lockedCount = scheduled.reduce((count, m, index) => (isPlayed(m) ? index + 1 : count), 0);

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
        locked: blocks.length < lockedCount,
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
