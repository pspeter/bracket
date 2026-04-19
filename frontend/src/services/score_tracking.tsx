import useSWR, { SWRResponse } from 'swr';

import { createAxios } from './adapter';

const fetcher = (url: string) =>
  createAxios()
    .get(url)
    .then((res: { data: any }) => res.data);

export function getScoreTrackingInfo(scoreTrackingToken: string | null): SWRResponse<any> {
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
): SWRResponse<any> {
  return useSWR(
    scoreTrackingToken == null || matchId == null
      ? null
      : `score-tracking/${scoreTrackingToken}/matches/${matchId}`,
    fetcher,
    { refreshInterval: 2_000 }
  );
}
