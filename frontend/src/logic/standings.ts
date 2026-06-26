import type { ScoringType } from '@openapi';

export function formatDifference(value: number): string {
  return value >= 0 ? `+${value}` : `${value}`;
}

export function getWinsColumnKey(scoringType: ScoringType | null): string {
  if (scoringType === 'SET_POINTS' || scoringType === 'SET_POINTS_WITH_MATCH_BONUS') {
    return 'sets_won_label';
  }
  return 'matches_won_label';
}
