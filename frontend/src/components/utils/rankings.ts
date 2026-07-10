import { Ranking, ScoringType } from '@openapi';

import { Translator } from './types';

/**
 * The default for "Play out all sets" per scoring type, mirroring the backend's creation
 * defaults: only "set points" scoring gives every set intrinsic standings value, so only
 * there do all sets play out by default.
 */
export function getPlayAllSetsDefault(scoringType: ScoringType): boolean {
  return scoringType === 'SET_POINTS';
}

/**
 * Best-of-n mode is active whenever "play out all sets" is off and there is more than one
 * set: a match then completes as soon as one side reaches a set-win majority. In that mode
 * `draws_allowed` is forced off and `num_sets` must be odd, both enforced by the backend and
 * mirrored here so the form can show the same invariant before saving.
 */
export function isBestOfNMode(playAllSets: boolean, numSets: number): boolean {
  return !playAllSets && numSets > 1;
}

/**
 * The label shown for a ranking. Uses the ranking's custom name when one is set,
 * otherwise falls back to the positional default "Ranking <position + 1>".
 */
export function getRankingTitle(ranking: Ranking, t: Translator): string {
  const name = ranking.name?.trim();
  if (name) {
    return name;
  }
  return `${t('ranking_title')} ${ranking.position + 1}`;
}
