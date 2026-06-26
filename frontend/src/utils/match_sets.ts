import type { MatchSet } from '@openapi';
import { SCORE_LIVE_COLOUR, SCORE_PENDING_COLOUR, scoreColour } from '../logic/colors';

export function getSetsWon(sets: MatchSet[]): { input1: number; input2: number } {
  const input1 = sets.filter(
    (s) => s.state === 'COMPLETED' && s.stage_item_input1_score > s.stage_item_input2_score
  ).length;
  const input2 = sets.filter(
    (s) => s.state === 'COMPLETED' && s.stage_item_input2_score > s.stage_item_input1_score
  ).length;
  return { input1, input2 };
}

export function getSetScoreColors(set: MatchSet): { s1: string; s2: string } {
  if (set.state === 'NOT_STARTED') return { s1: SCORE_PENDING_COLOUR, s2: SCORE_PENDING_COLOUR };
  if (set.state === 'IN_PROGRESS') return { s1: SCORE_LIVE_COLOUR, s2: SCORE_LIVE_COLOUR };
  return {
    s1: scoreColour(set.stage_item_input1_score, set.stage_item_input2_score),
    s2: scoreColour(set.stage_item_input2_score, set.stage_item_input1_score),
  };
}
