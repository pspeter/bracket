import { performMutation } from './adapter';

// No tournament-issue counter involves courts, and the backend refuses to delete a court
// that is used by any match (so deletion can never unschedule anything) -- neither mutation
// can change an issue count, so both skip invalidation.

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
