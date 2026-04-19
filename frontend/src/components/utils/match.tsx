import { MatchWithDetails } from '@openapi';
import dayjs from 'dayjs';
import { formatStageItemInput } from './stage_item_input';
import { Translator } from './types';

export interface SchedulerSettings {
  eloThreshold: number;
  setEloThreshold: any;
  limit: number;
  setLimit: any;
  iterations: number;
  setIterations: any;
  onlyRecommended: string;
  setOnlyRecommended: any;
}

export function getMatchStartTime(match: MatchWithDetails) {
  return dayjs(match.start_time || '');
}

export function getMatchEndTime(match: MatchWithDetails) {
  return getMatchStartTime(match).add(match.duration_minutes + match.margin_minutes, 'minutes');
}

export function isMatchCompletedRecently(match: MatchWithDetails, minutes: number) {
  return (
    match.completed_at != null &&
    dayjs(match.completed_at).isAfter(dayjs().subtract(minutes, 'minute'))
  );
}

export function isMatchHappening(match: MatchWithDetails) {
  return match.state === 'IN_PROGRESS';
}

export function isMatchInTheFutureOrPresent(match: MatchWithDetails) {
  return getMatchEndTime(match) > dayjs();
}

export function isMatchInTheFuture(match: MatchWithDetails) {
  return getMatchStartTime(match) > dayjs();
}

export function getScoreColors(match: MatchWithDetails) {
  if (match.state === 'IN_PROGRESS') {
    return {
      stage_item_input1_score: '#74c0fc',
      stage_item_input2_score: '#74c0fc',
      textColor: '#1c1c1c',
    };
  }

  if (match.state === 'NOT_STARTED') {
    return {
      stage_item_input1_score: '#868e96',
      stage_item_input2_score: '#868e96',
      textColor: 'white',
    };
  }

  const winColor = '#2a8f37';
  const drawColor = '#656565';
  const loseColor = '#af4034';
  return {
    stage_item_input1_score:
      match.stage_item_input1_score > match.stage_item_input2_score
        ? winColor
        : match.stage_item_input1_score === match.stage_item_input2_score
          ? drawColor
          : loseColor,
    stage_item_input2_score:
      match.stage_item_input2_score > match.stage_item_input1_score
        ? winColor
        : match.stage_item_input1_score === match.stage_item_input2_score
          ? drawColor
          : loseColor,
    textColor: 'white',
  };
}

export function formatMatchInput1(
  t: Translator,
  stageItemsLookup: any,
  matchesLookup: any,
  match: MatchWithDetails
): string {
  const formatted = formatStageItemInput(match.stage_item_input1, stageItemsLookup);
  if (formatted != null) return formatted;

  if (match.stage_item_input1_winner_from_match_id == null) {
    return t('empty_slot');
  }
  const winner = matchesLookup[match.stage_item_input1_winner_from_match_id].match;
  const match_1 = formatMatchInput1(t, stageItemsLookup, matchesLookup, winner);
  const match_2 = formatMatchInput2(t, stageItemsLookup, matchesLookup, winner);
  return `Winner of match ${match_1} - ${match_2}`;
}

export function formatMatchInput2(
  t: Translator,
  stageItemsLookup: any,
  matchesLookup: any,
  match: MatchWithDetails
): string {
  const formatted = formatStageItemInput(match.stage_item_input2, stageItemsLookup);
  if (formatted != null) return formatted;

  if (match.stage_item_input2_winner_from_match_id == null) {
    return t('empty_slot');
  }
  const winner = matchesLookup[match.stage_item_input2_winner_from_match_id].match;
  const match_1 = formatMatchInput1(t, stageItemsLookup, matchesLookup, winner);
  const match_2 = formatMatchInput2(t, stageItemsLookup, matchesLookup, winner);
  return `Winner of match ${match_1} - ${match_2}`;
}
