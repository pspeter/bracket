import { InsertionLine, LayoutCourt, ScheduleGridLayout, computeInsertionLines } from './layout';
import { OptimisticMatch, OptimisticStage, applyPlanningActions } from './optimistic';
import { PlanningAction, SelectionState, selectionReducer } from './selection';

export interface ConflictPreviewMatch extends OptimisticMatch {
  stage_item_input1_id: number | null;
  stage_item_input2_id: number | null;
}

export interface ConflictPreviewStage extends OptimisticStage {
  stage_items: { rounds: { matches: ConflictPreviewMatch[] }[] }[];
}

export interface ConflictPreview {
  insertionLines: Set<string>;
  swapTargets: Set<number>;
}

interface PreviewBlock {
  courtId: number;
  match: ConflictPreviewMatch;
  startMinutes: number;
}

interface PreparedPreview {
  matchesById: Map<number, ConflictPreviewMatch>;
  blocksByCourtId: Map<number, PreviewBlock[]>;
  blockByMatchId: Map<number, PreviewBlock>;
  defaultBreakMinutes: number;
}

export function insertionLineKey(courtId: number, index: number): string {
  return `${courtId}:${index}`;
}

function emptyPreview(): ConflictPreview {
  return { insertionLines: new Set(), swapTargets: new Set() };
}

function getSelectedMatchId(selection: SelectionState): number | null {
  switch (selection.kind) {
    case 'match-selected':
      return selection.match.matchId;
    case 'tray-match-selected':
      return selection.matchId;
    default:
      return null;
  }
}

function getMatches(stages: ConflictPreviewStage[]): ConflictPreviewMatch[] {
  return stages.flatMap((stage) =>
    stage.stage_items.flatMap((stageItem) => stageItem.rounds.flatMap((round) => round.matches))
  );
}

function matchInputIds(match: ConflictPreviewMatch): Set<number> {
  return new Set(
    [match.stage_item_input1_id, match.stage_item_input2_id].filter(
      (id): id is number => id != null
    )
  );
}

function sharesInput(match1: ConflictPreviewMatch, match2: ConflictPreviewMatch): boolean {
  const inputIds = matchInputIds(match1);
  return (
    (match2.stage_item_input1_id != null && inputIds.has(match2.stage_item_input1_id)) ||
    (match2.stage_item_input2_id != null && inputIds.has(match2.stage_item_input2_id))
  );
}

function playingIntervalMillis(match: ConflictPreviewMatch): [number, number] | null {
  if (match.start_time == null) return null;

  const start = new Date(match.start_time).getTime();
  return [start, start + slotLengthMinutes(match) * 60_000];
}

function playingTimesOverlap(match1: ConflictPreviewMatch, match2: ConflictPreviewMatch): boolean {
  const interval1 = playingIntervalMillis(match1);
  const interval2 = playingIntervalMillis(match2);
  if (interval1 == null || interval2 == null) return false;

  // Half-open intervals [start, end): adjacent playing windows do not conflict.
  return interval1[0] < interval2[1] && interval2[0] < interval1[1];
}

function slotLengthMinutes(match: ConflictPreviewMatch): number {
  return match.duration_minutes;
}

function playingMinutesOverlap(
  startMinutes1: number,
  durationMinutes1: number,
  startMinutes2: number,
  durationMinutes2: number
): boolean {
  return (
    startMinutes1 < startMinutes2 + durationMinutes2 &&
    startMinutes2 < startMinutes1 + durationMinutes1
  );
}

export function actionCreatesSelectedConflict({
  stages,
  selectedMatchId,
  tournamentStartTime,
  defaultBreakMinutes = 0,
  action,
}: {
  stages: ConflictPreviewStage[];
  selectedMatchId: number;
  tournamentStartTime: string | Date;
  defaultBreakMinutes?: number;
  action: PlanningAction;
}): boolean {
  const simulated = applyPlanningActions(
    stages,
    [action],
    tournamentStartTime,
    defaultBreakMinutes
  );
  const matches = getMatches(simulated);
  const selected = matches.find((match) => match.id === selectedMatchId);
  if (selected == null || matchInputIds(selected).size === 0) return false;

  return matches.some(
    (match) =>
      match.id !== selected.id &&
      sharesInput(selected, match) &&
      playingTimesOverlap(selected, match)
  );
}

