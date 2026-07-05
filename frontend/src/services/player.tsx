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
  active: boolean,
  team_id: string | null
) {
  // NOTE: unlike create/delete above, this has never invalidated tournament issues. Toggling
  // `active` or moving a player between teams can plausibly change issue counts, so this looks
  // like an accidental omission rather than a deliberate one -- preserved as-is and flagged.
  return performMutation(
    'put',
    `tournaments/${tournament_id}/players/${player_id}`,
    { name, active, team_id },
    { invalidateIssues: false }
  );
}
