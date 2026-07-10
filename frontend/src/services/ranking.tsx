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
  // Both flags must always be sent: the backend's per-scoring-type body defaults would
  // otherwise silently overwrite the stored values on save.
  play_all_sets: boolean,
  draws_allowed: boolean,
  name: string,
  win_points?: string,
  draw_points?: string,
  loss_points?: string,
  match_bonus_points?: string,
  // A `num_sets` or `play_all_sets` change on a ranking with in-progress or completed sets is
  // rejected with a 409 unless this is set: both can rewrite existing matches' derived state
  // (resizing set rows, or instantly completing/regressing best-of-n matches). The caller
  // (EditRankingForm) submits with `force` false first, and only retries with it true once the
  // organizer has confirmed the 409 through the force-confirm modal.
  force: boolean = false
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
    play_all_sets,
    draws_allowed,
  };
  if (scoring_type === 'MATCH_POINTS') {
    body.win_points = win_points;
    body.draw_points = draw_points;
    body.loss_points = loss_points;
  } else if (scoring_type === 'SET_POINTS_WITH_MATCH_BONUS') {
    body.match_bonus_points = match_bonus_points;
  }
  const url = `tournaments/${tournament_id}/rankings/${ranking_id}${force ? '?force=true' : ''}`;
  // A ranking edit reconciles every stage item using it, which can reassign dependent-input
  // teams (the unassigned-teams issue counter) and resize match sets (the overdue counters) --
  // so invalidate issues.
  //
  // catchErrors is off so the caller (EditRankingForm) can see a 409 and prompt for `force`
  // instead of it being swallowed by the default handleRequestError notification.
  return performMutation('put', url, body, {
    tournamentId: tournament_id,
    catchErrors: false,
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
