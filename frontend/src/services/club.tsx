import { performMutation } from './adapter';

export async function createClub(name: string) {
  // Clubs aren't tournament-scoped, so there's no tournament-issues key to invalidate.
  return performMutation('post', 'clubs', { name }, { invalidateIssues: false });
}

export async function deleteClub(club_id: number) {
  return performMutation('delete', `clubs/${club_id}`, undefined, { invalidateIssues: false });
}

export async function updateClub(club_id: number, name: string) {
  return performMutation('put', `clubs/${club_id}`, { name }, { invalidateIssues: false });
}
