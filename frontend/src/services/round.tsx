import { performMutation } from './adapter';

export async function createRound(tournament_id: number, stage_item_id: number) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/rounds`,
    { stage_item_id },
    {
      tournamentId: tournament_id,
    }
  );
}

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
  // NOTE: create/delete above invalidate issues; this update (rename + lifecycle_state change,
  // e.g. activating a round) never has. Lifecycle changes can plausibly affect issue counts, so
  // this looks like an accidental omission rather than a deliberate one -- preserved as-is and
  // flagged for the architect.
  return performMutation(
    'put',
    `tournaments/${tournament_id}/rounds/${round_id}`,
    { name, lifecycle_state },
    { invalidateIssues: false }
  );
}
