import { showNotification } from '@mantine/notifications';
import axios, { AxiosError, AxiosInstance, AxiosResponse } from 'axios';
import { useNavigate } from 'react-router';
import useSWR, { mutate, SWRResponse } from 'swr';

import { TournamentFilter } from '@components/utils/tournament';
import { Pagination } from '@components/utils/util';
import {
  ClubsResponse,
  CourtsResponse,
  FullTeamWithPlayers,
  PlayersResponse,
  RankingsResponse,
  RefereeNamesResponse,
  StageItemInputOptionsResponse,
  StagesWithStageItemsResponse,
  TeamsWithPlayersResponse,
  TournamentIssuesResponse,
  TournamentResponse,
  TournamentsResponse,
  UserPublicResponse,
} from '@openapi';
import dayjs from 'dayjs';
import { getLogin, performLogout, tokenPresent } from './local_storage';

export function handleRequestError(response: AxiosError) {
  if (response.code === 'ERR_NETWORK') {
    showNotification({
      color: 'red',
      title: 'An error occurred',
      message: 'Internal server error',
      autoClose: 10000,
    });
    return;
  }

  // @ts-ignore
  if (response.response != null && response.response.data.detail != null) {
    // If the detail contains an array, there is likely a pydantic validation error occurring.
    // @ts-ignore
    const { detail } = response.response.data;
    let message: string;

    if (Array.isArray(detail)) {
      const firstError = detail[0];
      message = `${firstError.loc.slice(1).join(' - ')}: ${firstError.msg}`;
    } else {
      message = detail.toString();
    }

    showNotification({
      color: 'red',
      title: 'An error occurred',
      message,
      autoClose: 10000,
    });
  }
}

export function requestSucceeded(result: AxiosResponse | AxiosError) {
  // @ts-ignore
  return result.name !== 'AxiosError';
}

export function getBaseApiUrl() {
  return import.meta.env.VITE_API_BASE_URL != null
    ? import.meta.env.VITE_API_BASE_URL
    : 'http://localhost:8400';
}

export function createAxios() {
  const user = getLogin();
  const access_token = user != null ? user.access_token : '';
  return axios.create({
    baseURL: getBaseApiUrl(),
    headers: {
      Authorization: `bearer ${access_token}`,
      Accept: 'application/json',
    },
  });
}

export async function awaitRequestAndHandleError(
  requestFunction: (instance: AxiosInstance) => Promise<AxiosResponse>
): Promise<AxiosError | AxiosResponse> {
  let response = null;
  try {
    response = await requestFunction(createAxios());
  } catch (exc: any) {
    if (exc.name === 'AxiosError') {
      handleRequestError(exc);
      return exc;
    }
    throw exc;
  }
  return response;
}

function getTimeState() {
  // Used to force a refresh on SWRResponse, even when the response stays the same.
  // For example, when the page layout depends on time, but the response contains
  // timestamps that don't change, this is necessary.
  return { time: dayjs() };
}

const fetcher = (url: string) =>
  createAxios()
    .get(url)
    .then((res: { data: any }) => res.data);

const fetcherWithTimestamp = (url: string) =>
  createAxios()
    .get(url)
    .then((res: { data: any }) => ({ ...res.data, ...getTimeState() }));

export function getClubs(): SWRResponse<ClubsResponse> {
  return useSWR('clubs', fetcher);
}

export function getTournamentByEndpointName(
  tournament_endpoint_name: string
): SWRResponse<TournamentsResponse> {
  return useSWR(`tournaments?endpoint_name=${tournament_endpoint_name}`, fetcher);
}

export function getTournamentById(tournament_id: number): SWRResponse<TournamentResponse> {
  return useSWR(`tournaments/${tournament_id}`, fetcher);
}

export function getIssuesKey(tournament_id: number): string {
  return `tournaments/${tournament_id}/issues`;
}

