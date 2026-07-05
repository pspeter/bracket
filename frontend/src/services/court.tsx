import { performMutation } from './adapter';

// NOTE: neither of these has ever invalidated tournament issues, though courts can plausibly
// affect scheduling-related issues (e.g. "no courts assigned"). Looks like a pre-existing
// omission rather than a deliberate one -- preserved as-is and flagged for the architect.

export async function createCourt(tournament_id: number, name: string) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/courts`,
    { name },
    {
      invalidateIssues: false,
    }
  );
}

export async function deleteCourt(tournament_id: number, court_id: number) {
  return performMutation('delete', `tournaments/${tournament_id}/courts/${court_id}`, undefined, {
    invalidateIssues: false,
  });
}
