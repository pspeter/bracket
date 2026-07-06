/**
 * Client-side conflict engine: a faithful 1:1 port of the backend
 * `bracket/logic/planning/conflicts.py`.
 *
 * `computeConflictFlags(stages, defaultBreakMinutes, options)` returns a
 * `Map<matchId, ConflictFlags>` covering every conflict type the backend persists:
 *
 *   - team double-booking (`stage_item_input{1,2}_conflict`), flagged two ways: a
 *     **team_id** pass (definitive matches only, catching the same team under different
 *     slot ids across stage items) and a **slot-id** pass that also covers placeholder
 *     (tentative/empty) playing slots not yet resolved to a team;
 *   - winner-of precedence (`precedence_conflict` / `feeder_precedence_conflict`);
 *   - cross-stage precedence (a stage item must wait for the group it feeds off);
 *   - short break (`short_break_conflict`);
 *   - referee double-booking (`referee_conflict`), both team-backed and placeholder
 *     (slot-id based, mirroring the auto-scheduler and the placement preview);
 *   - round order (`round_order_conflict`).
 *
 * Times are handled as epoch-millisecond numbers; a match's playing window is
 * `[start, start + duration_minutes)` — half-open, so back-to-back matches do not
 * conflict, exactly as the backend's `matches_overlap` / `_time_ranges_overlap`.
 */

/** A playing or referee slot, as much of it as conflict detection needs. */
export interface ConflictInput {
  id: number;
  team_id: number | null;
  winner_from_stage_item_id: number | null;
}

export interface ConflictMatch {
  id: number;
  start_time: string | null;
  duration_minutes: number;
  court_id: number | null;
  stage_item_input1: ConflictInput | null;
  stage_item_input2: ConflictInput | null;
  stage_item_input1_id: number | null;
  stage_item_input2_id: number | null;
  stage_item_input1_winner_from_match_id: number | null;
  stage_item_input2_winner_from_match_id: number | null;
  referee_stage_item_input_id: number | null;
  referee: ConflictInput | null;
}

export interface ConflictRound {
  id: number;
  matches: ConflictMatch[];
}

export interface ConflictStageItem {
  id: number;
  type: 'ROUND_ROBIN' | 'SINGLE_ELIMINATION' | 'SWISS' | 'MEXICANO';
  inputs: ConflictInput[];
  rounds: ConflictRound[];
}

export interface ConflictStage {
  stage_items: ConflictStageItem[];
}

export interface ConflictFlags {
  stage_item_input1_conflict: boolean;
  stage_item_input2_conflict: boolean;
  /** Set on the dependent match: it starts before a match it depends on has finished. */
  precedence_conflict: boolean;
  /** Set on the source match: it ends after a match depending on its results has started. */
  feeder_precedence_conflict: boolean;
  short_break_conflict: boolean;
  referee_conflict: boolean;
  /** Set on a round-N match whose start is before the last round-(N-1) match ends. */
  round_order_conflict: boolean;
}

interface PlayingWindow {
  stageItemInputId: number;
  startMillis: number;
  endMillis: number;
}

function emptyFlags(): ConflictFlags {
  return {
    stage_item_input1_conflict: false,
    stage_item_input2_conflict: false,
    precedence_conflict: false,
    feeder_precedence_conflict: false,
    short_break_conflict: false,
    referee_conflict: false,
    round_order_conflict: false,
  };
}

function startMillis(match: ConflictMatch): number | null {
  return match.start_time == null ? null : new Date(match.start_time).getTime();
}

function endMillis(match: ConflictMatch): number {
  // Callers guard start_time != null before reading the end of a window.
  return new Date(match.start_time!).getTime() + match.duration_minutes * 60_000;
}

/** Half-open intervals [start, end): back-to-back ranges (end1 == start2) do not overlap. */
function timeRangesOverlap(start1: number, end1: number, start2: number, end2: number): boolean {
  return start1 < end2 && start2 < end1;
}

function windowsOverlap(window1: PlayingWindow, window2: PlayingWindow): boolean {
  return timeRangesOverlap(
    window1.startMillis,
    window1.endMillis,
    window2.startMillis,
    window2.endMillis
  );
}

function matchesOverlap(match1: ConflictMatch, match2: ConflictMatch): boolean {
  if (match1.start_time == null || match2.start_time == null) {
    return false;
  }
  return timeRangesOverlap(
    startMillis(match1)!,
    endMillis(match1),
    startMillis(match2)!,
    endMillis(match2)
  );
}