export function getTournamentIssues(
  tournament_id: number | null
): SWRResponse<TournamentIssuesResponse> {
  return useSWR(tournament_id == null ? null : getIssuesKey(tournament_id), fetcher, {
    revalidateOnFocus: true,
    revalidateOnMount: true,
  });
}

export async function mutateIssues(tournament_id: number) {
  await mutate(getIssuesKey(tournament_id));
}

export function getTournaments(filter: TournamentFilter): SWRResponse<TournamentsResponse> {
  return useSWR(`tournaments?filter_=${filter}`, fetcher);
}

export function getPlayers(
  tournament_id: number,
  not_in_team: boolean = false
): SWRResponse<PlayersResponse> {
  return useSWR(getPlayersKey(tournament_id, not_in_team), fetcher);
}

export function getPlayersKey(tournament_id: number, not_in_team: boolean = false): string {
  return `tournaments/${tournament_id}/players?not_in_team=${not_in_team}&limit=100`;
}

export function getPlayersPaginated(
  tournament_id: number,
  pagination: Pagination
): SWRResponse<PlayersResponse> {
  return useSWR(
    `tournaments/${tournament_id}/players?limit=${pagination.limit}&offset=${pagination.offset}&sort_by=${pagination.sort_by}&sort_direction=${pagination.sort_direction}`,
    fetcher
  );
}

export function getTeams(tournament_id: number | undefined): SWRResponse<TeamsWithPlayersResponse> {
  return useSWR(
    tournament_id == null ? null : `tournaments/${tournament_id}/teams?limit=100`,
    fetcher
  );
}

export function getTeamsPaginated(
  tournament_id: number,
  pagination: Pagination,
  level_id: string = 'all'
): SWRResponse<TeamsWithPlayersResponse> {
  const levelParam = level_id === 'all' ? '' : `&level_id=${level_id}`;
  return useSWR(
    `tournaments/${tournament_id}/teams?limit=${pagination.limit}&offset=${pagination.offset}&sort_by=${pagination.sort_by}&sort_direction=${pagination.sort_direction}${levelParam}`,
    fetcher
  );
}

export function getTeamsLive(tournament_id: number | null): SWRResponse<TeamsWithPlayersResponse> {
  return useSWR(tournament_id == null ? null : `tournaments/${tournament_id}/teams`, fetcher, {
    refreshInterval: 5_000,
  });
}

// Teams for the public dashboard team filter, optionally restricted to a single level so the
// dropdown only offers teams from that level. The combobox filters this set client-side as the
// user types. The endpoint caps a page at 100, so we fetch a second page when the tournament has
// more than 100 teams (up to 200 total, which is plenty in practice).
export function getTeamsForDashboard(
  tournament_id: number | null,
  level_id: number | null
): { teams: FullTeamWithPlayers[]; isLoading: boolean } {
  const levelParam = level_id == null ? '' : `&level_id=${level_id}`;
  const baseUrl =
    tournament_id == null ? null : `tournaments/${tournament_id}/teams?limit=100${levelParam}`;

  const firstPage = useSWR<TeamsWithPlayersResponse>(baseUrl, fetcher);
  const totalCount = firstPage.data?.data.count ?? 0;
  const secondPage = useSWR<TeamsWithPlayersResponse>(
    baseUrl != null && totalCount > 100 ? `${baseUrl}&offset=100` : null,
    fetcher
  );

  return {
    teams: [...(firstPage.data?.data.teams ?? []), ...(secondPage.data?.data.teams ?? [])],
    isLoading: firstPage.isLoading,
  };
}

export function getReferees(tournament_id: number | undefined): SWRResponse<RefereeNamesResponse> {
  return useSWR(tournament_id == null ? null : `tournaments/${tournament_id}/referees`, fetcher);
}

export function getAvailableStageItemInputs(
  tournament_id: number
): SWRResponse<StageItemInputOptionsResponse> {
  return useSWR(`tournaments/${tournament_id}/available_inputs`, fetcher);
}

