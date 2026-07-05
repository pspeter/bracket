import { performMutation } from './adapter';

// createTeam/createTeams/updateTeam intentionally let AxiosError propagate: their callers
// (team_create_modal.tsx, team_update_modal.tsx) catch `instanceof AxiosError` themselves to
// show tailored notifications (e.g. "this team is full") before falling back to
// handleRequestError.

export async function createTeam(
  tournament_id: number,
  name: string,
  active: boolean,
  player_ids: string[],
  level_id: number | null
) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/teams`,
    { name, active, player_ids, level_id },
    { tournamentId: tournament_id, catchErrors: false }
  );
}

export async function createTeams(
  tournament_id: number,
  names: string,
  active: boolean,
  level_id: number | null
) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/teams_multi`,
    { names, active, level_id },
    { tournamentId: tournament_id, catchErrors: false }
  );
}

export async function deleteTeam(tournament_id: number, team_id: number) {
  await performMutation('delete', `tournaments/${tournament_id}/teams/${team_id}`, undefined, {
    tournamentId: tournament_id,
  });
}

export async function updateTeam(
  tournament_id: number,
  team_id: number,
  name: string,
  active: boolean,
  player_ids: string[],
  level_id: number | null
) {
  return performMutation(
    'put',
    `tournaments/${tournament_id}/teams/${team_id}`,
    { name, active, player_ids, level_id },
    { tournamentId: tournament_id, catchErrors: false }
  );
}