/**
 * A "definitive" match has both playing slots resolved to concrete inputs. The
 * backend models these as `MatchWithDetailsDefinitive`; here both input objects
 * are present.
 */
function isDefinitive(match: ConflictMatch): boolean {
  return match.stage_item_input1 != null && match.stage_item_input2 != null;
}

function getAllMatches(stages: ConflictStage[]): ConflictMatch[] {
  return stages.flatMap((stage) =>
    stage.stage_items.flatMap((stageItem) => stageItem.rounds.flatMap((round) => round.matches))
  );
}

function getMatchInputs(match: ConflictMatch): [number | null, ConflictInput | null][] {
  return [
    [match.stage_item_input1_id, match.stage_item_input1],
    [match.stage_item_input2_id, match.stage_item_input2],
  ];
}

function getTeamIdsByInputId(stages: ConflictStage[]): Map<number, number> {
  const teamIdsByInputId = new Map<number, number>();
  const set = (input: ConflictInput | null): void => {
    if (input != null && input.team_id != null) {
      teamIdsByInputId.set(input.id, input.team_id);
    }
  };
  for (const stage of stages) {
    for (const stageItem of stage.stage_items) {
      for (const input of stageItem.inputs) {
        set(input);
      }
      for (const round of stageItem.rounds) {
        for (const match of round.matches) {
          set(match.stage_item_input1);
          set(match.stage_item_input2);
        }
      }
    }
  }
  return teamIdsByInputId;
}

function getTeamId(
  inputId: number,
  input: ConflictInput | null,
  teamIdsByInputId: Map<number, number>
): number | null {
  if (input != null && input.team_id != null) {
    return input.team_id;
  }
  return teamIdsByInputId.get(inputId) ?? null;
}

type TeamPlayingWindows = Map<number, [ConflictMatch, PlayingWindow][]>;

function getTeamPlayingWindows(stages: ConflictStage[]): TeamPlayingWindows {
  const teamIdsByInputId = getTeamIdsByInputId(stages);
  const windowsByTeamId: TeamPlayingWindows = new Map();

  for (const match of getAllMatches(stages)) {
    const start = startMillis(match);
    if (start == null) {
      continue;
    }
    for (const [inputId, input] of getMatchInputs(match)) {
      if (inputId == null) {
        continue;
      }
      const teamId = getTeamId(inputId, input, teamIdsByInputId);
      if (teamId == null) {
        continue;
      }
      const window: PlayingWindow = {
        stageItemInputId: inputId,
        startMillis: start,
        endMillis: endMillis(match),
      };
      const existing = windowsByTeamId.get(teamId);
      if (existing == null) {
        windowsByTeamId.set(teamId, [[match, window]]);
      } else {
        existing.push([match, window]);
      }
    }
  }

  return windowsByTeamId;
}

function setStageItemInputConflict(
  match: ConflictMatch,
  window: PlayingWindow,
  flags: Map<number, ConflictFlags>
): void {
  const matchFlags = flags.get(match.id)!;
  if (window.stageItemInputId === match.stage_item_input1_id) {
    matchFlags.stage_item_input1_conflict = true;
    return;
  }
  if (window.stageItemInputId === match.stage_item_input2_id) {
    matchFlags.stage_item_input2_conflict = true;
    return;
  }
  throw new Error('Playing window input does not belong to match');
}

function setTeamOverlapConflicts(stages: ConflictStage[], flags: Map<number, ConflictFlags>): void {
  for (const teamWindows of getTeamPlayingWindows(stages).values()) {
    const definitiveWindows = teamWindows.filter(([match]) => isDefinitive(match));
    for (let i = 0; i < definitiveWindows.length; i += 1) {
      const [match1, window1] = definitiveWindows[i];
      for (let j = i + 1; j < definitiveWindows.length; j += 1) {
        const [match2, window2] = definitiveWindows[j];
        if (match1.id === match2.id || !windowsOverlap(window1, window2)) {
          continue;
        }
        setStageItemInputConflict(match1, window1, flags);
        setStageItemInputConflict(match2, window2, flags);
      }
    }
  }
}

