import { ScoringType } from '@openapi';

import { createAxios, handleRequestError } from './adapter';

export async function createRanking(tournament_id: number) {
  return createAxios()
    .post(`tournaments/${tournament_id}/rankings`, { scoring_type: 'MATCH_POINTS' })
    .catch((response: any) => handleRequestError(response));
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
  return createAxios()
    .put(`tournaments/${tournament_id}/rankings/${ranking_id}`, body)
    .catch((response: any) => handleRequestError(response));
}

export async function deleteRanking(tournament_id: number, ranking_id: number) {
  return createAxios()
    .delete(`tournaments/${tournament_id}/rankings/${ranking_id}`)
    .catch((response: any) => handleRequestError(response));
}
