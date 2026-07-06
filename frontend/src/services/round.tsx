import { performMutation } from './adapter';

export async function deleteRound(tournament_id: number, round_id: number) {
  return performMutation('delete', `tournaments/${tournament_id}/rounds/${round_id}`, undefined, {
    tournamentId: tournament_id,
  });
}

export async function updateRound(
  tournament_id: number,
  round_id: number,
  name: string,
  lifecycle_state: string
) {
  // The backend performs a bare UPDATE of name + lifecycle_state with no cascade, and no
  // issue counter reads round lifecycle -- this cannot change an issue count, so it skips
  // invalidation.
  return performMutation(
    'put',
    `tournaments/${tournament_id}/rounds/${round_id}`,
    { name, lifecycle_state },
    { invalidateIssues: false }
  );
}
