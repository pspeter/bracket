import { ScoringType } from '@openapi';

import { performMutation } from './adapter';

// createRanking adds a ranking nothing references yet and deleteRanking only affects
// unreferenced rankings; neither can change any issue counter, so both skip invalidation.
// editRanking reconciles stage items and therefore invalidates (see below).

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
  // A ranking edit reconciles every stage item using it, which can reassign dependent-input
  // teams (the unassigned-teams issue counter) and resize match sets (the overdue counters) --
  // so invalidate issues.
  return performMutation('put', `tournaments/${tournament_id}/rankings/${ranking_id}`, body, {
    tournamentId: tournament_id,
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
