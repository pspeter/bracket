import { Center, Group, Text } from '@mantine/core';
import { AiOutlineHourglass } from '@react-icons/all-files/ai/AiOutlineHourglass';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { DashboardFooter } from '@components/dashboard/footer';
import { DoubleHeader, getTournamentHeadTitle } from '@components/dashboard/layout';
import { NoContent } from '@components/no_content/empty_table_info';
import { compareDateTime, formatTime } from '@components/utils/datetime';
import { responseIsValid, setTitle } from '@components/utils/util';
import { getStagesLive } from '@services/adapter';
import { getTournamentResponseByEndpointName } from '@services/dashboard';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';
import { ScheduleRow } from './index';

export default function DashboardMatchesPage() {
  const { t } = useTranslation();
  const tournamentDataFull = getTournamentResponseByEndpointName();
  const tournamentValid = !React.isValidElement(tournamentDataFull);

  const swrStagesResponse = getStagesLive(tournamentValid ? tournamentDataFull.id : null);

  if (!tournamentValid) {
    return tournamentDataFull;
  }

  setTitle(getTournamentHeadTitle(tournamentDataFull));

  if (!responseIsValid(swrStagesResponse)) return null;

  const stageItemsLookup = getStageItemLookup(swrStagesResponse);
  const matchesLookup = getMatchLookup(swrStagesResponse);
  const sortedMatches = Object.values(matchesLookup)
    .filter((item: any) => item.match.start_time != null)
    .sort(
      (m1: any, m2: any) =>
        compareDateTime(m1.match.start_time, m2.match.start_time) ||
        (m1.match.court?.name || '').localeCompare(m2.match.court?.name || '') ||
        m1.match.id - m2.match.id
    );

  const rows: React.JSX.Element[] = [];
  for (let c = 0; c < sortedMatches.length; c += 1) {
    const data: any = sortedMatches[c];
    const startTime = formatTime(data.match.start_time);

    if (
      c < 1 ||
      startTime !==
        formatTime(
          // sortedMatches only includes matches with a start time (see filter above)
          sortedMatches[c - 1].match.start_time as string
        )
    ) {
      rows.push(
        <Center mt="md" key={`time-${c}`}>
          <Text size="xl" fw={800}>
            {startTime}
          </Text>
        </Center>
      );
    }

    rows.push(
      <ScheduleRow
        key={data.match.id}
        data={data}
        stageItemsLookup={stageItemsLookup}
        matchesLookup={matchesLookup}
      />
    );
  }

  return (
    <>
      <DoubleHeader tournamentData={tournamentDataFull} />
      <Center>
        <Group style={{ maxWidth: '48rem', width: '100%' }} px="1rem">
          <div style={{ width: '100%' }}>
            {rows.length > 0 ? (
              rows
            ) : (
              <NoContent
                title={t('no_matches_title')}
                description=""
                icon={<AiOutlineHourglass />}
              />
            )}
          </div>
        </Group>
      </Center>
      <DashboardFooter />
    </>
  );
}