export function getStages(
  tournament_id: number | null,
  no_draft_rounds: boolean = false
): SWRResponse<StagesWithStageItemsResponse> {
  return useSWR(
    tournament_id == null || tournament_id === -1
      ? null
      : `tournaments/${tournament_id}/stages?no_draft_rounds=${no_draft_rounds}`,
    fetcher
  );
}

/**
 * Like `getStages`, but revalidates every `refreshIntervalMs` so changes made by
 * co-organizers on other devices show up without a manual refresh. Pass 0 to
 * hold the data still (e.g. while the planner has a match selected); that also
 * suspends focus/reconnect revalidation, so nothing shifts under the user.
 */
export function getStagesWithPolling(
  tournament_id: number | null,
  refreshIntervalMs: number
): SWRResponse<StagesWithStageItemsResponse> {
  return useSWR(
    tournament_id == null || tournament_id === -1
      ? null
      : `tournaments/${tournament_id}/stages?no_draft_rounds=false`,
    fetcher,
    {
      refreshInterval: refreshIntervalMs,
      revalidateOnFocus: refreshIntervalMs > 0,
      revalidateOnReconnect: refreshIntervalMs > 0,
    }
  );
}

export function getStagesLive(
  tournament_id: number | null
): SWRResponse<StagesWithStageItemsResponse> {
  return useSWR(
    tournament_id == null ? null : `tournaments/${tournament_id}/stages?no_draft_rounds=true`,
    fetcherWithTimestamp,
    {
      refreshInterval: 5_000,
    }
  );
}

export function getRankings(tournament_id: number | null): SWRResponse<RankingsResponse> {
  return useSWR(tournament_id == null ? null : `tournaments/${tournament_id}/rankings`, fetcher);
}

export function getCourts(tournament_id: number): SWRResponse<CourtsResponse> {
  return useSWR(`tournaments/${tournament_id}/courts`, fetcher);
}

export function getCourtsLive(tournament_id: number | null): SWRResponse<CourtsResponse> {
  return useSWR(tournament_id == null ? null : `tournaments/${tournament_id}/courts`, fetcher, {
    refreshInterval: 60_000,
  });
}

export function getUser(): SWRResponse<UserPublicResponse> {
  return useSWR('users/me', fetcher);
}

export async function uploadTournamentLogo(tournament_id: number, file: any) {
  const bodyFormData = new FormData();
  bodyFormData.append('file', file, file.name);

  return createAxios().post(`tournaments/${tournament_id}/logo`, bodyFormData);
}

export async function removeTournamentLogo(tournament_id: number) {
  return createAxios().post(`tournaments/${tournament_id}/logo`);
}

export async function uploadTeamLogo(tournament_id: number, team_id: number, file: any) {
  const bodyFormData = new FormData();
  bodyFormData.append('file', file, file.name);

  return createAxios().post(`tournaments/${tournament_id}/teams/${team_id}/logo`, bodyFormData);
}

export async function removeTeamLogo(tournament_id: number, team_id: number) {
  return createAxios().post(`tournaments/${tournament_id}/teams/${team_id}/logo`);
}

export function checkForAuthError(response: any) {
  if (typeof window !== 'undefined' && !tokenPresent()) {
    const navigate = useNavigate();
    navigate('/login');
  }

  // We send a simple GET `/clubs` request to test whether we really should log out. // Next
  // sometimes uses out-of-date local storage, so we send an additional request with up-to-date
  // local storage.
  // If that gives a 401, we log out.
  function responseHasAuthError(_response: any) {
    return (
      _response.error != null &&
      _response.error.response != null &&
      _response.error.response.status === 401
    );
  }
  if (responseHasAuthError(response)) {
    createAxios()
      .get('users/me')
      .then(() => {})
      .catch((error: any) => {
        if (error.toJSON().status === 401) {
          performLogout();
        }
      });
  }
}