function setWinnerOfPrecedenceConflicts(
  matches: ConflictMatch[],
  flags: Map<number, ConflictFlags>
): void {
  const matchesById = new Map(matches.map((match) => [match.id, match]));

  for (const match of matches) {
    if (match.start_time == null) {
      continue;
    }
    const feederIds = [
      match.stage_item_input1_winner_from_match_id,
      match.stage_item_input2_winner_from_match_id,
    ];
    for (const feederId of feederIds) {
      if (feederId == null) {
        continue;
      }
      const feeder = matchesById.get(feederId);
      if (feeder != null && feeder.start_time != null && startMillis(match)! < endMillis(feeder)) {
        // The dependent match starts before its feeder finishes; flag both sides.
        flags.get(match.id)!.precedence_conflict = true;
        flags.get(feeder.id)!.feeder_precedence_conflict = true;
      }
    }
  }
}

function getStageItemEndTimes(stages: ConflictStage[]): Map<number, number> {
  const endTimes = new Map<number, number>();
  for (const stage of stages) {
    for (const stageItem of stage.stage_items) {
      let latest: number | null = null;
      for (const round of stageItem.rounds) {
        for (const match of round.matches) {
          if (match.start_time == null) {
            continue;
          }
          const end = endMillis(match);
          if (latest == null || end > latest) {
            latest = end;
          }
        }
      }
      if (latest != null) {
        endTimes.set(stageItem.id, latest);
      }
    }
  }
  return endTimes;
}

function getStageItemStartTimes(stages: ConflictStage[]): Map<number, number> {
  const startTimes = new Map<number, number>();
  for (const stage of stages) {
    for (const stageItem of stage.stage_items) {
      let earliest: number | null = null;
      for (const round of stageItem.rounds) {
        for (const match of round.matches) {
          const start = startMillis(match);
          if (start == null) {
            continue;
          }
          if (earliest == null || start < earliest) {
            earliest = start;
          }
        }
      }
      if (earliest != null) {
        startTimes.set(stageItem.id, earliest);
      }
    }
  }
  return startTimes;
}

/**
 * Map each source stage item to the earliest start of any stage item feeding off it
 * (i.e. one of its matches has an input whose `winner_from_stage_item_id` points there).
 */
function getEarliestDependentStartTimes(stages: ConflictStage[]): Map<number, number> {
  const stageItemStartTimes = getStageItemStartTimes(stages);
  const earliestDependentStart = new Map<number, number>();

  for (const stage of stages) {
    for (const stageItem of stage.stage_items) {
      const dependentStart = stageItemStartTimes.get(stageItem.id);
      if (dependentStart == null) {
        continue;
      }
      for (const round of stageItem.rounds) {
        for (const match of round.matches) {
          for (const input of [match.stage_item_input1, match.stage_item_input2]) {
            if (input == null || input.winner_from_stage_item_id == null) {
              continue;
            }
            const sourceId = input.winner_from_stage_item_id;
            const existing = earliestDependentStart.get(sourceId);
            if (existing == null || dependentStart < existing) {
              earliestDependentStart.set(sourceId, dependentStart);
            }
          }
        }
      }
    }
  }

  return earliestDependentStart;
}

function setCrossStagePrecedenceConflicts(
  stages: ConflictStage[],
  flags: Map<number, ConflictFlags>
): void {
  const stageItemEndTimes = getStageItemEndTimes(stages);

  for (const match of getAllMatches(stages)) {
    if (match.start_time == null) {
      continue;
    }
    for (const input of [match.stage_item_input1, match.stage_item_input2]) {
      if (input == null || input.winner_from_stage_item_id == null) {
        continue;
      }
      const sourceEnd = stageItemEndTimes.get(input.winner_from_stage_item_id);
      if (sourceEnd != null && startMillis(match)! < sourceEnd) {
        flags.get(match.id)!.precedence_conflict = true;
      }
    }
  }
}

function setCrossStageFeederPrecedenceConflicts(
  stages: ConflictStage[],
  flags: Map<number, ConflictFlags>
): void {
  const earliestDependentStart = getEarliestDependentStartTimes(stages);

  for (const stage of stages) {
    for (const stageItem of stage.stage_items) {
      const dependentStart = earliestDependentStart.get(stageItem.id);
      if (dependentStart == null) {
        continue;
      }
      for (const round of stageItem.rounds) {
        for (const match of round.matches) {
          if (match.start_time == null) {
            continue;
          }
          if (endMillis(match) > dependentStart) {
            flags.get(match.id)!.feeder_precedence_conflict = true;
          }
        }
      }
    }
  }
}

