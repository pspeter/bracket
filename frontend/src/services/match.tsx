import {
  MatchBody,
  MatchCreateBodyFrontend,
  MatchRescheduleBody,
  MatchResizeBreakBody,
  MatchSetScoreEditBody,
  MatchSwapBody,
  SchedulerWeights,
  ScoreTrackingInfoResponse,
} from '@openapi';
import { createAxios, handleRequestError, performMutation } from './adapter';

export async function createMatch(tournament_id: number, match: MatchCreateBodyFrontend) {
  return performMutation('post', `tournaments/${tournament_id}/matches`, match, {
    tournamentId: tournament_id,
  });
}

export async function deleteMatch(tournament_id: number, match_id: number) {
  return performMutation('delete', `tournaments/${tournament_id}/matches/${match_id}`, undefined, {
    tournamentId: tournament_id,
  });
}

export async function updateMatch(
  tournament_id: number,
  match_id: number,
  match: Omit<MatchBody, 'referee_stage_item_input_id' | 'referee_name'> &
    Partial<Pick<MatchBody, 'referee_stage_item_input_id' | 'referee_name'>>
) {
  return performMutation('put', `tournaments/${tournament_id}/matches/${match_id}`, match, {
    tournamentId: tournament_id,
  });
}

// Scores live on sets. A set's scores are the unit of change for both the authenticated
// match modal and the token-authenticated score-tracking screens; match progress only
// moves through the start/end/reopen/reset verbs below.
export async function scoreEditMatchSet(
  tournament_id: number,
  match_id: number,
  set_id: number,
  body: MatchSetScoreEditBody
) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/matches/${match_id}/sets/${set_id}/score-edit`,
    body,
    { tournamentId: tournament_id }
  );
}

export async function startMatch(tournament_id: number, match_id: number) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/matches/${match_id}/start`,
    undefined,
    { tournamentId: tournament_id }
  );
}

export async function endMatch(tournament_id: number, match_id: number) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/matches/${match_id}/end`,
    undefined,
    { tournamentId: tournament_id }
  );
}

export async function reopenMatch(tournament_id: number, match_id: number) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/matches/${match_id}/reopen`,
    undefined,
    { tournamentId: tournament_id }
  );
}

export async function resetMatch(tournament_id: number, match_id: number) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/matches/${match_id}/reset`,
    undefined,
    { tournamentId: tournament_id }
  );
}

export async function scoreEditScoreTrackingMatchSet(
  score_tracking_token: string,
  tournament_id: number | null,
  match_id: number,
  set_id: number,
  body: MatchSetScoreEditBody
) {
  return performMutation(
    'post',
    `score-tracking/${score_tracking_token}/matches/${match_id}/sets/${set_id}/score-edit`,
    body,
    {
      tournamentId: async () =>
        tournament_id ?? (await getTournamentIdForScoreTrackingToken(score_tracking_token)),
    }
  );
}

export async function startScoreTrackingMatch(
  score_tracking_token: string,
  tournament_id: number | null,
  match_id: number
) {
  return performMutation(
    'post',
    `score-tracking/${score_tracking_token}/matches/${match_id}/start`,
    undefined,
    {
      tournamentId: async () =>
        tournament_id ?? (await getTournamentIdForScoreTrackingToken(score_tracking_token)),
    }
  );
}

export async function endScoreTrackingMatch(
  score_tracking_token: string,
  tournament_id: number | null,
  match_id: number
) {
  return performMutation(
    'post',
    `score-tracking/${score_tracking_token}/matches/${match_id}/end`,
    undefined,
    {
      tournamentId: async () =>
        tournament_id ?? (await getTournamentIdForScoreTrackingToken(score_tracking_token)),
    }
  );
}

export async function reopenScoreTrackingMatch(
  score_tracking_token: string,
  tournament_id: number | null,
  match_id: number
) {
  return performMutation(
    'post',
    `score-tracking/${score_tracking_token}/matches/${match_id}/reopen`,
    undefined,
    {
      tournamentId: async () =>
        tournament_id ?? (await getTournamentIdForScoreTrackingToken(score_tracking_token)),
    }
  );
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
  return performMutation(
    'post',
    `tournaments/${tournament_id}/matches/${match_id}/unschedule`,
    undefined,
    { tournamentId: tournament_id, catchErrors: false }
  );
}

export async function rescheduleMatch(
  tournament_id: number,
  match_id: number,
  match: MatchRescheduleBody
) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/matches/${match_id}/reschedule`,
    match,
    { tournamentId: tournament_id, catchErrors: false }
  );
}

export async function swapMatches(tournament_id: number, body: MatchSwapBody) {
  return performMutation('post', `tournaments/${tournament_id}/matches/swap`, body, {
    tournamentId: tournament_id,
    catchErrors: false,
  });
}

export async function resizeMatchBreak(
  tournament_id: number,
  match_id: number,
  body: MatchResizeBreakBody
) {
  return performMutation(
    'post',
    `tournaments/${tournament_id}/matches/${match_id}/resize_break`,
    body,
    { tournamentId: tournament_id, catchErrors: false }
  );
}

export async function autoAssignReferees(tournament_id: number, weights?: SchedulerWeights) {
  // No tournament-issue counter involves referees, so referee assignment provably cannot
  // change any issue count today. If a referee issue source is ever added, wire this up
  // (see AGENTS.md on tournament issue badges).
  return performMutation(
    'post',
    `tournaments/${tournament_id}/matches/auto-assign-referees`,
    weights,
    { invalidateIssues: false }
  );
}

export async function scheduleMatches(tournament_id: number, weights?: SchedulerWeights) {
  return performMutation('post', `tournaments/${tournament_id}/schedule_matches`, weights, {
    tournamentId: tournament_id,
  });
}

export async function reoptimizeMatches(tournament_id: number, weights?: SchedulerWeights) {
  return performMutation('post', `tournaments/${tournament_id}/reoptimize_matches`, weights, {
    tournamentId: tournament_id,
  });
}
