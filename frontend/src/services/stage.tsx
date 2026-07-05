import { performMutation } from './adapter';

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
  // The caller (create_from_template_modal.tsx) chains its own try/catch around this and must
  // see the rejection -- errors are intentionally left uncaught here, as before.
  return performMutation('post', `tournaments/${tournament_id}/stages/from-template`, body, {
    tournamentId: tournament_id,
    catchErrors: false,
  });
}

export async function createStage(tournament_id: number, level_id: number | null = null) {
  // A freshly created stage has no stage items yet, so it cannot itself introduce issues.
  return performMutation(
    'post',
    `tournaments/${tournament_id}/stages`,
    { level_id },
    {
      invalidateIssues: false,
    }
  );
}

export async function updateStage(tournament_id: number, stage_id: number, name: string) {
  // Rename only -- cannot affect issue counts.
  return performMutation(
    'put',
    `tournaments/${tournament_id}/stages/${stage_id}`,
    { name },
    {
      invalidateIssues: false,
    }
  );
}

export async function setRankingForStageItems(
  tournament_id: number,
  stage_id: number,
  ranking_id: number
) {
  // Changing a stage's ranking resizes match sets (which feeds the overdue-match issue
  // counters) and reconciles its stage items, which can reassign dependent-input teams
  // (which feeds the unassigned-teams counter) -- so invalidate issues.
  return performMutation(
    'put',
    `tournaments/${tournament_id}/stages/${stage_id}/ranking`,
    { ranking_id },
    { tournamentId: tournament_id }
  );
}

export async function deleteStage(tournament_id: number, stage_id: number) {
  return performMutation('delete', `tournaments/${tournament_id}/stages/${stage_id}`, undefined, {
    tournamentId: tournament_id,
  });
}
