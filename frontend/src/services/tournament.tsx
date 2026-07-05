import { performMutation } from './adapter';

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
  min_team_size: number = 0,
  signup_team_choice_enabled: boolean = true,
  score_tracking_enabled: boolean = false,
  referees_enabled: boolean = false,
  levels: string[] | null = null
) {
  // No tournament id exists yet, so there's nothing to invalidate.
  return performMutation(
    'post',
    'tournaments',
    {
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
      min_team_size,
      signup_team_choice_enabled,
      score_tracking_enabled,
      referees_enabled,
      levels,
    },
    { invalidateIssues: false }
  );
}

export async function deleteTournament(tournament_id: number) {
  // The caller (settings.tsx) chains its own .then/.catch on this promise and must see the
  // rejection to skip navigating away on failure -- errors are intentionally left uncaught here.
  return performMutation('delete', `tournaments/${tournament_id}`, undefined, {
    invalidateIssues: false,
    catchErrors: false,
  });
}

export async function archiveTournament(tournament_id: number) {
  // The caller (settings.tsx) attaches its own .catch(handleRequestError) -- errors are
  // intentionally left uncaught here, as before.
  return performMutation(
    'post',
    `tournaments/${tournament_id}/change-status`,
    { status: 'ARCHIVED' },
    { invalidateIssues: false, catchErrors: false }
  );
}

export async function unarchiveTournament(tournament_id: number) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/change-status`,
    { status: 'OPEN' },
    { invalidateIssues: false, catchErrors: false }
  );
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
  min_team_size: number,
  signup_team_choice_enabled: boolean,
  score_tracking_enabled: boolean,
  referees_enabled: boolean,
  rules: string | null
) {
  // NOTE: the original implementation only invalidated issues on the success branch of a
  // .then/.catch chain, skipping invalidation entirely when the update failed -- unlike every
  // other mutation in this codebase, which invalidates unconditionally once the request settles.
  // That read as an accidental one-off inconsistency rather than deliberate design, so this now
  // uses the standard unconditional-invalidation behavior used everywhere else. Flagged for the
  // architect to confirm.
  return performMutation(
    'put',
    `tournaments/${tournament_id}`,
    {
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
      min_team_size,
      signup_team_choice_enabled,
      score_tracking_enabled,
      referees_enabled,
      rules,
    },
    { tournamentId: tournament_id }
  );
}
