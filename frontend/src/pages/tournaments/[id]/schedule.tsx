import { Affix, Box, Button, Grid, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { IconCalendarPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import CourtModal from '@components/modals/create_court_modal';
import MatchModal from '@components/modals/match_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import { computeScheduleLayout } from '@logic/planning/layout';
import {
  IDLE_SELECTION,
  SelectionEvent,
  SelectionState,
  selectionReducer,
} from '@logic/planning/selection';
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
import { rescheduleMatch, scheduleMatches, unscheduleMatch } from '@services/match';

import ScheduleGrid from '@components/scheduling/schedule_grid';
import UnscheduledSheet from '@components/scheduling/unscheduled_sheet';

export default function SchedulePage() {
  const [modalOpened, modalSetOpened] = useState(false);
  const [match, setMatch] = useState<MatchWithDetails | null>(null);
  const [selection, setSelection] = useState<SelectionState>(IDLE_SELECTION);

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

  async function handleSelectionEvent(event: SelectionEvent) {
    const { state, reschedule, swap, unschedule } = selectionReducer(selection, event);
    setSelection(state);
    if (reschedule != null) {
      await rescheduleMatch(tournamentData.id, reschedule.matchId, reschedule.body);
      await swrStagesResponse.mutate();
    }
    if (swap != null) {
      await rescheduleMatch(tournamentData.id, swap.first.matchId, swap.first.body);
      await rescheduleMatch(tournamentData.id, swap.second.matchId, swap.second.body);
      await swrStagesResponse.mutate();
    }
    if (unschedule != null) {
      await unscheduleMatch(tournamentData.id, unschedule.matchId);
      await swrStagesResponse.mutate();
    }
  }

  const selectedMatchId =
    selection.kind === 'match-selected'
      ? selection.match.matchId
      : selection.kind === 'tray-match-selected'
        ? selection.matchId
        : null;
  const selectedEntry = selectedMatchId != null ? matchesLookup[selectedMatchId] : null;

  const isPlacing = selection.kind !== 'idle';

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
        <Box mt="1rem" pb={isPlacing ? '14rem' : '4rem'}>
          <ScheduleGrid
            layout={layout}
            violations={violations}
            stageItemsLookup={stageItemsLookup}
            matchesLookup={matchesLookup}
            selection={selection}
            onSelectionEvent={handleSelectionEvent}
          />
          <UnscheduledSheet
            unscheduledMatches={unscheduledMatches}
            stageItemsLookup={stageItemsLookup}
            matchesLookup={matchesLookup}
            selectedTrayMatchId={
              selection.kind === 'tray-match-selected' ? selection.matchId : null
            }
            onTrayMatchSelect={(matchId) =>
              handleSelectionEvent({ type: 'tap-tray-match', matchId })
            }
          />
          {selectedEntry != null ? (
            <Affix position={{ bottom: 70, left: '50%' }} zIndex={300}>
              <Paper
                shadow="md"
                radius="xl"
                withBorder
                px="md"
                py={6}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  maxWidth: 'calc(100vw - 1rem)',
                  transform: 'translateX(-50%)',
                }}
              >
                <Box style={{ flex: 1, minWidth: 0 }}>
                  <Text size="sm" fw={600} truncate>
                    {formatMatchInput1(t, stageItemsLookup, matchesLookup, selectedEntry.match)} –{' '}
                    {formatMatchInput2(t, stageItemsLookup, matchesLookup, selectedEntry.match)}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {t('tap_to_place_hint')}
                  </Text>
                </Box>
                <Group gap="xs" wrap="nowrap">
                  {selection.kind === 'match-selected' && (
                    <Button
                      size="compact-sm"
                      variant="light"
                      color="orange"
                      onClick={() => handleSelectionEvent({ type: 'unschedule' })}
                    >
                      {t('unschedule_button')}
                    </Button>
                  )}
                  <Button
                    size="compact-sm"
                    variant="light"
                    color="red"
                    onClick={() => handleSelectionEvent({ type: 'cancel' })}
                  >
                    {t('cancel_button')}
                  </Button>
                </Group>
              </Paper>
            </Affix>
          ) : null}
        </Box>
      )}
    </TournamentLayout>
  );
}
