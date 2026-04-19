import { Badge, Card, Center, Flex, Grid, Group, Stack, Text } from '@mantine/core';
import { AiOutlineHourglass } from '@react-icons/all-files/ai/AiOutlineHourglass';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { DashboardFooter } from '@components/dashboard/footer';
import { DoubleHeader, getTournamentHeadTitle } from '@components/dashboard/layout';
import { NoContent } from '@components/no_content/empty_table_info';
import { Time } from '@components/utils/datetime';
import {
  formatMatchInput1,
  formatMatchInput2,
  getScoreColors,
  isMatchCompletedRecently,
} from '@components/utils/match';
import { Translator } from '@components/utils/types';
import { responseIsValid, setTitle } from '@components/utils/util';
import { getStagesLive } from '@services/adapter';
import { getTournamentResponseByEndpointName } from '@services/dashboard';
import { getMatchLookup, getStageItemLookup, stringToColour } from '@services/lookups';

export function ScheduleRow({
  data,
  stageItemsLookup,
  matchesLookup,
}: {
  data: any;
  stageItemsLookup: any;
  matchesLookup: any;
}) {
  const { t } = useTranslation();
  const colors = getScoreColors(data.match);

  return (
    <Card shadow="sm" radius="md" withBorder mt="md" pt="0rem">
      <Card.Section withBorder>
        <Grid pt="0.75rem" pb="0.5rem">
          <Grid.Col mb="0rem" span={4}>
            <Text pl="sm" mt="sm" fw={800}>
              {data.match.court.name}
            </Text>
          </Grid.Col>
          <Grid.Col mb="0rem" span={4}>
            <Center>
              <Text mt="sm" fw={800}>
                {data.match.start_time != null ? <Time datetime={data.match.start_time} /> : null}
              </Text>
            </Center>
          </Grid.Col>
          <Grid.Col mb="0rem" span={4}>
            <Flex justify="right">
              <Badge
                color={stringToColour(`${data.stageItem.id}`)}
                variant="outline"
                mr="md"
                mt="0.8rem"
                size="md"
              >
                {data.stageItem.name}
              </Badge>
            </Flex>
          </Grid.Col>
        </Grid>
      </Card.Section>
      <Stack pt="sm">
        <Grid>
          <Grid.Col span="auto" pb="0rem">
            <Text fw={500}>
              {formatMatchInput1(t, stageItemsLookup, matchesLookup, data.match)}
            </Text>
          </Grid.Col>
          <Grid.Col span="content" pb="0rem">
            <div
              style={{
                backgroundColor: colors.stage_item_input1_score,
                borderRadius: '0.5rem',
                width: '2.5rem',
                color: colors.textColor,
                fontWeight: 800,
              }}
            >
              <Center>{data.match.stage_item_input1_score}</Center>
            </div>
          </Grid.Col>
        </Grid>
        <Grid mb="0rem">
          <Grid.Col span="auto" pb="0rem">
            <Text fw={500}>
              {formatMatchInput2(t, stageItemsLookup, matchesLookup, data.match)}
            </Text>
          </Grid.Col>
          <Grid.Col span="content" pb="0rem">
            <div
              style={{
                backgroundColor: colors.stage_item_input2_score,
                borderRadius: '0.5rem',
                width: '2.5rem',
                color: colors.textColor,
                fontWeight: 800,
              }}
            >
              <Center>{data.match.stage_item_input2_score}</Center>
            </div>
          </Grid.Col>
        </Grid>
      </Stack>
    </Card>
  );
}

export function Schedule({
  t,
  stageItemsLookup,
  matchesLookup,
}: {
  t: Translator;
  stageItemsLookup: any;
  matchesLookup: any;
}) {
  const matches: any[] = Object.values(matchesLookup)
    .map((item: any) => item)
    .filter(
      (item: any) => item.match.state === 'IN_PROGRESS' || isMatchCompletedRecently(item.match, 5)
    )
    .sort((m1: any, m2: any) => {
      if (m1.match.state !== m2.match.state) {
        return m1.match.state === 'IN_PROGRESS' ? -1 : 1;
      }
      return (
        (m2.match.completed_at || m2.match.start_time || '').localeCompare(
          m1.match.completed_at || m1.match.start_time || ''
        ) || (m1.match.court?.name || '').localeCompare(m2.match.court?.name || '')
      );
    });

  const rows: React.JSX.Element[] = [];

  for (let c = 0; c < matches.length; c += 1) {
    const data = matches[c];
    rows.push(
      <ScheduleRow
        key={data.match.id}
        data={data}
        stageItemsLookup={stageItemsLookup}
        matchesLookup={matchesLookup}
      />
    );
  }

  if (rows.length < 1) {
    return (
      <NoContent title={t('no_live_matches_title')} description="" icon={<AiOutlineHourglass />} />
    );
  }

  return (
    <Group wrap="nowrap" align="top" style={{ width: '100%' }}>
      <div style={{ width: '100%' }}>{rows}</div>
    </Group>
  );
}
export default function DashboardSchedulePage() {
  const { t } = useTranslation();
  const tournamentDataFull = getTournamentResponseByEndpointName();
  const tournamentValid = !React.isValidElement(tournamentDataFull);

  const swrStagesResponse = getStagesLive(tournamentValid ? tournamentDataFull.id : null);
  if (!tournamentValid) {
    return tournamentDataFull;
  }

  setTitle(getTournamentHeadTitle(tournamentDataFull));

  const stageItemsLookup = responseIsValid(swrStagesResponse)
    ? getStageItemLookup(swrStagesResponse)
    : [];
  const matchesLookup = responseIsValid(swrStagesResponse) ? getMatchLookup(swrStagesResponse) : [];

  // TODO: show loading icon.
  if (!responseIsValid(swrStagesResponse)) return null;

  return (
    <>
      <DoubleHeader tournamentData={tournamentDataFull} />
      <Center>
        <Group style={{ maxWidth: '48rem', width: '100%' }} px="1rem">
          <Schedule t={t} matchesLookup={matchesLookup} stageItemsLookup={stageItemsLookup} />
        </Group>
      </Center>
      <DashboardFooter />
    </>
  );
}
