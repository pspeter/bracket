import { createAxios, handleRequestError } from './adapter';

export async function createRound(tournament_id: number, stage_item_id: number) {
  return createAxios()
    .post(`tournaments/${tournament_id}/rounds`, {
      stage_item_id,
    })
    .catch((response: any) => handleRequestError(response));
}

export async function deleteRound(tournament_id: number, round_id: number) {
  return createAxios()
    .delete(`tournaments/${tournament_id}/rounds/${round_id}`)
    .catch((response: any) => handleRequestError(response));
}

export async function updateRound(
  tournament_id: number,
  round_id: number,
  name: string,
  lifecycle_state: string
) {
  return createAxios()
    .put(`tournaments/${tournament_id}/rounds/${round_id}`, { name, lifecycle_state })
    .catch((response: any) => handleRequestError(response));
}
