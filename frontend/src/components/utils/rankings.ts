import { Ranking } from '@openapi';

import { Translator } from './types';

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
