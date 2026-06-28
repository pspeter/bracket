import { createAxios, handleRequestError, mutateIssues } from './adapter';

export async function createPlayer(tournament_id: number, name: string, active: boolean) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/players`, { name, active })
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function createMultiplePlayers(tournament_id: number, names: string, active: boolean) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/players_multi`, { names, active })
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function deletePlayer(tournament_id: number, player_id: number) {
  const response = await createAxios()
    .delete(`tournaments/${tournament_id}/players/${player_id}`)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function updatePlayer(
  tournament_id: number,
  player_id: number,
  name: string,
  active: boolean,
  team_id: string | null
) {
  return createAxios()
    .put(`tournaments/${tournament_id}/players/${player_id}`, {
      name,
      active,
      team_id,
    })
    .catch((response: any) => handleRequestError(response));
}
