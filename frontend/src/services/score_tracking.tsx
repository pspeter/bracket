import { ScoreTrackingInfoResponse, ScoreTrackingMatchResponse } from '@openapi';
import useSWR, { SWRResponse } from 'swr';

import { createAxios } from './adapter';

const fetcher = (url: string) =>
  createAxios()
    .get(url)
    .then((res: { data: any }) => res.data);

export function getScoreTrackingInfo(
  scoreTrackingToken: string | null
): SWRResponse<ScoreTrackingInfoResponse> {
  return useSWR(
    scoreTrackingToken == null ? null : `score-tracking/${scoreTrackingToken}`,
    fetcher,
    {
      refreshInterval: 5_000,
    }
  );
}

export function getScoreTrackingMatch(
  scoreTrackingToken: string | null,
  matchId: number | null
): SWRResponse<ScoreTrackingMatchResponse> {
  return useSWR(
    scoreTrackingToken == null || matchId == null
      ? null
      : `score-tracking/${scoreTrackingToken}/matches/${matchId}`,
    fetcher,
    { refreshInterval: 2_000 }
  );
}

export function getTournamentScoreTrackingInfo(
  tournamentId: number | null
): SWRResponse<ScoreTrackingInfoResponse> {
  return useSWR(
    tournamentId == null ? null : `tournaments/${tournamentId}/score-tracking`,
    fetcher,
    {
      refreshInterval: 5_000,
    }
  );
}

export function getTournamentScoreTrackingMatch(
  tournamentId: number | null,
  matchId: number | null
): SWRResponse<ScoreTrackingMatchResponse> {
  return useSWR(
    tournamentId == null || matchId == null
      ? null
      : `tournaments/${tournamentId}/score-tracking/matches/${matchId}`,
    fetcher,
    { refreshInterval: 2_000 }
  );
}
