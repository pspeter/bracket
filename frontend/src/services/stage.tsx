import { createAxios, handleRequestError, mutateIssues } from './adapter';

export type StageTemplateCreateBody = {
  groups: 2 | 3 | 4;
  total_teams: number;
  until_rank: 'all' | number;
  include_semi_final?: boolean;
  level_id?: number | null;
};

export async function createStagesFromTemplate(
  tournament_id: number,
  body: StageTemplateCreateBody
) {
  const response = await createAxios().post(
    `tournaments/${tournament_id}/stages/from-template`,
    body
  );
  await mutateIssues(tournament_id);
  return response;
}

export async function createStage(tournament_id: number, level_id: number | null = null) {
  return createAxios()
    .post(`tournaments/${tournament_id}/stages`, { level_id })
    .catch((response: any) => handleRequestError(response));
}

export async function updateStage(tournament_id: number, stage_id: number, name: string) {
  return createAxios()
    .put(`tournaments/${tournament_id}/stages/${stage_id}`, { name })
    .catch((response: any) => handleRequestError(response));
}

export async function setRankingForStageItems(
  tournament_id: number,
  stage_id: number,
  ranking_id: number
) {
  return createAxios()
    .put(`tournaments/${tournament_id}/stages/${stage_id}/ranking`, { ranking_id })
    .catch((response: any) => handleRequestError(response));
}

export async function deleteStage(tournament_id: number, stage_id: number) {
  const response = await createAxios()
    .delete(`tournaments/${tournament_id}/stages/${stage_id}`)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}
