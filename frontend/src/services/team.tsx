import { createAxios, handleRequestError } from './adapter';

export async function createTeam(
  tournament_id: number,
  name: string,
  active: boolean,
  player_ids: string[],
  level_id: number | null
) {
  return createAxios().post(`tournaments/${tournament_id}/teams`, {
    name,
    active,
    player_ids,
    level_id,
  });
}

export async function createTeams(
  tournament_id: number,
  names: string,
  active: boolean,
  level_id: number | null
) {
  return createAxios().post(`tournaments/${tournament_id}/teams_multi`, {
    names,
    active,
    level_id,
  });
}

export async function deleteTeam(tournament_id: number, team_id: number) {
  await createAxios()
    .delete(`tournaments/${tournament_id}/teams/${team_id}`)
    .catch((response: any) => handleRequestError(response));
}

export async function updateTeam(
  tournament_id: number,
  team_id: number,
  name: string,
  active: boolean,
  player_ids: string[],
  level_id: number | null
) {
  return createAxios().put(`tournaments/${tournament_id}/teams/${team_id}`, {
    name,
    active,
    player_ids,
    level_id,
  });
}