function setShortBreakConflicts(
  matches: ConflictMatch[],
  defaultBreakMinutes: number,
  flags: Map<number, ConflictFlags>
): void {
  const matchesByCourt = new Map<number, ConflictMatch[]>();
  for (const match of matches) {
    if (match.court_id != null && match.start_time != null) {
      const existing = matchesByCourt.get(match.court_id);
      if (existing == null) {
        matchesByCourt.set(match.court_id, [match]);
      } else {
        existing.push(match);
      }
    }
  }

  for (const courtMatches of matchesByCourt.values()) {
    const scheduled = [...courtMatches].sort((a, b) => {
      const startDiff = startMillis(a)! - startMillis(b)!;
      return startDiff !== 0 ? startDiff : a.id - b.id;
    });
    for (let i = 0; i + 1 < scheduled.length; i += 1) {
      const previous = scheduled[i];
      const match = scheduled[i + 1];
      const breakMinutes = (startMillis(match)! - endMillis(previous)) / 60_000;
      if (breakMinutes < defaultBreakMinutes) {
        flags.get(match.id)!.short_break_conflict = true;
      }
    }
  }
}

function setRefereeOverlapConflicts(
  stages: ConflictStage[],
  flags: Map<number, ConflictFlags>
): void {
  const teamPlayingWindows = getTeamPlayingWindows(stages);
  const refereeingMatchesByTeam = new Map<number, ConflictMatch[]>();

  for (const match of getAllMatches(stages)) {
    if (match.start_time == null) {
      continue;
    }
    const referee = match.referee;
    if (referee == null || referee.team_id == null) {
      continue;
    }

    const existing = refereeingMatchesByTeam.get(referee.team_id);
    if (existing == null) {
      refereeingMatchesByTeam.set(referee.team_id, [match]);
    } else {
      existing.push(match);
    }

    for (const [playingMatch, playingWindow] of teamPlayingWindows.get(referee.team_id) ?? []) {
      if (
        !timeRangesOverlap(
          startMillis(match)!,
          endMillis(match),
          playingWindow.startMillis,
          playingWindow.endMillis
        )
      ) {
        continue;
      }
      flags.get(match.id)!.referee_conflict = true;
      if (isDefinitive(playingMatch)) {
        setStageItemInputConflict(playingMatch, playingWindow, flags);
      }
    }
  }

  // A team cannot referee two matches that overlap in time; flag both of them.
  for (const refereeingMatches of refereeingMatchesByTeam.values()) {
    for (let i = 0; i < refereeingMatches.length; i += 1) {
      for (let j = i + 1; j < refereeingMatches.length; j += 1) {
        if (matchesOverlap(refereeingMatches[i], refereeingMatches[j])) {
          flags.get(refereeingMatches[i].id)!.referee_conflict = true;
          flags.get(refereeingMatches[j].id)!.referee_conflict = true;
        }
      }
    }
  }
}

interface SlotOccupancy {
  match: ConflictMatch;
  startMillis: number;
  endMillis: number;
  /** 1 or 2 for the playing slots, null when the slot is occupied as the referee. */
  playingSide: 1 | 2 | null;
}

function flagSlotOccupancy(occupancy: SlotOccupancy, flags: Map<number, ConflictFlags>): void {
  const matchFlags = flags.get(occupancy.match.id)!;
  if (occupancy.playingSide === 1) {
    matchFlags.stage_item_input1_conflict = true;
  } else if (occupancy.playingSide === 2) {
    matchFlags.stage_item_input2_conflict = true;
  } else {
    matchFlags.referee_conflict = true;
  }
}

/**
 * Flag any two overlapping matches that share a `stage_item_input` slot id. This is
 * slot-id based rather than team-id based, so it flags placeholder (tentative/empty)
 * slots too — a slot that isn't yet resolved to a concrete team is still a resource
 * that cannot play and/or referee two overlapping matches.
 */