function preparePreview(
  stages: ConflictPreviewStage[],
  layout: ScheduleGridLayout<LayoutCourt, ConflictPreviewMatch>,
  selection: SelectionState
): PreparedPreview | null {
  const selectedMatchId = getSelectedMatchId(selection);
  if (selectedMatchId == null) return null;

  const matchesById = new Map(getMatches(stages).map((match) => [match.id, match]));
  if (!matchesById.has(selectedMatchId)) return null;

  const blocksByCourtId = new Map<number, PreviewBlock[]>();
  const blockByMatchId = new Map<number, PreviewBlock>();

  for (const { court, blocks } of layout.courts) {
    const previewBlocks = blocks.map((block) => ({
      courtId: court.id,
      match: block.match,
      startMinutes: block.startMinutes,
    }));
    blocksByCourtId.set(court.id, previewBlocks);
    for (const block of previewBlocks) {
      blockByMatchId.set(block.match.id, block);
    }
  }

  return {
    matchesById,
    blocksByCourtId,
    blockByMatchId,
    defaultBreakMinutes: layout.defaultBreakMinutes,
  };
}

/**
 * A match queued for a court, paired with the start it would keep if nothing
 * forced it later. Matches that stay put carry their existing start; a match
 * that moves into a slot adopts that slot's start (mirroring the backend, which
 * copies the swapped match's `start_time` or resets a rescheduled one to None).
 */
interface RescheduleEntry {
  match: ConflictPreviewMatch;
  baseStartMinutes: number;
}

function rescheduleCourt(
  prepared: PreparedPreview,
  courtId: number,
  entries: RescheduleEntry[]
): PreviewBlock[] {
  let previousEnd: number | null = null;
  return entries.map(({ match, baseStartMinutes }) => {
    let startMinutes = baseStartMinutes;
    if (previousEnd != null) {
      startMinutes = Math.max(startMinutes, previousEnd + prepared.defaultBreakMinutes);
    }
    const block = { courtId, match, startMinutes };
    previousEnd = startMinutes + slotLengthMinutes(match);
    return block;
  });
}

/** Existing matches on a court as entries that keep their current starts. */
function courtEntries(
  prepared: PreparedPreview,
  courtId: number,
  excludeMatchId?: number
): RescheduleEntry[] {
  return (prepared.blocksByCourtId.get(courtId) ?? [])
    .filter((block) => block.match.id !== excludeMatchId)
    .map((block) => ({ match: block.match, baseStartMinutes: block.startMinutes }));
}

function blocksConflict(block1: PreviewBlock, block2: PreviewBlock): boolean {
  return (
    sharesInput(block1.match, block2.match) &&
    playingMinutesOverlap(
      block1.startMinutes,
      slotLengthMinutes(block1.match),
      block2.startMinutes,
      slotLengthMinutes(block2.match)
    )
  );
}

function postScheduleBlocks(
  prepared: PreparedPreview,
  affectedCourts: Map<number, PreviewBlock[]>
): PreviewBlock[] {
  const courtIds = new Set([...prepared.blocksByCourtId.keys(), ...affectedCourts.keys()]);
  return [...courtIds].flatMap(
    (courtId) => affectedCourts.get(courtId) ?? prepared.blocksByCourtId.get(courtId) ?? []
  );
}

function changedPostBlocks(prepared: PreparedPreview, postBlocks: PreviewBlock[]): PreviewBlock[] {
  return postBlocks.filter((block) => {
    const previous = prepared.blockByMatchId.get(block.match.id);
    return (
      previous == null ||
      previous.courtId !== block.courtId ||
      previous.startMinutes !== block.startMinutes
    );
  });
}

function affectedScheduleCreatesConflict(
  prepared: PreparedPreview,
  affectedCourts: Map<number, PreviewBlock[]>
): boolean {
  const postBlocks = postScheduleBlocks(prepared, affectedCourts);
  const changedBlocks = changedPostBlocks(prepared, postBlocks);

  for (const changedBlock of changedBlocks) {
    for (const block of postBlocks) {
      if (changedBlock.match.id !== block.match.id && blocksConflict(changedBlock, block)) {
        return true;
      }
    }
  }

  return false;
}

function rescheduleAffectedCourts(
  prepared: PreparedPreview,
  action: Extract<PlanningAction, { type: 'reschedule' }>
): Map<number, PreviewBlock[]> | null {
  const match = prepared.matchesById.get(action.matchId);
  if (match == null) return null;

  const { old_court_id, new_court_id, new_position } = action.body;
  const targetEntries = courtEntries(prepared, new_court_id, match.id);
  const index = Math.min(Math.max(new_position, 0), targetEntries.length);
  // The moved match seeds at the tournament start (backend resets start_time to None).
  const newCourtEntries: RescheduleEntry[] = [
    ...targetEntries.slice(0, index),
    { match, baseStartMinutes: 0 },
    ...targetEntries.slice(index),
  ];
  const affectedCourts = new Map<number, PreviewBlock[]>();
  affectedCourts.set(new_court_id, rescheduleCourt(prepared, new_court_id, newCourtEntries));

  if (old_court_id != null && old_court_id !== new_court_id) {
    affectedCourts.set(
      old_court_id,
      rescheduleCourt(prepared, old_court_id, courtEntries(prepared, old_court_id, match.id))
    );
  }

  return affectedCourts;
}

