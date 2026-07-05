import { performMutation } from './adapter';

export async function createStageItem(
  tournament_id: number,
  stage_id: number,
  type: string,
  team_count: number,
  ranking_id: number,
  games_per_player: number | null = null
) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/stage_items`,
    { stage_id, type, team_count, ranking_id, games_per_player },
    { tournamentId: tournament_id }
  );
}

export async function updateStageItem(
  tournament_id: number,
  stage_item_id: number,
  name: string,
  ranking_id: string,
  team_count: number,
  games_per_player: number | null = null
) {
  return performMutation(
    'put',
    `tournaments/${tournament_id}/stage_items/${stage_item_id}`,
    { name, ranking_id, team_count, games_per_player },
    { tournamentId: tournament_id }
  );
}

export async function deleteStageItem(tournament_id: number, stage_item_id: number) {
  return performMutation(
    'delete',
    `tournaments/${tournament_id}/stage_items/${stage_item_id}`,
    undefined,
    { tournamentId: tournament_id }
  );
}