function setSlotOverlapConflicts(
  stages: ConflictStage[],
  flags: Map<number, ConflictFlags>,
  refereesEnabled: boolean
): void {
  const occupanciesBySlot = new Map<number, SlotOccupancy[]>();
  for (const match of getAllMatches(stages)) {
    const start = startMillis(match);
    if (start == null) {
      continue;
    }
    const slots: [number | null, 1 | 2 | null][] = [
      [match.stage_item_input1_id, 1],
      [match.stage_item_input2_id, 2],
    ];
    // When referees are disabled for the tournament, the referee slot is not a conflict
    // resource, so it is excluded from the overlap pass (matching the team-backed pass).
    if (refereesEnabled) {
      slots.push([match.referee_stage_item_input_id, null]);
    }
    for (const [slotId, playingSide] of slots) {
      if (slotId == null) {
        continue;
      }
      const occupancy: SlotOccupancy = {
        match,
        startMillis: start,
        endMillis: endMillis(match),
        playingSide,
      };
      const existing = occupanciesBySlot.get(slotId);
      if (existing == null) {
        occupanciesBySlot.set(slotId, [occupancy]);
      } else {
        existing.push(occupancy);
      }
    }
  }

  for (const occupancies of occupanciesBySlot.values()) {
    for (let i = 0; i < occupancies.length; i += 1) {
      for (let j = i + 1; j < occupancies.length; j += 1) {
        const occupancy1 = occupancies[i];
        const occupancy2 = occupancies[j];
        if (
          !timeRangesOverlap(
            occupancy1.startMillis,
            occupancy1.endMillis,
            occupancy2.startMillis,
            occupancy2.endMillis
          )
        ) {
          continue;
        }
        flagSlotOccupancy(occupancy1, flags);
        flagSlotOccupancy(occupancy2, flags);
      }
    }
  }
}

/**
 * Flag matches in round N that start before all matches of round N-1 have ended.
 * Round-robin stage items are excluded: their rounds have no required ordering.
 */
function setRoundOrderConflicts(stages: ConflictStage[], flags: Map<number, ConflictFlags>): void {
  for (const stage of stages) {
    for (const stageItem of stage.stage_items) {
      if (stageItem.type === 'ROUND_ROBIN') {
        continue;
      }
      const rounds = [...stageItem.rounds].sort((a, b) => a.id - b.id);
      for (let i = 0; i + 1 < rounds.length; i += 1) {
        const prevRound = rounds[i];
        const currRound = rounds[i + 1];
        let prevRoundEnd: number | null = null;
        for (const match of prevRound.matches) {
          if (match.start_time == null) {
            continue;
          }
          const end = endMillis(match);
          if (prevRoundEnd == null || end > prevRoundEnd) {
            prevRoundEnd = end;
          }
        }
        if (prevRoundEnd == null) {
          continue;
        }
        for (const match of currRound.matches) {
          const start = startMillis(match);
          if (start != null && start < prevRoundEnd) {
            flags.get(match.id)!.round_order_conflict = true;
          }
        }
      }
    }
  }
}

export interface ComputeConflictFlagsOptions {
  /**
   * Restrict the returned map to these match ids. Conflicts are relational, so they are
   * always computed over the whole schedule; only the returned map is narrowed. Defaults
   * to every match.
   */
  matchesOfInterest?: 'all' | ReadonlySet<number>;
  /**
   * Mirrors the tournament's `referees_enabled` toggle. When false, referee slots are not
   * treated as a conflict resource: referee double-booking is skipped in both the
   * team-backed pass (`setRefereeOverlapConflicts`) and the referee-slot pass
   * (`setSlotOverlapConflicts`). Defaults to true.
   */
  refereesEnabled?: boolean;
}

export function computeConflictFlags(
  stages: ConflictStage[],
  defaultBreakMinutes: number,
  options: ComputeConflictFlagsOptions = {}
): Map<number, ConflictFlags> {
  const { matchesOfInterest = 'all', refereesEnabled = true } = options;
  const matches = getAllMatches(stages);
  const flags = new Map<number, ConflictFlags>(matches.map((match) => [match.id, emptyFlags()]));

  setTeamOverlapConflicts(stages, flags);
  if (refereesEnabled) {
    setRefereeOverlapConflicts(stages, flags);
  }
  setSlotOverlapConflicts(stages, flags, refereesEnabled);
  setWinnerOfPrecedenceConflicts(matches, flags);
  setCrossStagePrecedenceConflicts(stages, flags);
  setCrossStageFeederPrecedenceConflicts(stages, flags);
  setShortBreakConflicts(matches, defaultBreakMinutes, flags);
  setRoundOrderConflicts(stages, flags);

  if (matchesOfInterest === 'all') {
    return flags;
  }

  // Conflicts are relational, so they are always computed over the whole schedule;
  // only the returned map is narrowed to the matches of interest.
  const filtered = new Map<number, ConflictFlags>();
  for (const matchId of matchesOfInterest) {
    const matchFlags = flags.get(matchId);
    if (matchFlags != null) {
      filtered.set(matchId, matchFlags);
    }
  }
  return filtered;
}
