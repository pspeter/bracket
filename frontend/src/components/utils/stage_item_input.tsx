import {
  StageItemInputEmpty,
  StageItemInputFinal,
  StageItemInputOptionFinal,
  StageItemInputOptionTentative,
  StageItemInputTentative,
} from '@openapi';
import { assert_not_none } from './assert';

export type StageItemInput = StageItemInputTentative | StageItemInputFinal | StageItemInputEmpty;
export type StageItemInputOption = StageItemInputOptionTentative | StageItemInputOptionFinal;

export interface StageItemInputChoice {
  value: string;
  label: string;
  team_id: number | null;
  winner_from_stage_item_id: number | null;
  winner_position: number | null;
  already_taken: boolean;
  team_level_id?: number | null;
}

export function getPositionName(position: number) {
  // TODO: handle inputs like `21` (21st)
  return (
    {
      1: '1st',
      2: '2nd',
      3: '3rd',
    }[position] || `${position}th`
  );
}

export function formatStageItemInputTentative(
  stage_item_input: StageItemInputTentative | StageItemInputOptionTentative,
  stageItemsLookup: any
) {
  const winnerFromStageItemId = assert_not_none(stage_item_input.winner_from_stage_item_id);
  const stageItemName =
    stageItemsLookup[winnerFromStageItemId]?.name ?? `stage item ${winnerFromStageItemId}`;
  return `${getPositionName(assert_not_none(stage_item_input.winner_position))} of ${stageItemName}`;
}

export function formatStageItemInput(
  stage_item_input: StageItemInput | null,
  stageItemsLookup: any
) {
  if (stage_item_input == null) return null;
  if ('team' in stage_item_input) return stage_item_input.team.name;
  if (stage_item_input?.winner_from_stage_item_id != null) {
    return formatStageItemInputTentative(stage_item_input, stageItemsLookup);
  }
  return null;
}

// Inactive teams are excluded from referee duty universally, across every stage type (issue
// #282): a resolved (Final) slot naming an inactive team is never a referee candidate. Tentative
// and Empty slots don't yet name a team, so they stay eligible exactly as they do for playing.
export function isEligibleRefereeSlot(stage_item_input: StageItemInput) {
  return !('team' in stage_item_input) || stage_item_input.team.active;
}
