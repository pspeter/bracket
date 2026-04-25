import { createAxios, handleRequestError } from './adapter';

export type StageTemplateCreateBody = {
  groups: 2 | 4;
  total_teams: number;
  until_rank: 'all' | number;
  include_semi_final?: boolean;
};

export async function createStagesFromTemplate(
  tournament_id: number,
  body: StageTemplateCreateBody,
) {
  return createAxios().post(`tournaments/${tournament_id}/stages/from-template`, body);
}

export async function createStage(tournament_id: number) {
  return createAxios()
    .post(`tournaments/${tournament_id}/stages`)
    .catch((response: any) => handleRequestError(response));
}

export async function updateStage(tournament_id: number, stage_id: number, name: string) {
  return createAxios()
    .put(`tournaments/${tournament_id}/stages/${stage_id}`, { name })
    .catch((response: any) => handleRequestError(response));
}

export async function activateNextStage(tournament_id: number, direction: string) {
  return createAxios()
    .post(`tournaments/${tournament_id}/stages/activate`, { direction })
    .catch((response: any) => handleRequestError(response));
}

export async function deleteStage(tournament_id: number, stage_id: number) {
  return createAxios()
    .delete(`tournaments/${tournament_id}/stages/${stage_id}`)
    .catch((response: any) => handleRequestError(response));
}
