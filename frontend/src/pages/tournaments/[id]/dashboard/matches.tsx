import { Center, Group } from '@mantine/core';
import { parseAsInteger, useQueryState } from 'nuqs';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { DashboardFooter } from '@components/dashboard/footer';
import { DoubleHeader, getTournamentHeadTitle } from '@components/dashboard/layout';
import { MatchesList } from '@components/matches/matches_list';
import { matchHasTeam } from '@components/utils/match';
import { responseIsValid, setTitle } from '@components/utils/util';
import { getStagesLive } from '@services/adapter';
import { getTournamentResponseByEndpointName } from '@services/dashboard';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';

export default function DashboardMatchesPage() {
  const { t } = useTranslation();
  const tournamentDataFull = getTournamentResponseByEndpointName();
  const tournamentValid = !React.isValidElement(tournamentDataFull);
  const [levelId] = useQueryState('level', parseAsInteger);
  const [teamId] = useQueryState('team', parseAsInteger);

  const swrStagesResponse = getStagesLive(tournamentValid ? tournamentDataFull.id : null);

  if (!tournamentValid) {
    return tournamentDataFull;
  }

  setTitle(getTournamentHeadTitle(tournamentDataFull));

  if (!responseIsValid(swrStagesResponse)) return null;

  const stageItemsLookup = getStageItemLookup(swrStagesResponse);
  const matchesLookup = getMatchLookup(swrStagesResponse);
  const filteredMatchesLookup =
    levelId != null || teamId != null
      ? Object.fromEntries(
          Object.entries(matchesLookup).filter(
            ([, entry]: any) =>
              (levelId == null || entry.stage.level_id === levelId) &&
              (teamId == null ||
                matchHasTeam(entry.match, teamId, tournamentDataFull.referees_enabled))
          )
        )
      : matchesLookup;

  return (
    <>
      <DoubleHeader tournamentData={tournamentDataFull} />
      <Center>
        <Group style={{ maxWidth: '48rem', width: '100%' }} px="1rem">
          <MatchesList
            matchesLookup={filteredMatchesLookup}
            stageItemsLookup={stageItemsLookup}
            levels={tournamentDataFull.levels}
            refereesEnabled={tournamentDataFull.referees_enabled}
          />
        </Group>
      </Center>
      <DashboardFooter />
    </>
  );
}
