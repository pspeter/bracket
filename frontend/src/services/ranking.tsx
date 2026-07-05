import { ScoringType } from '@openapi';

import { performMutation } from './adapter';

// NOTE: none of these three has ever invalidated tournament issues (consistent across this
// file, unlike e.g. player.tsx/round.tsx where only one sibling function omits it). Ranking
// changes can plausibly affect standings-derived issues, so this is still worth the architect
// double-checking, but the consistency within the file makes it read more like a deliberate
// choice than an accident.

export async function createRanking(tournament_id: number) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/rankings`,
    { scoring_type: 'MATCH_POINTS' },
    { invalidateIssues: false }
  );
}

export async function editRanking(
  tournament_id: number,
  ranking_id: number,
  scoring_type: ScoringType,
  position: number,
  side_switch_every_n_points: number | null,
  num_sets: number,
  max_points: number,
  last_set_max_points: number | null,
  two_point_advantage: boolean,
  name: string,
  win_points?: string,
  draw_points?: string,
  loss_points?: string,
  match_bonus_points?: string
) {
  const body: Record<string, unknown> = {
    scoring_type,
    position,
    name,
    side_switch_every_n_points,
    num_sets,
    max_points,
    last_set_max_points,
    two_point_advantage,
  };
  if (scoring_type === 'MATCH_POINTS') {
    body.win_points = win_points;
    body.draw_points = draw_points;
    body.loss_points = loss_points;
  } else if (scoring_type === 'SET_POINTS_WITH_MATCH_BONUS') {
    body.match_bonus_points = match_bonus_points;
  }
  return performMutation('put', `tournaments/${tournament_id}/rankings/${ranking_id}`, body, {
    invalidateIssues: false,
  });
}

export async function deleteRanking(tournament_id: number, ranking_id: number) {
  return performMutation(
    'delete',
    `tournaments/${tournament_id}/rankings/${ranking_id}`,
    undefined,
    { invalidateIssues: false }
  );
}
