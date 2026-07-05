import { performMutation } from './adapter';

export async function createPlayer(tournament_id: number, name: string, active: boolean) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/players`,
    { name, active },
    {
      tournamentId: tournament_id,
    }
  );
}

export async function createMultiplePlayers(tournament_id: number, names: string, active: boolean) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/players_multi`,
    { names, active },
    { tournamentId: tournament_id }
  );
}

export async function deletePlayer(tournament_id: number, player_id: number) {
  return performMutation('delete', `tournaments/${tournament_id}/players/${player_id}`, undefined, {
    tournamentId: tournament_id,
  });
}

export async function updatePlayer(
  tournament_id: number,
  player_id: number,
  name: string,
  active: boolean
) {
  // The backend updates name + active only, and no issue counter filters on `active`, so this
  // cannot change an issue count and skips invalidation.
  return performMutation(
    'put',
    `tournaments/${tournament_id}/players/${player_id}`,
    { name, active },
    { invalidateIssues: false }
  );
}
