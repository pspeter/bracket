import { Affix, Badge, Box, Button, Grid, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { IconCalendarPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import CourtModal from '@components/modals/create_court_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import { computeScheduleLayout } from '@logic/planning/layout';
import { applyPlanningActions } from '@logic/planning/optimistic';
import {
  FocusTarget,
  PlannerEvent,
  PlannerState,
  PlanningAction,
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
import { rescheduleMatch, scheduleMatches, swapMatches, unscheduleMatch } from '@services/match';

import CourtsToolbar from '@components/scheduling/courts_toolbar';
import ScheduleGrid from '@components/scheduling/schedule_grid';
import UnscheduledSheet from '@components/scheduling/unscheduled_sheet';
import { usePinchZoom } from '@components/scheduling/use_pinch_zoom';
import ZoomControls from '@components/scheduling/zoom_controls';

export default function SchedulePage() {
  const [planner, setPlanner] = useState<PlannerState>(() =>
    initialPlannerState(defaultZoomLevel(window.innerWidth))
  );
  const [trayOpened, setTrayOpened] = useState(false);
  const [focus, setFocus] = useState<(FocusTarget & { nonce: number }) | null>(null);
  // Captures pinch and ctrl+wheel over the whole planning content, so a pinch
  // that starts next to the grid zooms the schedule instead of the page.
  const pinchRef = usePinchZoom(handlePlannerEvent);

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

  async function performAction(action: PlanningAction) {
    switch (action.type) {
      case 'swap':
        await swapMatches(tournamentData.id, {
          match1_id: action.matchId1,
          match2_id: action.matchId2,
        });
        break;
      case 'reschedule':
        await rescheduleMatch(tournamentData.id, action.matchId, action.body);
        break;
      case 'unschedule':
        await unscheduleMatch(tournamentData.id, action.matchId);
        break;
      default:
        break;
    }
  }

  async function handlePlannerEvent(event: PlannerEvent) {
    const wasTraySelection = planner.selection.kind === 'tray-match-selected';
    const { state, actions, focus: focusTarget } = plannerReducer(planner, event);
    setPlanner(state);
    if (focusTarget != null) {
      setFocus((previous) => ({ ...focusTarget, nonce: (previous?.nonce ?? 0) + 1 }));
    }

    // Picking a match from the tray collapses it so the grid is free for placing.
    if (state.selection.kind === 'tray-match-selected') {
      setTrayOpened(false);
    }

    if (actions.length > 0) {
      // After placing a tray match, reopen the tray so scheduling many matches
      // in a row flows without extra taps.
      if (wasTraySelection && event.type === 'tap-insertion-line') {
        setTrayOpened(true);
      }

      // Show the predicted outcome immediately; the revalidation that follows the
      // request replaces it with the backend's authoritative schedule.
      await swrStagesResponse.mutate(
        async (current) => {
          for (const action of actions) {
            await performAction(action);
          }
          return current;
        },
        {
          optimisticData: (current) =>
            current == null
              ? current!
              : {
                  ...current,
                  data: applyPlanningActions(current.data, actions, tournament.start_time),
                },
          populateCache: false,
          revalidate: true,
        }
      );
    }
  }

  const selectedMatchId =
    planner.selection.kind === 'match-selected'
      ? planner.selection.match.matchId
      : planner.selection.kind === 'tray-match-selected'
        ? planner.selection.matchId
        : null;
  const selectedEntry = selectedMatchId != null ? matchesLookup[selectedMatchId] : null;
  const isOverview = planner.zoom === 'overview';

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      <Box ref={pinchRef} style={{ touchAction: 'pan-x pan-y' }}>
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
          <Box
            mt="1rem"
            pb={planner.selection.kind !== 'idle' ? '14rem' : '4rem'}
            // The grid sizes its court columns in cqw units of this box, so the
            // schedule hugs the same available width at every zoom level.
            style={{ containerType: 'inline-size' }}
          >
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
              opened={trayOpened}
              onToggle={() => setTrayOpened(!trayOpened)}
              onSelectMatch={(m) => handlePlannerEvent({ type: 'tap-tray-match', matchId: m.id })}
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
                  {planner.selection.kind === 'match-selected' && (
                    <Button
                      size="compact-sm"
                      variant="light"
                      color="orange"
                      onClick={() => handlePlannerEvent({ type: 'unschedule' })}
                    >
                      {t('unschedule_button')}
                    </Button>
                  )}
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
      </Box>
    </TournamentLayout>
  );
}
