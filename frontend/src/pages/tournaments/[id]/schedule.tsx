import {
  ActionIcon,
  Affix,
  Badge,
  Box,
  Button,
  Grid,
  Group,
  Loader,
  Modal,
  Overlay,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Title,
  Tooltip,
  VisuallyHidden,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { showNotification } from '@mantine/notifications';
import {
  IconArrowsMove,
  IconCalendarOff,
  IconCalendarPlus,
  IconListDetails,
  IconTools,
  IconUserCheck,
  IconWand,
} from '@tabler/icons-react';
import { isAxiosError } from 'axios';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import CourtModal from '@components/modals/create_court_modal';
import MatchModal from '@components/modals/match_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import { computeStageItemColours, levelSwatchColour } from '@logic/colors';
import { ConflictPreview, computeConflictPreview } from '@logic/planning/conflict_preview';
import { stageHighlightOptions } from '@logic/planning/highlight';
import { computeScheduleLayout } from '@logic/planning/layout';
import { currentTimeOffsetMinutes } from '@logic/planning/now_line';
import { applyPlanningActions } from '@logic/planning/optimistic';
import {
  isStaleScheduleError,
  scheduleRefreshInterval,
  shouldRefreshOnSelectionChange,
} from '@logic/planning/polling';
import {
  ActiveSelectionState,
  FocusTarget,
  IDLE_SELECTION,
  PlannerEvent,
  PlannerState,
  PlanningAction,
  initialPlannerState,
  isPlannerMode,
  plannerReducer,
} from '@logic/planning/selection';
import { nextTrayOpenedAfterPlannerEvent } from '@logic/planning/unscheduled_tray';
import { ZOOM_TICK_INTERVAL_MINUTES, defaultZoomLevel } from '@logic/planning/zoom';
import {
  Court,
  LevelResponse,
  MatchWithDetails,
  SchedulerWeights,
  StageWithStageItems,
} from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import {
  getCourts,
  getStagesWithPolling,
  getTournamentById,
  handleRequestError,
} from '@services/adapter';
import {
  MatchLookupEntry,
  getMatchLookup,
  getMatchLookupByCourt,
  getStageItemLookup,
  getStageOrderViolations,
  getUnscheduledMatches,
} from '@services/lookups';
import {
  autoAssignReferees,
  reoptimizeMatches,
  rescheduleMatch,
  resizeMatchBreak,
  scheduleMatches,
  swapMatches,
  unscheduleMatch,
} from '@services/match';

import CourtsToolbar from '@components/scheduling/courts_toolbar';
import {
  PLANNER_DESELECT_IGNORE_ATTRIBUTE,
  PLANNER_GRID_ATTRIBUTE,
} from '@components/scheduling/planner_anchor';
import PlannerToolsSheet from '@components/scheduling/planner_tools_sheet';
import ScheduleGrid from '@components/scheduling/schedule_grid';
import SchedulerWeightsForm, {
  DEFAULT_SCHEDULER_WEIGHTS,
} from '@components/scheduling/scheduler_weights_form';
import UnscheduledSheet from '@components/scheduling/unscheduled_sheet';
import { useLockViewportZoom } from '@components/scheduling/use_lock_viewport_zoom';
import { usePinchZoom } from '@components/scheduling/use_pinch_zoom';
import ZoomControls from '@components/scheduling/zoom_controls';

function activeSelectionFrom(selection: PlannerState['selection']): ActiveSelectionState | null {
  switch (selection.kind) {
    case 'match-selected':
    case 'tray-match-selected':
      return selection;
    case 'confirm-move':
      return selection.previous;
    default:
      return null;
  }
}

export default function SchedulePage() {
  const [planner, setPlanner] = useState<PlannerState>(() =>
    initialPlannerState(defaultZoomLevel(window.innerWidth))
  );
  const [highlightValue, setHighlightValue] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());
  const [trayOpened, setTrayOpened] = useState(false);
  // On phones the inline top toolbar (team search, courts, auto-schedule) is
  // awkward, so it collapses into a tools sheet reached from a button beside the
  // unscheduled tray. Same breakpoint the grid uses for its mobile affordances.
  const isMobile = useMediaQuery('(max-width: 768px)') ?? false;
  const [toolsOpened, setToolsOpened] = useState(false);
  const [focus, setFocus] = useState<(FocusTarget & { nonce: number }) | null>(null);
  // Details modal opened from the selection pill; holds the match id (not the
  // match) so a background revalidation refreshes the modal's data instead of
  // detaching it.
  const [detailsMatchId, setDetailsMatchId] = useState<number | null>(null);
  // Guards "Re-optimize everything": the modal warns that manual placements and
  // adjusted breaks are recomputed, so nothing is sent until the user confirms.
  const [reoptimizeModalOpened, setReoptimizeModalOpened] = useState(false);
  // Both scheduling actions open a modal whose collapsed "advanced" panel lets the
  // organizer override the solver's objective weights before the request is sent.
  const [scheduleModalOpened, setScheduleModalOpened] = useState(false);
  const [scheduleWeights, setScheduleWeights] =
    useState<SchedulerWeights>(DEFAULT_SCHEDULER_WEIGHTS);
  const [scheduleAdvancedOpened, setScheduleAdvancedOpened] = useState(false);
  const [reoptimizeWeights, setReoptimizeWeights] =
    useState<SchedulerWeights>(DEFAULT_SCHEDULER_WEIGHTS);
  const [reoptimizeAdvancedOpened, setReoptimizeAdvancedOpened] = useState(false);
  // Set while an optimize-all / schedule-unscheduled SAT run is in flight; dims
  // the planning view behind a spinner so the long solve reads as deliberate.
  const [isOptimizing, setIsOptimizing] = useState(false);
  // Captures pinch and ctrl+wheel over the whole planning content, so a pinch
  // that starts next to the grid zooms the schedule instead of the page.
  const pinchRef = usePinchZoom(handlePlannerEvent);
  // Lock the browser's page zoom on mobile so the planner's own zoom levels are
  // the only thing that changes scale; otherwise the page drifts zoomed-in and
  // the content pinch handler leaves no way to zoom back out.
  useLockViewportZoom();

  const activeSelection = activeSelectionFrom(planner.selection);

  useEffect(() => {
    const intervalId = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(intervalId);
  }, []);

  // Escape cancels an active match selection. Confirmation and details modals
  // own Escape while they're open (Mantine closes them first), so only act on
  // the plain selected states here.
  useEffect(() => {
    if (
      detailsMatchId != null ||
      planner.selection.kind === 'confirm-move' ||
      activeSelection == null
    ) {
      return undefined;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        handlePlannerEvent({ type: 'cancel' });
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [planner.selection, activeSelection, detailsMatchId]);

  useEffect(() => {
    if (
      detailsMatchId != null ||
      planner.selection.kind === 'confirm-move' ||
      activeSelection == null
    ) {
      return undefined;
    }

    const ignoredSelector = [
      `[${PLANNER_GRID_ATTRIBUTE}]`,
      `[${PLANNER_DESELECT_IGNORE_ATTRIBUTE}]`,
      '[role="dialog"]',
      '[role="menu"]',
      '[role="menuitem"]',
      '[role="button"]',
      'button',
      'a',
      'input',
      'textarea',
      'select',
      '.mantine-Modal-root',
      '.mantine-Drawer-root',
      '.mantine-Popover-dropdown',
    ].join(',');

    const handlePointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest(ignoredSelector) != null) return;
      handlePlannerEvent({ type: 'cancel' });
    };

    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [planner.selection, activeSelection, detailsMatchId]);

  const { t } = useTranslation();
  const { tournamentData } = getTournamentIdFromRouter();
  // The schedule polls so co-organizers' changes show up, but holds still
  // (interval 0) while a selection or move confirmation is active.
  const swrStagesResponse = getStagesWithPolling(
    tournamentData.id,
    scheduleRefreshInterval(planner.selection)
  );
  const swrCourtsResponse = getCourts(tournamentData.id);
  const swrTournamentResponse = getTournamentById(tournamentData.id);

  // When a pause ends (selection cleared), refresh immediately instead of
  // waiting up to a full polling interval for changes made in the meantime.
  const refreshSchedule = swrStagesResponse.mutate;
  const previousSelectionRef = useRef(planner.selection);
  useEffect(() => {
    if (shouldRefreshOnSelectionChange(previousSelectionRef.current, planner.selection)) {
      refreshSchedule();
    }
    previousSelectionRef.current = planner.selection;
  }, [planner.selection, refreshSchedule]);

  // The conflict preview simulates every candidate placement against the shared
  // conflict engine, so it is memoized on the inputs that actually change its
  // result — the schedule, courts, tournament settings, the active selection and
  // the zoom level — instead of being recomputed on every unrelated re-render
  // (e.g. the minute clock tick). At overview zoom placement is disabled, so there
  // is nothing to preview.
  const conflictPreview = useMemo<ConflictPreview>(() => {
    if (
      planner.zoom === 'overview' ||
      !responseIsValid(swrStagesResponse) ||
      !responseIsValid(swrCourtsResponse) ||
      !responseIsValid(swrTournamentResponse)
    ) {
      return { insertionLines: new Set<string>(), swapTargets: new Set<number>() };
    }
    const tournamentValue = swrTournamentResponse.data!.data;
    const courtsValue: Court[] = swrCourtsResponse.data?.data ?? [];
    const stagesValue: StageWithStageItems[] = swrStagesResponse.data?.data ?? [];
    const previewLayout = computeScheduleLayout({
      courts: courtsValue,
      matchesByCourtId: getMatchLookupByCourt(swrStagesResponse),
      tournamentStartTime: tournamentValue.start_time,
      defaultBreakMinutes: tournamentValue.margin_minutes,
      tickIntervalMinutes: ZOOM_TICK_INTERVAL_MINUTES[planner.zoom],
    });
    return computeConflictPreview({
      stages: stagesValue,
      layout: previewLayout,
      selection: planner.selection,
      tournamentStartTime: tournamentValue.start_time,
      refereesEnabled: tournamentValue.referees_enabled,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    swrStagesResponse.data?.data,
    swrCourtsResponse.data?.data,
    swrTournamentResponse.data?.data,
    planner.selection,
    planner.zoom,
  ]);

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
  // Level → hue, stage → hue cluster, stage item → shade; shared by every
  // schedule view so a match keeps its colour identity across zoom levels.
  const stageItemColours = computeStageItemColours(rawStages, levels);
  const highlightOptions = stageHighlightOptions(rawStages);
  const highlightTarget =
    highlightOptions.find((option) => option.value === highlightValue)?.target ?? null;

  const layout = computeScheduleLayout({
    courts,
    matchesByCourtId,
    tournamentStartTime: tournament.start_time,
    defaultBreakMinutes: tournament.margin_minutes,
    tickIntervalMinutes: ZOOM_TICK_INTERVAL_MINUTES[planner.zoom],
  });
  const nowOffsetMinutes = currentTimeOffsetMinutes({
    tournamentStartTime: tournament.start_time,
    totalMinutes: layout.totalMinutes,
    now,
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

  async function handleAssignReferees() {
    setIsOptimizing(true);
    try {
      await autoAssignReferees(tournamentData.id);
      await swrStagesResponse.mutate();
    } finally {
      setIsOptimizing(false);
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
      case 'resize-break':
        await resizeMatchBreak(tournamentData.id, action.matchId, {
          new_duration_minutes: action.newDurationMinutes,
        });
        break;
      default:
        break;
    }
  }

  async function handlePlannerEvent(event: PlannerEvent) {
    const previousSelectionForTray =
      planner.selection.kind === 'confirm-move' ? planner.selection.previous : planner.selection;
    const wasTraySelection = previousSelectionForTray.kind === 'tray-match-selected';
    const { state, actions, focus: focusTarget } = plannerReducer(planner, event);
    setPlanner(state);
    if (focusTarget != null) {
      setFocus((previous) => ({ ...focusTarget, nonce: (previous?.nonce ?? 0) + 1 }));
    }

    for (const action of actions) {
      if (action.type === 'open-details') {
        setDetailsMatchId(action.matchId);
      }
    }

    const backendActions = actions.filter((action) => action.type !== 'open-details');

    const updateTrayOpened = () =>
      setTrayOpened((opened) =>
        nextTrayOpenedAfterPlannerEvent({
          opened,
          previousSelection: previousSelectionForTray,
          nextSelection: state.selection,
          event,
          actions,
        })
      );

    if (backendActions.length > 0) {
      try {
        // Show the predicted outcome immediately; the revalidation that follows the
        // request replaces it with the backend's authoritative schedule.
        await swrStagesResponse.mutate(
          async (current) => {
            for (const action of backendActions) {
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
                    data: applyPlanningActions(
                      current.data,
                      backendActions,
                      tournament.start_time,
                      tournament.margin_minutes
                    ),
                  },
            populateCache: false,
            revalidate: true,
          }
        );
      } catch (error) {
        // The optimistic update was rolled back; resync with the backend's
        // authoritative schedule and restart the placement flow from idle.
        setPlanner((current) => ({ ...current, selection: IDLE_SELECTION }));
        await swrStagesResponse.mutate();
        if (isStaleScheduleError(error)) {
          // Someone else moved a match between this device's last refresh and
          // the placement: not an error to apologize for, just pick again.
          showNotification({
            color: 'orange',
            title: t('schedule_changed_title'),
            message: t('schedule_changed_message'),
            autoClose: 10000,
          });
        } else if (isAxiosError(error)) {
          handleRequestError(error);
        } else {
          throw error;
        }
      }
      if (wasTraySelection) {
        updateTrayOpened();
      }
    } else {
      updateTrayOpened();
    }
  }

  const selectedMatchId =
    activeSelection?.kind === 'match-selected'
      ? activeSelection.match.matchId
      : activeSelection?.kind === 'tray-match-selected'
        ? activeSelection.matchId
        : null;
  const selectedEntry = selectedMatchId != null ? matchesLookup[selectedMatchId] : null;
  const detailsMatch =
    detailsMatchId != null ? (matchesLookup[detailsMatchId]?.match ?? null) : null;
  const isOverview = planner.zoom === 'overview';

  // Pieces of the selection pill, extracted so the mobile (stacked) and desktop
  // (single row) layouts can compose them without duplicating the markup.
  const matchTitle =
    selectedEntry != null ? (
      <Text size="sm" fw={600} truncate>
        {formatMatchInput1(t, stageItemsLookup, matchesLookup, selectedEntry.match)} –{' '}
        {formatMatchInput2(t, stageItemsLookup, matchesLookup, selectedEntry.match)}
      </Text>
    ) : null;
  const placeHint = (
    <Text size="xs" c="dimmed">
      {isOverview ? t('zoom_in_to_place_hint') : t('tap_to_place_hint')}
    </Text>
  );
  const detailsButton = (
    <Button
      size="compact-sm"
      variant="light"
      color="blue"
      leftSection={<IconListDetails size={16} />}
      onClick={() => {
        if (selectedMatchId != null) setDetailsMatchId(selectedMatchId);
      }}
    >
      {t('details_button')}
    </Button>
  );
  const unscheduleButton =
    activeSelection?.kind === 'match-selected' && selectedEntry?.match.state === 'NOT_STARTED' ? (
      <Button
        size="compact-sm"
        variant="light"
        color="orange"
        leftSection={<IconCalendarOff size={16} />}
        onClick={() => handlePlannerEvent({ type: 'unschedule' })}
      >
        {t('unschedule_button')}
      </Button>
    ) : null;
  const plannerModeControl = (
    <SegmentedControl
      size={isMobile ? 'xs' : 'sm'}
      value={planner.mode}
      aria-label={t('planner_mode_aria_label')}
      onChange={(value) => {
        if (isPlannerMode(value)) handlePlannerEvent({ type: 'set-mode', mode: value });
      }}
      data={[
        {
          value: 'move',
          label: (
            <Tooltip label={t('planner_mode_move')} disabled={!isMobile}>
              <Group gap={4} wrap="nowrap" justify="center" miw={isMobile ? 26 : undefined}>
                <IconArrowsMove size={16} aria-hidden />
                {isMobile ? (
                  <VisuallyHidden>{t('planner_mode_move')}</VisuallyHidden>
                ) : (
                  <Text span size="sm">
                    {t('planner_mode_move')}
                  </Text>
                )}
              </Group>
            </Tooltip>
          ),
        },
        {
          value: 'unschedule',
          label: (
            <Tooltip label={t('planner_mode_unschedule')} disabled={!isMobile}>
              <Group gap={4} wrap="nowrap" justify="center" miw={isMobile ? 26 : undefined}>
                <IconCalendarOff size={16} aria-hidden />
                {isMobile ? (
                  <VisuallyHidden>{t('planner_mode_unschedule')}</VisuallyHidden>
                ) : (
                  <Text span size="sm">
                    {t('planner_mode_unschedule')}
                  </Text>
                )}
              </Group>
            </Tooltip>
          ),
        },
        {
          value: 'edit',
          label: (
            <Tooltip label={t('planner_mode_edit')} disabled={!isMobile}>
              <Group gap={4} wrap="nowrap" justify="center" miw={isMobile ? 26 : undefined}>
                <IconListDetails size={16} aria-hidden />
                {isMobile ? (
                  <VisuallyHidden>{t('planner_mode_edit')}</VisuallyHidden>
                ) : (
                  <Text span size="sm">
                    {t('planner_mode_edit')}
                  </Text>
                )}
              </Group>
            </Tooltip>
          ),
        },
      ]}
    />
  );

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      <Box ref={pinchRef} style={{ touchAction: 'pan-x pan-y' }}>
        {/* A SAT solve is a single synchronous request, so dim the whole
            viewport — header and navbar included — behind a spinner to make the
            wait read as deliberate and discourage navigating away mid-solve. */}
        {isOptimizing && (
          <Overlay fixed color="#000" backgroundOpacity={0.55} blur={1} zIndex={1000} center>
            <Stack align="center" gap="sm">
              <Loader size="lg" />
              <Text c="white" fw={600}>
                {t('optimizing_schedule_label', 'Optimizing schedule …')}
              </Text>
            </Stack>
          </Overlay>
        )}
        <Grid grow>
          <Grid.Col span={6}>
            <Title>{t('planning_title')}</Title>
          </Grid.Col>
          {/* On mobile these controls move into the tools sheet reached from the
              unscheduled tray, leaving the header uncluttered. */}
          {!isMobile && (
            <Grid.Col span={6}>
              <Group justify="right">
                <Select
                  aria-label={t('team_highlight_label', 'Highlight team or input')}
                  placeholder={t('team_highlight_placeholder', 'Find team or input')}
                  data={highlightOptions}
                  value={highlightValue}
                  onChange={setHighlightValue}
                  searchable
                  clearable
                  limit={100}
                  w={220}
                  size="sm"
                  mb={10}
                />
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
                    onClick={() => setScheduleModalOpened(true)}
                  >
                    {t('schedule_description')}
                  </Button>
                )}
                {courts.length < 1 ? null : (
                  <Button
                    color="grape"
                    size="md"
                    variant="light"
                    style={{ marginBottom: 10 }}
                    leftSection={<IconWand size={24} />}
                    onClick={() => setReoptimizeModalOpened(true)}
                  >
                    {t('reoptimize_description')}
                  </Button>
                )}
                {courts.length < 1 || !tournament.referees_enabled ? null : (
                  <Button
                    color="teal"
                    size="md"
                    variant="light"
                    style={{ marginBottom: 10 }}
                    leftSection={<IconUserCheck size={24} />}
                    onClick={handleAssignReferees}
                  >
                    {t('assign_missing_referees_description')}
                  </Button>
                )}
              </Group>
            </Grid.Col>
          )}
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
            {/* Colour legend: the level name lives only in the hue, so a compact
                key maps each level's colour back to its name. Stages (hue
                clusters) and items (shades) stay readable from the badge text. */}
            {levels.length > 0 && (
              <Group gap="xs" mb="xs">
                {[...levels]
                  .sort((a, b) => a.position - b.position)
                  .map((level) => (
                    <Badge
                      key={level.id}
                      color={levelSwatchColour(level.id, levels)}
                      variant="light"
                    >
                      {level.name}
                    </Badge>
                  ))}
              </Group>
            )}
            <ScheduleGrid
              layout={layout}
              stages={rawStages}
              violations={violations}
              conflictPreview={conflictPreview}
              stageItemsLookup={stageItemsLookup}
              matchesLookup={matchesLookup}
              stageItemColours={stageItemColours}
              selection={planner.selection}
              highlightTarget={highlightTarget}
              zoom={planner.zoom}
              focus={focus}
              nowOffsetMinutes={nowOffsetMinutes}
              refereesEnabled={tournament.referees_enabled}
              onSelectionEvent={handlePlannerEvent}
            />
            <UnscheduledSheet
              unscheduledMatches={unscheduledMatches}
              stageItemsLookup={stageItemsLookup}
              matchesLookup={matchesLookup}
              levels={levels}
              stageItemColours={stageItemColours}
              opened={trayOpened}
              // On phones a live selection shows the placement pill at the
              // bottom; slide the whole tray off the bottom of the screen while
              // one is active so it's out of the way during tap-to-place. It's
              // derived (not stored), so the tray returns once selection clears.
              hidden={isMobile && activeSelection != null}
              onToggle={() => setTrayOpened((opened) => !opened)}
              onSelectMatch={(m) => handlePlannerEvent({ type: 'tap-tray-match', matchId: m.id })}
              rightSection={
                isMobile ? (
                  <Group gap="xs" wrap="nowrap">
                    {plannerModeControl}
                    <ActionIcon
                      variant="default"
                      size="lg"
                      aria-label={t('planner_tools_title')}
                      onClick={() => setToolsOpened(true)}
                    >
                      <IconTools size={20} />
                    </ActionIcon>
                  </Group>
                ) : (
                  plannerModeControl
                )
              }
            />
            {isMobile && (
              <PlannerToolsSheet
                opened={toolsOpened}
                onClose={() => setToolsOpened(false)}
                tournamentId={tournamentData.id}
                swrCourtsResponse={swrCourtsResponse}
                courts={courts}
                matchesByCourtId={matchesByCourtId}
                highlightOptions={highlightOptions}
                highlightValue={highlightValue}
                onHighlightChange={setHighlightValue}
                onSchedule={() => setScheduleModalOpened(true)}
                onReoptimize={() => setReoptimizeModalOpened(true)}
                refereesEnabled={tournament.referees_enabled && courts.length > 0}
                onAssignReferees={handleAssignReferees}
              />
            )}
            <Modal
              opened={planner.selection.kind === 'confirm-move'}
              onClose={() => handlePlannerEvent({ type: 'cancel' })}
              title={t('move_confirmation_title')}
              centered
              zIndex={500}
            >
              <Stack>
                <Text>{t('move_confirmation_body')}</Text>
                <Group justify="flex-end">
                  <Button variant="default" onClick={() => handlePlannerEvent({ type: 'cancel' })}>
                    {t('move_confirmation_cancel')}
                  </Button>
                  <Button
                    color="orange"
                    leftSection={<IconArrowsMove size={18} />}
                    onClick={() => handlePlannerEvent({ type: 'confirm' })}
                  >
                    {t('move_confirmation_confirm')}
                  </Button>
                </Group>
              </Stack>
            </Modal>
            <MatchModal
              tournamentData={tournamentData}
              match={detailsMatch}
              swrStagesResponse={swrStagesResponse}
              opened={detailsMatch != null}
              setOpened={(value: boolean) => {
                if (!value) setDetailsMatchId(null);
              }}
              round={null}
              levels={levels}
            />
            <Modal
              opened={scheduleModalOpened}
              onClose={() => setScheduleModalOpened(false)}
              title={t('schedule_modal_title')}
            >
              <Stack>
                <Text>{t('schedule_modal_body')}</Text>
                <SchedulerWeightsForm
                  weights={scheduleWeights}
                  onChange={setScheduleWeights}
                  opened={scheduleAdvancedOpened}
                  onToggle={() => setScheduleAdvancedOpened((o) => !o)}
                />
                <Group justify="flex-end">
                  <Button variant="default" onClick={() => setScheduleModalOpened(false)}>
                    {t('schedule_modal_cancel')}
                  </Button>
                  <Button
                    color="indigo"
                    leftSection={<IconCalendarPlus size={18} />}
                    onClick={async () => {
                      setScheduleModalOpened(false);
                      setIsOptimizing(true);
                      try {
                        await scheduleMatches(tournamentData.id, scheduleWeights);
                        await swrStagesResponse.mutate();
                      } finally {
                        setIsOptimizing(false);
                      }
                    }}
                  >
                    {t('schedule_modal_confirm')}
                  </Button>
                </Group>
              </Stack>
            </Modal>
            <Modal
              opened={reoptimizeModalOpened}
              onClose={() => setReoptimizeModalOpened(false)}
              title={t('reoptimize_modal_title')}
            >
              <Stack>
                <Text>{t('reoptimize_modal_body')}</Text>
                <SchedulerWeightsForm
                  weights={reoptimizeWeights}
                  onChange={setReoptimizeWeights}
                  opened={reoptimizeAdvancedOpened}
                  onToggle={() => setReoptimizeAdvancedOpened((o) => !o)}
                />
                <Group justify="flex-end">
                  <Button variant="default" onClick={() => setReoptimizeModalOpened(false)}>
                    {t('reoptimize_modal_cancel')}
                  </Button>
                  <Button
                    color="grape"
                    leftSection={<IconWand size={18} />}
                    onClick={async () => {
                      setReoptimizeModalOpened(false);
                      setIsOptimizing(true);
                      try {
                        await reoptimizeMatches(tournamentData.id, reoptimizeWeights);
                        await swrStagesResponse.mutate();
                      } finally {
                        setIsOptimizing(false);
                      }
                    }}
                  >
                    {t('reoptimize_modal_confirm')}
                  </Button>
                </Group>
              </Stack>
            </Modal>
            {/* Like the selection pill below: above the tray (150), below modals. */}
            <Affix position={{ right: 8, top: '45%' }} zIndex={180}>
              <ZoomControls zoom={planner.zoom} onZoomEvent={handlePlannerEvent} />
            </Affix>
            {selectedEntry != null ? (
              // Below modals, so the selection pill never covers them on small
              // screens; above the tray (150), which sits underneath it.
              // On phones the tray slides away while a match is selected, so drop
              // the pill near the bottom edge; on desktop keep it clear of the
              // tray header that stays visible underneath it.
              <Affix position={{ bottom: isMobile ? 16 : 70, left: '50%' }} zIndex={180}>
                <Paper
                  {...{ [PLANNER_DESELECT_IGNORE_ATTRIBUTE]: true }}
                  shadow="md"
                  radius="xl"
                  withBorder
                  px="md"
                  py={6}
                  style={{
                    display: 'flex',
                    // On phones the hint text and buttons cannot share one row
                    // without the text wrapping awkwardly in a narrow column, so
                    // stack them: title, then a full-width button row, then hint.
                    flexDirection: isMobile ? 'column' : 'row',
                    alignItems: isMobile ? 'stretch' : 'center',
                    gap: isMobile ? 8 : 12,
                    width: isMobile ? 'calc(100vw - 1rem)' : undefined,
                    maxWidth: 'calc(100vw - 1rem)',
                    transform: 'translateX(-50%)',
                  }}
                >
                  {isMobile ? (
                    <>
                      {matchTitle}
                      <Group gap="xs" grow>
                        {detailsButton}
                        {unscheduleButton}
                      </Group>
                      {placeHint}
                    </>
                  ) : (
                    <>
                      <Box style={{ flex: 1, minWidth: 0 }}>
                        {matchTitle}
                        {placeHint}
                      </Box>
                      {detailsButton}
                      {unscheduleButton}
                    </>
                  )}
                </Paper>
              </Affix>
            ) : null}
          </Box>
        )}
      </Box>
    </TournamentLayout>
  );
}
