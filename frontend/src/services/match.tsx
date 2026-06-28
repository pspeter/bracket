import {
  MatchBody,
  MatchCreateBodyFrontend,
  MatchRescheduleBody,
  MatchResizeBreakBody,
  MatchSetBody,
  MatchSwapBody,
  SchedulerWeights,
} from '@openapi';
import { createAxios, handleRequestError, mutateIssues } from './adapter';

export async function createMatch(tournament_id: number, match: MatchCreateBodyFrontend) {
  return createAxios()
    .post(`tournaments/${tournament_id}/matches`, match)
    .catch((response: any) => handleRequestError(response));
}

export async function deleteMatch(tournament_id: number, match_id: number) {
  return createAxios()
    .delete(`tournaments/${tournament_id}/matches/${match_id}`)
    .catch((response: any) => handleRequestError(response));
}

export async function updateMatch(
  tournament_id: number,
  match_id: number,
  match: Omit<MatchBody, 'referee_stage_item_input_id' | 'referee_name'> &
    Partial<Pick<MatchBody, 'referee_stage_item_input_id' | 'referee_name'>>
) {
  return createAxios()
    .put(`tournaments/${tournament_id}/matches/${match_id}`, match)
    .catch((response: any) => handleRequestError(response));
}

// Scores live on sets now. Updating a single set is the unit of change for both the
// authenticated match modal and the token-authenticated score-tracking screens.
export async function updateMatchSet(
  tournament_id: number,
  match_id: number,
  set_id: number,
  body: MatchSetBody
) {
  return createAxios()
    .put(`tournaments/${tournament_id}/matches/${match_id}/sets/${set_id}`, body)
    .catch((response: any) => handleRequestError(response));
}

export async function updateScoreTrackingMatchSet(
  score_tracking_token: string,
  match_id: number,
  set_id: number,
  body: MatchSetBody
) {
  return createAxios()
    .put(`score-tracking/${score_tracking_token}/matches/${match_id}/sets/${set_id}`, body)
    .catch((response: any) => handleRequestError(response));
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
  return createAxios().post(`tournaments/${tournament_id}/matches/swap`, body);
}

export async function resizeMatchBreak(
  tournament_id: number,
  match_id: number,
  body: MatchResizeBreakBody
) {
  return createAxios().post(`tournaments/${tournament_id}/matches/${match_id}/resize_break`, body);
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
