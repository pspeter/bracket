import {
  MatchBody,
  MatchCreateBodyFrontend,
  MatchRescheduleBody,
  MatchResizeBreakBody,
  MatchSetBody,
  MatchSetScoreEditBody,
  MatchSwapBody,
  SchedulerWeights,
  ScoreTrackingInfoResponse,
} from '@openapi';
import { createAxios, handleRequestError, mutateIssues } from './adapter';

export async function createMatch(tournament_id: number, match: MatchCreateBodyFrontend) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/matches`, match)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function deleteMatch(tournament_id: number, match_id: number) {
  const response = await createAxios()
    .delete(`tournaments/${tournament_id}/matches/${match_id}`)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function updateMatch(
  tournament_id: number,
  match_id: number,
  match: Omit<MatchBody, 'referee_stage_item_input_id' | 'referee_name'> &
    Partial<Pick<MatchBody, 'referee_stage_item_input_id' | 'referee_name'>>
) {
  const response = await createAxios()
    .put(`tournaments/${tournament_id}/matches/${match_id}`, match)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

// Scores live on sets now. Updating a single set is the unit of change for both the
// authenticated match modal and the token-authenticated score-tracking screens.
export async function updateMatchSet(
  tournament_id: number,
  match_id: number,
  set_id: number,
  body: MatchSetBody
) {
  const response = await createAxios()
    .put(`tournaments/${tournament_id}/matches/${match_id}/sets/${set_id}`, body)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function scoreEditMatchSet(
  tournament_id: number,
  match_id: number,
  set_id: number,
  body: MatchSetScoreEditBody
) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/matches/${match_id}/sets/${set_id}/score-edit`, body)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function startMatch(tournament_id: number, match_id: number) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/matches/${match_id}/start`)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function endMatch(tournament_id: number, match_id: number) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/matches/${match_id}/end`)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function reopenMatch(tournament_id: number, match_id: number) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/matches/${match_id}/reopen`)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function resetMatch(tournament_id: number, match_id: number) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/matches/${match_id}/reset`)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function scoreEditScoreTrackingMatchSet(
  score_tracking_token: string,
  tournament_id: number | null,
  match_id: number,
  set_id: number,
  body: MatchSetScoreEditBody
) {
  const response = await createAxios()
    .post(
      `score-tracking/${score_tracking_token}/matches/${match_id}/sets/${set_id}/score-edit`,
      body
    )
    .catch((response: any) => handleRequestError(response));
  const tournamentId =
    tournament_id ?? (await getTournamentIdForScoreTrackingToken(score_tracking_token));
  if (tournamentId != null) {
    await mutateIssues(tournamentId);
  }
  return response;
}

export async function startScoreTrackingMatch(
  score_tracking_token: string,
  tournament_id: number | null,
  match_id: number
) {
  const response = await createAxios()
    .post(`score-tracking/${score_tracking_token}/matches/${match_id}/start`)
    .catch((response: any) => handleRequestError(response));
  const tournamentId =
    tournament_id ?? (await getTournamentIdForScoreTrackingToken(score_tracking_token));
  if (tournamentId != null) {
    await mutateIssues(tournamentId);
  }
  return response;
}

export async function endScoreTrackingMatch(
  score_tracking_token: string,
  tournament_id: number | null,
  match_id: number
) {
  const response = await createAxios()
    .post(`score-tracking/${score_tracking_token}/matches/${match_id}/end`)
    .catch((response: any) => handleRequestError(response));
  const tournamentId =
    tournament_id ?? (await getTournamentIdForScoreTrackingToken(score_tracking_token));
  if (tournamentId != null) {
    await mutateIssues(tournamentId);
  }
  return response;
}

export async function reopenScoreTrackingMatch(
  score_tracking_token: string,
  tournament_id: number | null,
  match_id: number
) {
  const response = await createAxios()
    .post(`score-tracking/${score_tracking_token}/matches/${match_id}/reopen`)
    .catch((response: any) => handleRequestError(response));
  const tournamentId =
    tournament_id ?? (await getTournamentIdForScoreTrackingToken(score_tracking_token));
  if (tournamentId != null) {
    await mutateIssues(tournamentId);
  }
  return response;
}

export async function updateScoreTrackingMatchSet(
  score_tracking_token: string,
  tournament_id: number | null,
  match_id: number,
  set_id: number,
  body: MatchSetBody
) {
  const response = await createAxios()
    .put(`score-tracking/${score_tracking_token}/matches/${match_id}/sets/${set_id}`, body)
    .catch((response: any) => handleRequestError(response));
  const tournamentId =
    tournament_id ?? (await getTournamentIdForScoreTrackingToken(score_tracking_token));
  if (tournamentId != null) {
    await mutateIssues(tournamentId);
  }
  return response;
}

async function getTournamentIdForScoreTrackingToken(score_tracking_token: string) {
  const response = await createAxios()
    .get<ScoreTrackingInfoResponse>(`score-tracking/${score_tracking_token}`)
    .catch((response: any) => handleRequestError(response));

  return response?.data.data.tournament_id;
}

// The planner's scheduling mutations let errors propagate instead of handling
// them here: the planner must see failures (in particular the 409 stale-write
// rejection when another device moved a match concurrently) to refetch the
// schedule and clear the selection.

export async function unscheduleMatch(tournament_id: number, match_id: number) {
  const response = await createAxios().post(
    `tournaments/${tournament_id}/matches/${match_id}/unschedule`
  );
  await mutateIssues(tournament_id);
  return response;
}

export async function rescheduleMatch(
  tournament_id: number,
  match_id: number,
  match: MatchRescheduleBody
) {
  const response = await createAxios().post(
    `tournaments/${tournament_id}/matches/${match_id}/reschedule`,
    match
  );
  await mutateIssues(tournament_id);
  return response;
}

export async function swapMatches(tournament_id: number, body: MatchSwapBody) {
  const response = await createAxios().post(`tournaments/${tournament_id}/matches/swap`, body);
  await mutateIssues(tournament_id);
  return response;
}

export async function resizeMatchBreak(
  tournament_id: number,
  match_id: number,
  body: MatchResizeBreakBody
) {
  const response = await createAxios().post(
    `tournaments/${tournament_id}/matches/${match_id}/resize_break`,
    body
  );
  await mutateIssues(tournament_id);
  return response;
}

export async function autoAssignReferees(tournament_id: number, weights?: SchedulerWeights) {
  return createAxios()
    .post(`tournaments/${tournament_id}/matches/auto-assign-referees`, weights)
    .catch((response: any) => handleRequestError(response));
}

export async function scheduleMatches(tournament_id: number, weights?: SchedulerWeights) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/schedule_matches`, weights)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}

export async function reoptimizeMatches(tournament_id: number, weights?: SchedulerWeights) {
  const response = await createAxios()
    .post(`tournaments/${tournament_id}/reoptimize_matches`, weights)
    .catch((response: any) => handleRequestError(response));
  await mutateIssues(tournament_id);
  return response;
}
