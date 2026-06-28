import { createAxios, handleRequestError, mutateIssues } from './adapter';

export async function createStageItem(
  tournament_id: number,
  stage_id: number,
  type: string,
  team_count: number,
  ranking_id: number,
  games_per_player: number | null = null
) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/stage_items`, {
      stage_id,
      type,
      team_count,
      ranking_id,
      games_per_player,
    })
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function updateStageItem(
  tournament_id: number,
  stage_item_id: number,
  name: string,
  ranking_id: string,
  team_count: number,
  games_per_player: number | null = null
) {
  const response = await createAxios()
    .put(`tournaments/${tournament_id}/stage_items/${stage_item_id}`, {
      name,
      ranking_id,
      team_count,
      games_per_player,
    })
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function deleteStageItem(tournament_id: number, stage_item_id: number) {
  const response = await createAxios()
    .delete(`tournaments/${tournament_id}/stage_items/${stage_item_id}`)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}
