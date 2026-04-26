import { SWRResponse } from 'swr';

import { assert_not_none } from '@components/utils/assert';
import { groupBy, responseIsValid } from '@components/utils/util';
import {
  Court,
  CourtsResponse,
  FullTeamWithPlayers,
  MatchWithDetails,
  StageItemWithRounds,
  StageWithStageItems,
} from '@openapi';
import { getTeams } from './adapter';

export function getTeamsLookup(tournamentId: number) {
  const swrTeamsResponse: SWRResponse = getTeams(tournamentId);
  const isResponseValid = responseIsValid(swrTeamsResponse);

  if (!isResponseValid) {
    return null;
  }
  return Object.fromEntries(
    swrTeamsResponse.data.data.teams.map((x: FullTeamWithPlayers) => [x.id, x])
  );
}

export function getStageItemLookup(swrStagesResponse: SWRResponse) {
  let result: any[] = [];
  if (swrStagesResponse?.data == null) return Object.fromEntries(result);

  swrStagesResponse.data.data.map((stage: StageWithStageItems) =>
    stage.stage_items.forEach((stage_item) => {
      result = result.concat([[stage_item.id, stage_item]]);
    })
  );
  return Object.fromEntries(result);
}

export function getStageItemList(swrStagesResponse: SWRResponse) {
  let result: any[] = [];

  swrStagesResponse.data.data.map((stage: StageWithStageItems) =>
    stage.stage_items.forEach((stage_item) => {
      result = result.concat([[stage_item]]);
    })
  );
  return result;
}

export function getStageItemTeamIdsLookup(swrStagesResponse: SWRResponse) {
  let result: any[] = [];

  swrStagesResponse.data.data.map((stage: StageWithStageItems) =>
    stage.stage_items.forEach((stageItem) => {
      const teamIds = stageItem.inputs.map((input) => input.team_id);
      result = result.concat([[stageItem.id, teamIds]]);
    })
  );
  return Object.fromEntries(result);
}

export function getAssignedTeamIds(swrStagesResponse: SWRResponse): number[] {
  const teamIds = new Set<number>();

  swrStagesResponse.data.data.forEach((stage: StageWithStageItems) => {
    stage.stage_items.forEach((stageItem) => {
      stageItem.inputs.forEach((input) => {
        if (input.team_id != null) {
          teamIds.add(input.team_id);
        }
      });
    });
  });

  return [...teamIds];
}

export function getStageItemTeamsLookup(swrStagesResponse: SWRResponse) {
  let result: any[] = [];

  swrStagesResponse.data.data.map((stage: StageWithStageItems) =>
    stage.stage_items
      .sort((si1, si2) => (si1.name > si2.name ? 1 : -1))
      .forEach((stageItem) => {
        const teams_with_inputs = stageItem.inputs.filter(
          (input) => 'team' in input && input.team != null
        );

        if (teams_with_inputs.length > 0) {
          result = result.concat([[stageItem.id, teams_with_inputs]]);
        }
      })
  );
  return Object.fromEntries(result);
}

/** One match in the schedule tree with its parent stage item and top-level stage. */
export type MatchLookupEntry = {
  match: MatchWithDetails;
  stageItem: StageItemWithRounds;
  stage: StageWithStageItems;
};

/**
 * Map each match id to its `MatchWithDetails` plus the owning `StageItemWithRounds` and parent
 * `StageWithStageItems`, so UIs (e.g. the schedule) can group by stage without re-walking the tree.
 */
export function getMatchLookup(swrStagesResponse: SWRResponse): Record<number, MatchLookupEntry> {
  const result: [number, MatchLookupEntry][] = [];

  for (const stage of swrStagesResponse.data.data as StageWithStageItems[]) {
    for (const stageItem of stage.stage_items) {
      for (const round of stageItem.rounds) {
        for (const match of round.matches) {
          result.push([match.id, { match, stageItem, stage }]);
        }
      }
    }
  }
  return Object.fromEntries(result);
}

export function stringToColour(input: string) {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    // eslint-disable-next-line no-bitwise
    hash = input.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = [
    'pink',
    'violet',
    'green',
    'blue',
    'red',
    'grape',
    'indigo',
    'cyan',
    'orange',
    'yellow',
    'teal',
  ];
  return colors[Math.abs(hash) % colors.length];
}

export function getMatchLookupByCourt(swrStagesResponse: SWRResponse) {
  const matches = Object.values(getMatchLookup(swrStagesResponse)).map((x) => x.match);
  return groupBy(['court_id'])(matches);
}

export function getUnscheduledMatches(swrStagesResponse: SWRResponse): MatchWithDetails[] {
  const matches: MatchWithDetails[] = [];
  for (const stage of swrStagesResponse.data.data) {
    for (const stageItem of stage.stage_items) {
      for (const round of stageItem.rounds) {
        for (const match of round.matches) {
          if (match.start_time == null) {
            matches.push(match);
          }
        }
      }
    }
  }
  return matches;
}

export function getScheduleData(
  swrCourtsResponse: SWRResponse<CourtsResponse>,
  matchesByCourtId: any
): { court: Court; matches: MatchWithDetails[] }[] {
  return (swrCourtsResponse.data?.data || []).map((court: Court) => ({
    matches: (matchesByCourtId[court.id] || [])
      .filter((match: MatchWithDetails) => match.start_time != null)
      .sort((m1: MatchWithDetails, m2: MatchWithDetails) => {
        return assert_not_none(m1.position_in_schedule) > assert_not_none(m2.position_in_schedule)
          ? 1
          : -1 || [];
      }),
    court,
  }));
}
