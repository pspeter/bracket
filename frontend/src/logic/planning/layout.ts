/**
 * Pure, headless layout computation for the time-proportional schedule grid.
 *
 * Mirrors the backend schedule source of truth: per court, scheduled matches are
 * sorted by `start_time`, and each card occupies `duration_minutes`.
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
  start_time: string | null;
  state?: LayoutMatchState | null;
}

export interface MatchBlock<M extends LayoutMatch = LayoutMatch> {
  match: M;
  /** Offset of the match start from the tournament start. */
  startMinutes: number;
  /** Playing time (the backend already folds custom durations into this). */
  durationMinutes: number;
  /** `startMinutes + durationMinutes`. */
  endMinutes: number;
  /** Absolute computed start time. */
  startTime: Date;
  /** Tournament-level default break, used for insertion affordances. */
  defaultBreakMinutes: number;
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
  defaultBreakMinutes: number;
}

export interface ScheduleLayoutInput<C extends LayoutCourt, M extends LayoutMatch> {
  courts: C[];
  matchesByCourtId: Record<number, M[]>;
  tournamentStartTime: string | Date;
  defaultBreakMinutes?: number;
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
 * Tap targets for placing a match on a court: one line before the first match, one
 * centered in each actual gap between consecutive matches, and one after the last
 * match. An empty court gets a single line at the top.
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
  const defaultBreakMinutes = first.defaultBreakMinutes;
  const lines: InsertionLine[] = [
    { index: 0, offsetMinutes: Math.max(0, first.startMinutes - defaultBreakMinutes / 2) },
  ];
  for (let i = 1; i <= blocks.length; i += 1) {
    const previous = blocks[i - 1];
    const next = blocks[i];
    if (next == null) {
      lines.push({ index: i, offsetMinutes: previous.endMinutes + defaultBreakMinutes / 2 });
    } else {
      lines.push({ index: i, offsetMinutes: (previous.endMinutes + next.startMinutes) / 2 });
    }
  }
  return lines.filter((line) => line.index >= lockedCount);
}

/**
 * A derived break on a court. For a break between two matches it is the gap from
 * the previous match's end to the next match's start; for the leading break it is
 * the delay between the tournament start and the first match. Either way it is
 * identified by the match that *follows* it (resizing shifts that match and every
 * later one on the court).
 */
export interface BreakBlock {
  /** The match after the break; the backend key for resizing it. */
  matchId: number;
  /** Index of the following match in the court's blocks. */
  index: number;
  /** Break start, in minutes from the tournament start (previous match's end, or 0). */
  startMinutes: number;
  /** Break end (next match's start). */
  endMinutes: number;
  /** `endMinutes - startMinutes`, clamped at 0 for overlapping/sub-default spacing. */
  durationMinutes: number;
  /**
   * The value the "default pause duration" reset writes: the tournament default
   * break for a break between matches, but 0 for the leading break (a court has
   * no delay by default).
   */
  defaultBreakMinutes: number;
  /**
   * Inside the court's frozen past: the following match is locked (see
   * `MatchBlock.locked`). Editing such a break would shift recorded start times
   * of played matches, so the UI does not offer it.
   */
  locked: boolean;
}

/**
 * Derive the break elements for a court: a leading break before the first match
 * (the court's start delay, 0 by default) plus one between every pair of
 * consecutive matches. A back-to-back pair — or a court starting at the
 * tournament start — still yields a 0-minute break so the planner can render a
 * clickable line where a pause can be inserted.
 */
export function computeBreaks(blocks: MatchBlock[]): BreakBlock[] {
  if (blocks.length === 0) {
    return [];
  }

  const first = blocks[0];
  const breaks: BreakBlock[] = [
    {
      matchId: first.match.id,
      index: 0,
      startMinutes: 0,
      endMinutes: first.startMinutes,
      durationMinutes: Math.max(0, first.startMinutes),
      // A court has no start delay by default, so resetting clears it to 0.
      defaultBreakMinutes: 0,
      locked: first.locked,
    },
  ];
  for (let i = 1; i < blocks.length; i += 1) {
    const previous = blocks[i - 1];
    const next = blocks[i];
    breaks.push({
      matchId: next.match.id,
      index: i,
      startMinutes: previous.endMinutes,
      endMinutes: next.startMinutes,
      durationMinutes: Math.max(0, next.startMinutes - previous.endMinutes),
      defaultBreakMinutes: next.defaultBreakMinutes,
      locked: next.locked,
    });
  }
  return breaks;
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
  defaultBreakMinutes = 0,
  tickIntervalMinutes = DEFAULT_TICK_INTERVAL_MINUTES,
  minTotalMinutes = DEFAULT_MIN_TOTAL_MINUTES,
}: ScheduleLayoutInput<C, M>): ScheduleGridLayout<C, M> {
  const startTime =
    tournamentStartTime instanceof Date ? tournamentStartTime : new Date(tournamentStartTime);

  const courtTimelines = courts.map((c) => {
    const scheduled = (matchesByCourtId[c.id] ?? [])
      .filter((m) => m.start_time != null)
      .sort((m1, m2) => new Date(m1.start_time!).getTime() - new Date(m2.start_time!).getTime());

    // Everything up to the court's last played match is the frozen past.
    const lockedCount = scheduled.reduce((count, m, index) => (isPlayed(m) ? index + 1 : count), 0);

    const blocks: MatchBlock<M>[] = [];
    for (const m of scheduled) {
      const matchStartTime = new Date(m.start_time!);
      const startMinutes = (matchStartTime.getTime() - startTime.getTime()) / 60_000;
      const endMinutes = startMinutes + m.duration_minutes;
      blocks.push({
        match: m,
        startMinutes,
        durationMinutes: m.duration_minutes,
        endMinutes,
        startTime: matchStartTime,
        defaultBreakMinutes,
        locked: blocks.length < lockedCount,
      });
    }
    return { court: c, blocks };
  });

  const maxEndMinutes = Math.max(
    minTotalMinutes,
    ...courtTimelines.map((timeline) =>
      timeline.blocks.length === 0
        ? 0
        : timeline.blocks[timeline.blocks.length - 1].endMinutes + defaultBreakMinutes
    )
  );
  const totalMinutes = Math.ceil(maxEndMinutes / tickIntervalMinutes) * tickIntervalMinutes;

  const ticks: RulerTick[] = [];
  for (let offset = 0; offset <= totalMinutes; offset += tickIntervalMinutes) {
    ticks.push({ offsetMinutes: offset, time: addMinutes(startTime, offset) });
  }

  return { courts: courtTimelines, totalMinutes, ticks, defaultBreakMinutes };
}
