import { MatchBody, MatchCreateBodyFrontend, MatchRescheduleBody, MatchSwapBody } from '@openapi';
import { createAxios, handleRequestError } from './adapter';

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

export async function updateMatch(tournament_id: number, match_id: number, match: MatchBody) {
  return createAxios()
    .put(`tournaments/${tournament_id}/matches/${match_id}`, match)
    .catch((response: any) => handleRequestError(response));
}

export async function updateScoreTrackingMatch(
  score_tracking_token: string,
  match_id: number,
  match: {
    stage_item_input1_score: number;
    stage_item_input2_score: number;
    state: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  }
) {
  return createAxios()
    .put(`score-tracking/${score_tracking_token}/matches/${match_id}`, match)
    .catch((response: any) => handleRequestError(response));
}

export async function updateTournamentScoreTrackingMatch(
  tournament_id: number,
  match_id: number,
  match: {
    stage_item_input1_score: number;
    stage_item_input2_score: number;
    state: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  }
) {
  return createAxios()
    .put(`tournaments/${tournament_id}/score-tracking/matches/${match_id}`, match)
    .catch((response: any) => handleRequestError(response));
}

// The planner's scheduling mutations let errors propagate instead of handling
// them here: the planner must see failures (in particular the 409 stale-write
// rejection when another device moved a match concurrently) to refetch the
// schedule and clear the selection.

export async function unscheduleMatch(tournament_id: number, match_id: number) {
  return createAxios().post(`tournaments/${tournament_id}/matches/${match_id}/unschedule`);
}

export async function rescheduleMatch(
  tournament_id: number,
  match_id: number,
  match: MatchRescheduleBody
) {
  return createAxios().post(`tournaments/${tournament_id}/matches/${match_id}/reschedule`, match);
}

export async function swapMatches(tournament_id: number, body: MatchSwapBody) {
  return createAxios().post(`tournaments/${tournament_id}/matches/swap`, body);
}

export async function scheduleMatches(tournament_id: number) {
  return createAxios()
    .post(`tournaments/${tournament_id}/schedule_matches`)
    .catch((response: any) => handleRequestError(response));
}
