import { Affix, Badge, Box, Button, Grid, Group, Paper, Stack, Text, Title } from '@mantine/core';
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
  FocusTarget,
  PlannerEvent,
  PlannerState,
  initialPlannerState,
  plannerReducer,
} from '@logic/planning/selection';
import { ZOOM_TICK_INTERVAL_MINUTES, defaultZoomLevel, levelColour } from '@logic/planning/zoom';
import { Court, LevelResponse, MatchWithDetails, StageWithStageItems } from '@openapi';
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
import { rescheduleMatch, scheduleMatches } from '@services/match';

import CourtsToolbar from '@components/scheduling/courts_toolbar';
import ScheduleGrid from '@components/scheduling/schedule_grid';
import UnscheduledSheet from '@components/scheduling/unscheduled_sheet';
import ZoomControls from '@components/scheduling/zoom_controls';

export default function SchedulePage() {
  const [modalOpened, modalSetOpened] = useState(false);
  const [match, setMatch] = useState<MatchWithDetails | null>(null);
  const [planner, setPlanner] = useState<PlannerState>(() =>
    initialPlannerState(defaultZoomLevel(window.innerWidth))
  );
  const [focus, setFocus] = useState<(FocusTarget & { nonce: number }) | null>(null);

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
  const levels: LevelResponse[] = tournament.levels ?? [];

  const layout = computeScheduleLayout({
    courts,
    matchesByCourtId,
    tournamentStartTime: tournament.start_time,
    tickIntervalMinutes: ZOOM_TICK_INTERVAL_MINUTES[planner.zoom],
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

  async function handlePlannerEvent(event: PlannerEvent) {
    const { state, reschedule, focus: focusTarget } = plannerReducer(planner, event);
    setPlanner(state);
    if (focusTarget != null) {
      setFocus((previous) => ({ ...focusTarget, nonce: (previous?.nonce ?? 0) + 1 }));
    }
    if (reschedule != null) {
      await rescheduleMatch(tournamentData.id, reschedule.matchId, reschedule.body);
      await swrStagesResponse.mutate();
    }
  }

  const selectedEntry =
    planner.selection.kind === 'match-selected'
      ? matchesLookup[planner.selection.match.matchId]
      : null;
  const isOverview = planner.zoom === 'overview';

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
          <Group justify="right">
            <CourtsToolbar
              tournamentId={tournamentData.id}
              swrCourtsResponse={swrCourtsResponse}
              courts={courts}
              matchesByCourtId={matchesByCourtId}
            />
            {courts.length < 1 ? null : (
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
            )}
          </Group>
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
        <Box mt="1rem" pb={planner.selection.kind === 'match-selected' ? '14rem' : '4rem'}>
          {isOverview && levels.length > 0 && (
            <Group gap="xs" mb="xs">
              {[...levels]
                .sort((a, b) => a.position - b.position)
                .map((level) => (
                  <Badge key={level.id} color={levelColour(level.id, levels)} variant="filled">
                    {level.name}
                  </Badge>
                ))}
            </Group>
          )}
          <ScheduleGrid
            layout={layout}
            violations={violations}
            stageItemsLookup={stageItemsLookup}
            matchesLookup={matchesLookup}
            levels={levels}
            selection={planner.selection}
            zoom={planner.zoom}
            focus={focus}
            onSelectionEvent={handlePlannerEvent}
          />
          <UnscheduledSheet
            unscheduledMatches={unscheduledMatches}
            stageItemsLookup={stageItemsLookup}
            matchesLookup={matchesLookup}
            openMatchModal={openMatchModal}
          />
          <Affix position={{ right: 8, top: '45%' }} zIndex={200}>
            <ZoomControls zoom={planner.zoom} onZoomEvent={handlePlannerEvent} />
          </Affix>
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
                    {isOverview ? t('zoom_in_to_place_hint') : t('tap_to_place_hint')}
                  </Text>
                </Box>
                <Button
                  size="compact-sm"
                  variant="light"
                  color="red"
                  onClick={() => handlePlannerEvent({ type: 'cancel' })}
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
