import { createAxios, handleRequestError } from './adapter';

export async function createTournament(
  club_id: number,
  name: string,
  dashboard_public: boolean,
  dashboard_endpoint: string,
  players_can_be_in_multiple_teams: boolean,
  auto_assign_courts: boolean,
  start_time: string,
  duration_minutes: number,
  margin_minutes: number,
  signup_enabled: boolean = false,
  max_team_size: number = 4,
  signup_team_choice_enabled: boolean = true,
  score_tracking_enabled: boolean = false,
  levels: string[] | null = null
) {
  return createAxios()
    .post('tournaments', {
      name,
      club_id,
      dashboard_public,
      dashboard_endpoint,
      players_can_be_in_multiple_teams,
      auto_assign_courts,
      start_time,
      duration_minutes,
      margin_minutes,
      signup_enabled,
      max_team_size,
      signup_team_choice_enabled,
      score_tracking_enabled,
      levels,
    })
    .catch((response: any) => handleRequestError(response));
}

export async function deleteTournament(tournament_id: number) {
  return createAxios().delete(`tournaments/${tournament_id}`);
}

export async function archiveTournament(tournament_id: number) {
  return createAxios().post(`tournaments/${tournament_id}/change-status`, { status: 'ARCHIVED' });
}

export async function unarchiveTournament(tournament_id: number) {
  return createAxios().post(`tournaments/${tournament_id}/change-status`, { status: 'OPEN' });
}

export async function updateTournament(
  tournament_id: number,
  name: string,
  dashboard_public: boolean,
  dashboard_endpoint: string | null | undefined,
  players_can_be_in_multiple_teams: boolean,
  auto_assign_courts: boolean,
  start_time: string,
  duration_minutes: number,
  margin_minutes: number,
  signup_enabled: boolean,
  max_team_size: number,
  signup_team_choice_enabled: boolean,
  score_tracking_enabled: boolean,
  rules: string | null
) {
  return createAxios()
    .put(`tournaments/${tournament_id}`, {
      name,
      dashboard_public,
      dashboard_endpoint,
      players_can_be_in_multiple_teams,
      auto_assign_courts,
      start_time,
      duration_minutes,
      margin_minutes,
      signup_enabled,
      max_team_size,
      signup_team_choice_enabled,
      score_tracking_enabled,
      rules,
    })
    .catch((response: any) => handleRequestError(response));
}
