import { MatchSet } from '@openapi';

export type ScoreTrackingViewState =
  | { kind: 'not_started' }
  | { kind: 'playing'; set: MatchSet }
  | { kind: 'between_sets'; completed: MatchSet; next: MatchSet; allSets: MatchSet[] }
  | { kind: 'completed' };

export function getScoreTrackingViewState(sets: MatchSet[]): ScoreTrackingViewState {
  const inProgress = sets.find((s) => s.state === 'IN_PROGRESS');
  if (inProgress) return { kind: 'playing', set: inProgress };

  const lastCompleted = [...sets].reverse().find((s) => s.state === 'COMPLETED');
  const nextNotStarted = sets.find((s) => s.state === 'NOT_STARTED');

  if (lastCompleted && nextNotStarted) {
    return { kind: 'between_sets', completed: lastCompleted, next: nextNotStarted, allSets: sets };
  }
  if (sets.every((s) => s.state === 'NOT_STARTED')) {
    return { kind: 'not_started' };
  }
  return { kind: 'completed' };
}

export function isEndSetDisabled(
  set: MatchSet,
  match: {
    two_point_advantage: boolean;
    max_points: number;
    last_set_max_points: number | null;
    num_sets: number;
  },
  isSwapped: boolean
): boolean {
  const { two_point_advantage, max_points, last_set_max_points, num_sets } = match;
  const limit =
    set.set_number === num_sets && last_set_max_points != null ? last_set_max_points : max_points;
  const s1 = isSwapped ? set.stage_item_input2_score : set.stage_item_input1_score;
  const s2 = isSwapped ? set.stage_item_input1_score : set.stage_item_input2_score;
  const maxScore = Math.max(s1, s2);
  if (maxScore < limit) return true;
  if (two_point_advantage && Math.abs(s1 - s2) < 2) return true;
  return false;
}
