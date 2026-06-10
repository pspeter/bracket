import { Box, Button, Grid, Group, Stack, Title } from '@mantine/core';
import { IconCalendarPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import CourtModal from '@components/modals/create_court_modal';
import MatchModal from '@components/modals/match_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import { computeScheduleLayout } from '@logic/planning/layout';
import { Court, MatchWithDetails, StageWithStageItems } from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getCourts, getStages, getTournamentById } from '@services/adapter';
import {
  MatchLookupEntry,
  getMatchLookup,
  getMatchLookupByCourt,
  getStageItemLookup,
  getStageOrderViolations,
  getUnscheduledMatches,
} from '@services/lookups';
import { scheduleMatches } from '@services/match';

import ScheduleGrid from '@components/scheduling/schedule_grid';
import UnscheduledSheet from '@components/scheduling/unscheduled_sheet';

export default function SchedulePage() {
  const [modalOpened, modalSetOpened] = useState(false);
  const [match, setMatch] = useState<MatchWithDetails | null>(null);

  const { t } = useTranslation();
  const { tournamentData } = getTournamentIdFromRouter();
  const swrStagesResponse = getStages(tournamentData.id);
  const swrCourtsResponse = getCourts(tournamentData.id);
  const swrTournamentResponse = getTournamentById(tournamentData.id);

  const stageItemsLookup = responseIsValid(swrStagesResponse)
    ? getStageItemLookup(swrStagesResponse)
    : [];
  const matchesLookup: Record<number, MatchLookupEntry> = responseIsValid(swrStagesResponse)
    ? getMatchLookup(swrStagesResponse)
    : ({} as Record<number, MatchLookupEntry>);
  const matchesByCourtId: Record<number, MatchWithDetails[]> = responseIsValid(swrStagesResponse)
    ? getMatchLookupByCourt(swrStagesResponse)
    : {};

  const unscheduledMatches = responseIsValid(swrStagesResponse)
    ? getUnscheduledMatches(swrStagesResponse)
    : [];

  if (!responseIsValid(swrStagesResponse)) return null;
  if (!responseIsValid(swrCourtsResponse)) return null;
  if (!responseIsValid(swrTournamentResponse)) return null;

  const tournament = swrTournamentResponse.data!.data;
  const courts: Court[] = swrCourtsResponse.data?.data ?? [];
  const rawStages: StageWithStageItems[] = swrStagesResponse.data?.data ?? [];

  const layout = computeScheduleLayout({
    courts,
    matchesByCourtId,
    tournamentStartTime: tournament.start_time,
  });

  const violations = new Set<number>();
  for (const { blocks } of layout.courts) {
    for (const matchId of getStageOrderViolations(
      blocks.map((block) => block.match),
      matchesLookup,
      rawStages
    )) {
      violations.add(matchId);
    }
  }

  function openMatchModal(matchToOpen: MatchWithDetails) {
    setMatch(matchToOpen);
    modalSetOpened(true);
  }

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      {match != null ? (
        <MatchModal
          swrStagesResponse={swrStagesResponse}
          swrUpcomingMatchesResponse={null}
          tournamentData={tournamentData}
          match={match}
          opened={modalOpened}
          setOpened={modalSetOpened}
          round={null}
        />
      ) : null}
      <Grid grow>
        <Grid.Col span={6}>
          <Title>{t('planning_title')}</Title>
        </Grid.Col>
        <Grid.Col span={6}>
          {courts.length < 1 ? null : (
            <Group justify="right">
              <Button
                color="indigo"
                size="md"
                variant="filled"
                style={{ marginBottom: 10 }}
                leftSection={<IconCalendarPlus size={24} />}
                onClick={async () => {
                  await scheduleMatches(tournamentData.id);
                  await swrStagesResponse.mutate();
                }}
              >
                {t('schedule_description')}
              </Button>
            </Group>
          )}
        </Grid.Col>
      </Grid>
      {courts.length < 1 ? (
        <Stack align="center" mt="1rem">
          <NoContent title={t('no_courts_title')} description={t('no_courts_description')} />
          <CourtModal
            swrCourtsResponse={swrCourtsResponse}
            tournamentId={tournamentData.id}
            buttonSize="lg"
          />
        </Stack>
      ) : (
        <Box mt="1rem" pb="4rem">
          <ScheduleGrid
            layout={layout}
            violations={violations}
            stageItemsLookup={stageItemsLookup}
            matchesLookup={matchesLookup}
            openMatchModal={openMatchModal}
          />
          <UnscheduledSheet
            unscheduledMatches={unscheduledMatches}
            stageItemsLookup={stageItemsLookup}
            matchesLookup={matchesLookup}
            openMatchModal={openMatchModal}
          />
        </Box>
      )}
    </TournamentLayout>
  );
}
