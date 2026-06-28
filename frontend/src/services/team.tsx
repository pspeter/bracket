import { createAxios, handleRequestError, mutateIssues } from './adapter';

export async function createTeam(
  tournament_id: number,
  name: string,
  active: boolean,
  player_ids: string[],
  level_id: number | null
) {
  const response = await createAxios().post(`tournaments/${tournament_id}/teams`, {
    name,
    active,
    player_ids,
    level_id,
  });
  await mutateIssues(tournament_id);
  return response;
}

export async function createTeams(
  tournament_id: number,
  names: string,
  active: boolean,
  level_id: number | null
) {
  const response = await createAxios().post(`tournaments/${tournament_id}/teams_multi`, {
    names,
    active,
    level_id,
  });
  await mutateIssues(tournament_id);
  return response;
}

export async function deleteTeam(tournament_id: number, team_id: number) {
  await createAxios()
    .delete(`tournaments/${tournament_id}/teams/${team_id}`)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
}

export async function updateTeam(
  tournament_id: number,
  team_id: number,
  name: string,
  active: boolean,
  player_ids: string[],
  level_id: number | null
) {
  const response = await createAxios().put(`tournaments/${tournament_id}/teams/${team_id}`, {
    name,
    active,
    player_ids,
    level_id,
  });
  await mutateIssues(tournament_id);
  return response;
}
