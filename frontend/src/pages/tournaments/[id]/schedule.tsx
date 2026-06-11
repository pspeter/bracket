import { Affix, Box, Button, Grid, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { IconCalendarPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import CourtModal from '@components/modals/create_court_modal';
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
  const [selection, setSelection] = useState<SelectionState>(IDLE_SELECTION);
  const [trayOpened, setTrayOpened] = useState(false);

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

  async function handleSelectionEvent(event: SelectionEvent) {
    const wasTraySelection = selection.kind === 'tray-match-selected';
    const { state, actions } = selectionReducer(selection, event);
    setSelection(state);

    // Picking a match from the tray collapses it so the grid is free for placing.
    if (state.kind === 'tray-match-selected') {
      setTrayOpened(false);
    }

    if (actions.length > 0) {
      for (const action of actions) {
        if (action.type === 'reschedule') {
          await rescheduleMatch(tournamentData.id, action.matchId, action.body);
        } else {
          await unscheduleMatch(tournamentData.id, action.matchId);
        }
      }
      await swrStagesResponse.mutate();

      // After placing a tray match, reopen the tray so scheduling many matches
      // in a row flows without extra taps.
      if (wasTraySelection && event.type === 'tap-insertion-line') {
        setTrayOpened(true);
      }
    }
  }

  const selectedMatchId =
    selection.kind === 'match-selected'
      ? selection.match.matchId
      : selection.kind === 'tray-match-selected'
        ? selection.matchId
        : null;
  const selectedEntry = selectedMatchId != null ? matchesLookup[selectedMatchId] : null;

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
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
        <Box mt="1rem" pb={selection.kind !== 'idle' ? '14rem' : '4rem'}>
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
            opened={trayOpened}
            onToggle={() => setTrayOpened(!trayOpened)}
            onSelectMatch={(m) => handleSelectionEvent({ type: 'tap-tray-match', matchId: m.id })}
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
              </Paper>
            </Affix>
          ) : null}
        </Box>
      )}
    </TournamentLayout>
  );
}
