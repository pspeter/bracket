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
