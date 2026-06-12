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
  selected: ConflictPreviewMatch;
  blocksByCourtId: Map<number, PreviewBlock[]>;
  blockByMatchId: Map<number, PreviewBlock>;
  sharedBlocks: PreviewBlock[];
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
  return [start, start + match.duration_minutes * 60_000];
}

function playingTimesOverlap(match1: ConflictPreviewMatch, match2: ConflictPreviewMatch): boolean {
  const interval1 = playingIntervalMillis(match1);
  const interval2 = playingIntervalMillis(match2);
  if (interval1 == null || interval2 == null) return false;

  // Half-open intervals [start, end): adjacent playing windows do not conflict.
  return interval1[0] < interval2[1] && interval2[0] < interval1[1];
}

function slotLengthMinutes(match: ConflictPreviewMatch): number {
  return match.duration_minutes + match.margin_minutes;
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
  action,
}: {
  stages: ConflictPreviewStage[];
  selectedMatchId: number;
  tournamentStartTime: string | Date;
  action: PlanningAction;
}): boolean {
  const simulated = applyPlanningActions(stages, [action], tournamentStartTime);
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

  const selected = getMatches(stages).find((match) => match.id === selectedMatchId);
  if (selected == null) return null;

  const selectedInputIds = matchInputIds(selected);
  if (selectedInputIds.size === 0) return null;

  const blocksByCourtId = new Map<number, PreviewBlock[]>();
  const blockByMatchId = new Map<number, PreviewBlock>();
  const sharedBlocks: PreviewBlock[] = [];

  for (const { court, blocks } of layout.courts) {
    const previewBlocks = blocks.map((block) => ({
      courtId: court.id,
      match: block.match,
      startMinutes: block.startMinutes,
    }));
    blocksByCourtId.set(court.id, previewBlocks);
    for (const block of previewBlocks) {
      blockByMatchId.set(block.match.id, block);
      if (block.match.id !== selected.id && sharesInput(selected, block.match)) {
        sharedBlocks.push(block);
      }
    }
  }

  return { selected, blocksByCourtId, blockByMatchId, sharedBlocks };
}

function repackCourt(courtId: number, matches: ConflictPreviewMatch[]): PreviewBlock[] {
  let startMinutes = 0;
  return matches.map((match) => {
    const block = { courtId, match, startMinutes };
    startMinutes += slotLengthMinutes(match);
    return block;
  });
}

function startAtPosition(blocks: PreviewBlock[], position: number): number {
  let startMinutes = 0;
  for (const block of blocks.slice(0, position)) {
    startMinutes += slotLengthMinutes(block.match);
  }
  return startMinutes;
}

function blockConflictsWithSelected(
  prepared: PreparedPreview,
  selectedStartMinutes: number,
  block: PreviewBlock
): boolean {
  return (
    sharesInput(prepared.selected, block.match) &&
    playingMinutesOverlap(
      selectedStartMinutes,
      prepared.selected.duration_minutes,
      block.startMinutes,
      block.match.duration_minutes
    )
  );
}

function selectedIntervalConflicts({
  prepared,
  selectedCourtId,
  selectedStartMinutes,
  affectedCourts,
}: {
  prepared: PreparedPreview;
  selectedCourtId: number;
  selectedStartMinutes: number;
  affectedCourts: Map<number, PreviewBlock[]>;
}): boolean {
  for (const [courtId, blocks] of affectedCourts) {
    if (courtId === selectedCourtId) continue;
    if (blocks.some((block) => blockConflictsWithSelected(prepared, selectedStartMinutes, block))) {
      return true;
    }
  }

  return prepared.sharedBlocks.some(
    (block) =>
      block.courtId !== selectedCourtId &&
      !affectedCourts.has(block.courtId) &&
      blockConflictsWithSelected(prepared, selectedStartMinutes, block)
  );
}

function rescheduleCreatesSelectedConflict(
  prepared: PreparedPreview,
  action: Extract<PlanningAction, { type: 'reschedule' }>
): boolean {
  if (action.matchId !== prepared.selected.id) return false;

  const { old_court_id, new_court_id, new_position } = action.body;
  const targetBlocks = (prepared.blocksByCourtId.get(new_court_id) ?? []).filter(
    (block) => block.match.id !== prepared.selected.id
  );
  const selectedStartMinutes = startAtPosition(targetBlocks, new_position);
  const affectedCourts = new Map<number, PreviewBlock[]>();

  if (old_court_id != null && old_court_id !== new_court_id) {
    const oldCourtMatches = (prepared.blocksByCourtId.get(old_court_id) ?? [])
      .filter((block) => block.match.id !== prepared.selected.id)
      .map((block) => block.match);
    affectedCourts.set(old_court_id, repackCourt(old_court_id, oldCourtMatches));
  }

  return selectedIntervalConflicts({
    prepared,
    selectedCourtId: new_court_id,
    selectedStartMinutes,
    affectedCourts,
  });
}

function swapCreatesSelectedConflict(
  prepared: PreparedPreview,
  action: Extract<PlanningAction, { type: 'swap' }>
): boolean {
  const selectedMatchId = prepared.selected.id;
  const targetMatchId =
    action.matchId1 === selectedMatchId
      ? action.matchId2
      : action.matchId2 === selectedMatchId
        ? action.matchId1
        : null;
  if (targetMatchId == null) return false;

  const targetBlock = prepared.blockByMatchId.get(targetMatchId);
  // Swapping a scheduled selected match with a tray match sends the selected
  // match to the tray, so there is no selected match interval to preview.
  if (targetBlock == null) return false;

  const selectedBlock = prepared.blockByMatchId.get(selectedMatchId);
  const affectedCourts = new Map<number, PreviewBlock[]>();
  if (selectedBlock != null && selectedBlock.courtId !== targetBlock.courtId) {
    const oldCourtMatches = (prepared.blocksByCourtId.get(selectedBlock.courtId) ?? []).map(
      (block) => (block.match.id === selectedMatchId ? targetBlock.match : block.match)
    );
    affectedCourts.set(selectedBlock.courtId, repackCourt(selectedBlock.courtId, oldCourtMatches));
  }

  return selectedIntervalConflicts({
    prepared,
    selectedCourtId: targetBlock.courtId,
    selectedStartMinutes: targetBlock.startMinutes,
    affectedCourts,
  });
}

function planningActionCreatesSelectedConflict(
  prepared: PreparedPreview,
  action: PlanningAction
): boolean {
  switch (action.type) {
    case 'reschedule':
      return rescheduleCreatesSelectedConflict(prepared, action);
    case 'swap':
      return swapCreatesSelectedConflict(prepared, action);
    default:
      return false;
  }
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
    return actions.some((action) => planningActionCreatesSelectedConflict(preparedPreview, action));
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
          position: block.match.position_in_schedule ?? blockIndex,
        },
      });
      if (hasConflict(transition.actions)) {
        preview.swapTargets.add(block.match.id);
      }
    });
  }

  return preview;
}
