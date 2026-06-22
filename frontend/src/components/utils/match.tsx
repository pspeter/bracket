import { MatchWithDetails } from '@openapi';
import dayjs from 'dayjs';
import { formatStageItemInput } from './stage_item_input';
import { Translator } from './types';

export function getMatchStartTime(match: MatchWithDetails) {
  return dayjs(match.start_time || '');
}

export function getMatchEndTime(match: MatchWithDetails) {
  return getMatchStartTime(match).add(match.duration_minutes, 'minutes');
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

/**
 * Whether the given team is involved in the match: as one of the two (already determined)
 * participants, or — when `includeReferee` is set — as the assigned referee.
 */
export function matchHasTeam(match: MatchWithDetails, teamId: number, includeReferee = false) {
  return (
    match.stage_item_input1?.team_id === teamId ||
    match.stage_item_input2?.team_id === teamId ||
    (includeReferee && match.referee?.team_id === teamId)
  );
}

export function isMatchInTheFutureOrPresent(match: MatchWithDetails) {
  return getMatchEndTime(match) > dayjs();
}

export function isMatchInTheFuture(match: MatchWithDetails) {
  return getMatchStartTime(match) > dayjs();
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
