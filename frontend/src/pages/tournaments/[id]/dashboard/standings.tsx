import { Container, Text } from '@mantine/core';
import { AiOutlineHourglass } from '@react-icons/all-files/ai/AiOutlineHourglass';
import { parseAsInteger, useQueryState } from 'nuqs';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { DashboardFooter } from '@components/dashboard/footer';
import { DoubleHeader, getTournamentHeadTitle } from '@components/dashboard/layout';
import { NoContent } from '@components/no_content/empty_table_info';
import { StandingsTableForStageItem } from '@components/tables/standings';
import { TableSkeletonTwoColumns } from '@components/utils/skeletons';
import { responseIsValid, setTitle } from '@components/utils/util';
import { Ranking, StagesWithStageItemsResponse } from '@openapi';
import { getRankings, getStagesLive } from '@services/adapter';
import { getTournamentResponseByEndpointName } from '@services/dashboard';
import {
  getStageItemLevelLookup,
  getStageItemLookup,
  getStageItemTeamsLookup,
} from '@services/lookups';

export function StandingsContent({
  swrStagesResponse,
  fontSizeInPixels,
  maxTeamsToDisplay,
  rankingsById = {},
  levelId = null,
  teamId = null,
}: {
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  fontSizeInPixels: number;
  maxTeamsToDisplay: number;
  rankingsById?: Record<number, Ranking>;
  levelId?: number | null;
  teamId?: number | null;
}) {
  const { t } = useTranslation();

  const stageItemsLookup = getStageItemLookup(swrStagesResponse);
  const stageItemTeamLookup = responseIsValid(swrStagesResponse)
    ? getStageItemTeamsLookup(swrStagesResponse)
    : {};
  const stageItemLevelLookup = responseIsValid(swrStagesResponse)
    ? getStageItemLevelLookup(swrStagesResponse)
    : {};

  const rows = Object.keys(stageItemTeamLookup)
    .filter((stageItemId) => stageItemsLookup[stageItemId] != null)
    .filter(
      (stageItemId) => levelId == null || stageItemLevelLookup[parseInt(stageItemId)] === levelId
    )
    .filter(
      (stageItemId) =>
        teamId == null ||
        stageItemTeamLookup[stageItemId].some((input: any) => input.team_id === teamId)
    )
    .sort((si1: any, si2: any) =>
      stageItemsLookup[si1].name > stageItemsLookup[si2].name ? 1 : -1
    )
    .map((stageItemId) => {
      const stageItem = stageItemsLookup[stageItemId];
      const ranking =
        stageItem.ranking_id != null ? (rankingsById[stageItem.ranking_id] ?? null) : null;
      return (
        <div key={stageItemId}>
          <Text size="xl" mt="md" mb="xs" inherit>
            {stageItem.name}
          </Text>
          <StandingsTableForStageItem
            teams_with_inputs={stageItemTeamLookup[stageItemId]}
            stageItem={stageItem}
            stageItemsLookup={stageItemsLookup}
            fontSizeInPixels={fontSizeInPixels}
            maxTeamsToDisplay={maxTeamsToDisplay}
            ranking={ranking}
          />
        </div>
      );
    });

  if (rows.length < 1) {
    return (
      <NoContent
        title={`${t('could_not_find_any_alert')} ${t('teams_title')}`}
        description=""
        icon={<AiOutlineHourglass />}
      />
    );
  }
  return rows;
}

export default function DashboardStandingsPage() {
  const tournamentDataFull = getTournamentResponseByEndpointName();
  const tournamentValid = !React.isValidElement(tournamentDataFull);
  const [levelId] = useQueryState('level', parseAsInteger);
  const [teamId] = useQueryState('team', parseAsInteger);

  const swrStagesResponse = getStagesLive(tournamentValid ? tournamentDataFull.id : null);
  const swrRankingsResponse = getRankings(tournamentValid ? tournamentDataFull.id : null);

  if (!tournamentValid) {
    return tournamentDataFull;
  }

  setTitle(getTournamentHeadTitle(tournamentDataFull));

  if (swrStagesResponse.isLoading) {
    return <TableSkeletonTwoColumns />;
  }

  const rankingsById: Record<number, Ranking> = Object.fromEntries(
    (swrRankingsResponse.data?.data ?? []).map((r) => [r.id, r])
  );

  return (
    <>
      <DoubleHeader tournamentData={tournamentDataFull} />
      <Container mt="1rem" px="0rem">
        <Container style={{ width: '100%' }} px="sm">
          <StandingsContent
            swrStagesResponse={swrStagesResponse}
            fontSizeInPixels={16}
            maxTeamsToDisplay={100}
            rankingsById={rankingsById}
            levelId={levelId}
            teamId={teamId}
          />
        </Container>
      </Container>
      <DashboardFooter />
    </>
  );
}