function swapAffectedCourts(
  prepared: PreparedPreview,
  action: Extract<PlanningAction, { type: 'swap' }>
): Map<number, PreviewBlock[]> | null {
  const match1 = prepared.matchesById.get(action.matchId1);
  const match2 = prepared.matchesById.get(action.matchId2);
  if (match1 == null || match2 == null) return null;

  const block1 = prepared.blockByMatchId.get(match1.id);
  const block2 = prepared.blockByMatchId.get(match2.id);
  if (block1 == null && block2 == null) return null;

  const affectedCourts = new Map<number, PreviewBlock[]>();

  if (block1 != null && block2 != null) {
    // Two scheduled matches trade slots: each adopts the other slot's start.
    const swapEntry = (block: PreviewBlock): RescheduleEntry => {
      if (block.match.id === match1.id)
        return { match: match2, baseStartMinutes: block.startMinutes };
      if (block.match.id === match2.id)
        return { match: match1, baseStartMinutes: block.startMinutes };
      return { match: block.match, baseStartMinutes: block.startMinutes };
    };

    if (block1.courtId === block2.courtId) {
      const entries = (prepared.blocksByCourtId.get(block1.courtId) ?? []).map(swapEntry);
      affectedCourts.set(block1.courtId, rescheduleCourt(prepared, block1.courtId, entries));
      return affectedCourts;
    }

    affectedCourts.set(
      block1.courtId,
      rescheduleCourt(
        prepared,
        block1.courtId,
        (prepared.blocksByCourtId.get(block1.courtId) ?? []).map(swapEntry)
      )
    );
    affectedCourts.set(
      block2.courtId,
      rescheduleCourt(
        prepared,
        block2.courtId,
        (prepared.blocksByCourtId.get(block2.courtId) ?? []).map(swapEntry)
      )
    );
    return affectedCourts;
  }

  // Mixed swap: the tray match takes over the scheduled match's slot.
  const scheduledBlock = block1 ?? block2!;
  const incomingMatch = block1 == null ? match1 : match2;
  const entries = (prepared.blocksByCourtId.get(scheduledBlock.courtId) ?? []).map(
    (block): RescheduleEntry =>
      block.match.id === scheduledBlock.match.id
        ? { match: incomingMatch, baseStartMinutes: block.startMinutes }
        : { match: block.match, baseStartMinutes: block.startMinutes }
  );
  affectedCourts.set(
    scheduledBlock.courtId,
    rescheduleCourt(prepared, scheduledBlock.courtId, entries)
  );
  return affectedCourts;
}

function planningActionCreatesConflict(prepared: PreparedPreview, action: PlanningAction): boolean {
  let affectedCourts: Map<number, PreviewBlock[]> | null = null;

  switch (action.type) {
    case 'reschedule':
      affectedCourts = rescheduleAffectedCourts(prepared, action);
      break;
    case 'swap':
      affectedCourts = swapAffectedCourts(prepared, action);
      break;
    default:
      return false;
  }

  return affectedCourts != null && affectedScheduleCreatesConflict(prepared, affectedCourts);
}

export function computeConflictPreview({
  stages,
  layout,
  selection,
}: {
  stages: ConflictPreviewStage[];
  layout: ScheduleGridLayout<LayoutCourt, ConflictPreviewMatch>;
  selection: SelectionState;
}): ConflictPreview {
  if (selection.kind === 'idle') return emptyPreview();
  const prepared = preparePreview(stages, layout, selection);
  if (prepared == null) return emptyPreview();
  const preparedPreview = prepared;

  const preview = emptyPreview();

  function hasConflict(actions: PlanningAction[]): boolean {
    return actions.some((action) => planningActionCreatesConflict(preparedPreview, action));
  }

  for (const { court, blocks } of layout.courts) {
    const lines: InsertionLine[] = computeInsertionLines(blocks);
    for (const line of lines) {
      const transition = selectionReducer(selection, {
        type: 'tap-insertion-line',
        courtId: court.id,
        index: line.index,
      });
      if (hasConflict(transition.actions)) {
        preview.insertionLines.add(insertionLineKey(court.id, line.index));
      }
    }

    blocks.forEach((block, blockIndex) => {
      const transition = selectionReducer(selection, {
        type: 'tap-match',
        match: {
          matchId: block.match.id,
          courtId: court.id,
          position: blockIndex,
        },
      });
      if (hasConflict(transition.actions)) {
        preview.swapTargets.add(block.match.id);
      }
    });
  }

  return preview;
}
