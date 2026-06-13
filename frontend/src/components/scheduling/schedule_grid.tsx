import { Badge, Box, Flex, Text, Tooltip } from '@mantine/core';
import { AiFillWarning } from '@react-icons/all-files/ai/AiFillWarning';
import { format } from 'date-fns';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { ConflictPreview, insertionLineKey } from '@logic/planning/conflict_preview';
import { HighlightTarget, matchInvolvesHighlight } from '@logic/planning/highlight';
import {
  InsertionLine,
  MatchBlock,
  ScheduleGridLayout,
  computeInsertionLines,
} from '@logic/planning/layout';
import { nowLineScrollTop } from '@logic/planning/now_line';
import { FocusTarget, GridMatchRef, PlannerEvent, SelectionState } from '@logic/planning/selection';
import {
  ZOOM_PX_PER_MINUTE,
  ZoomLevel,
  abbreviateTeamName,
  levelColour,
  shortCourtLabel,
} from '@logic/planning/zoom';
import { Court, LevelResponse, MatchWithDetails } from '@openapi';
import { MatchLookupEntry, getStageItemLookup, stringToColour } from '@services/lookups';

import { COURT_CONTENT_ATTRIBUTE, PLANNER_GRID_ATTRIBUTE } from './planner_anchor';
import classes from './schedule_grid.module.css';

const RULER_WIDTH = '3.25rem';
const HEADER_HEIGHT = '2.5rem';
const HEADER_HEIGHT_PX = 40;
const NOW_LINE_OPACITY = 0.4;
/** Height of an insertion line's tap target; the visible line is centered inside it. */
const INSERTION_HIT_AREA_PX = 32;
/**
 * Breathing space between the header and minute 0, applied to the ruler and all
 * court columns alike so time alignment is preserved. Gives the topmost insertion
 * line room above the first match, so moving a match to the front of a court is
 * an easy tap.
 */
const GRID_TOP_INSET_PX = 32;

/**
 * Court column width per zoom level, in container-query units of the grid's
 * parent (set up by the page), so the grid hugs its content at every level
 * instead of jumping between content width and full width when zooming.
 * Agenda fills a phone screen with a single court; compact fits 3–4 courts on
 * a phone and widens on larger screens; overview divides the available width
 * among all courts, capped so few courts don't stretch wider than agenda.
 */
function courtColumnWidth(zoom: ZoomLevel, courtCount: number): string {
  // All courts share the available width, capped at the agenda width — so with
  // few courts, overview occupies the same footprint as agenda instead of
  // stretching, and compact widens up to that same footprint (the max() below)
  // instead of staying narrower.
  const evenShare = `min(calc((100cqw - ${RULER_WIDTH} - 4px) / ${Math.max(courtCount, 1)} - 1px), 20rem)`;
  switch (zoom) {
    case 'agenda':
      return `min(calc(100cqw - ${RULER_WIDTH} - 4px), 20rem)`;
    case 'compact':
      return `max(clamp(5.5rem, 27cqw, 9rem), ${evenShare})`;
    case 'overview':
    default:
      return evenShare;
  }
}

function matchColour(
  match: MatchWithDetails,
  entry: MatchLookupEntry | undefined,
  levels: LevelResponse[]
) {
  // Colored by level when the tournament has levels; tournaments without
  // levels degrade to the stage-item colours used by the detailed cards.
  // The level is assigned on the stage; match.level_id is not populated.
  if (levels.length > 0) return levelColour(entry?.stage.level_id ?? match.level_id, levels);
  return entry != null ? stringToColour(`${entry.stageItem.id}`) : 'gray';
}

function MatchCard({
  block,
  zoom,
  pxPerMinute,
  isViolation,
  hasPlacementWarning,
  isSelected,
  highlightActive,
  isHighlighted,
  stageItemsLookup,
  matchesLookup,
  levels,
  onTap,
}: {
  block: MatchBlock<MatchWithDetails>;
  zoom: 'agenda' | 'compact';
  pxPerMinute: number;
  isViolation: boolean;
  hasPlacementWarning: boolean;
  isSelected: boolean;
  highlightActive: boolean;
  isHighlighted: boolean;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  levels: LevelResponse[];
  onTap: () => void;
}) {
  const { t } = useTranslation();
  const { match } = block;
  const entry = matchesLookup[match.id];
  const color = entry != null ? stringToColour(`${entry.stageItem.id}`) : 'gray';

  // The card covers only the playing time; the margin after the match shows as a
  // calendar-style gap before the next card.
  const cardHeightPx = block.durationMinutes * pxPerMinute;
  // Pick the densest layout that still fits: three rows (time / team 1 / team 2),
  // two rows (time + team 1 / team 2), or a single "time team 1 – team 2" row.
  const rows = cardHeightPx >= 52 ? 3 : cardHeightPx >= 34 ? 2 : 1;
  const fontSize = zoom === 'compact' ? 11 : undefined;
  // A one-row compact card is too narrow for time plus names plus icons; the
  // names win, and both conflict flags collapse into a single icon.
  const showTime = !(zoom === 'compact' && rows === 1);
  const mergeConflictIcons = zoom === 'compact' && rows === 1;

  let input1 = formatMatchInput1(t, stageItemsLookup, matchesLookup, match);
  let input2 = formatMatchInput2(t, stageItemsLookup, matchesLookup, match);
  if (zoom === 'compact') {
    input1 = abbreviateTeamName(input1);
    input2 = abbreviateTeamName(input2);
  }

  const timeLabel = (
    <Text size="xs" fz={fontSize} c="dimmed" lh={1.3} style={{ whiteSpace: 'nowrap' }}>
      {format(block.startTime, 'HH:mm')}
    </Text>
  );
  // Status marker: a check for completed matches (paired with the dimmed card),
  // a pulsing dot for in-progress ones. Upcoming matches carry no marker.
  const statusIndicator =
    match.state === 'COMPLETED' ? (
      <Text component="span" c="teal" fz={fontSize ?? 12} fw={700} lh={1} style={{ flexShrink: 0 }}>
        ✓
      </Text>
    ) : match.state === 'IN_PROGRESS' ? (
      <Box component="span" className={classes.liveDot} />
    ) : null;
  // Agenda also carries the current score once a match has started. Scores are
  // pinned to the card's right edge and never shrink, so they stay visible at
  // every card height — including the one-line layout of short matches, where
  // both scores collapse into a single "1–2" next to the names.
  const showScore = zoom === 'agenda' && match.state !== 'NOT_STARTED';
  const scoreText = (value: string) => (
    <Text
      size="xs"
      fz={fontSize}
      fw={700}
      lh={1.3}
      style={{ flexShrink: 0, marginLeft: 'auto', whiteSpace: 'nowrap' }}
    >
      {value}
    </Text>
  );
  // Agenda is the full-detail level: cards also carry the match's level, stage
  // and stage item. The tallest cards spread that over two rows of their own
  // (level · stage, then stage item), shorter ones get a single combined row,
  // and below that the badge squeezes in next to the time.
  const levelName = levels.find((level) => level.id === entry?.stage.level_id)?.name;
  const contextParts =
    zoom === 'agenda' && rows === 3 && entry != null
      ? [levelName, entry.stage.name, entry.stageItem.name].filter(
          (part): part is string => part != null
        )
      : [];
  const contextRows: string[] =
    contextParts.length === 0
      ? []
      : cardHeightPx >= 96 && contextParts.length > 1
        ? [contextParts.slice(0, -1).join(' · '), contextParts[contextParts.length - 1]]
        : cardHeightPx >= 72
          ? [contextParts.join(' · ')]
          : [];
  const contextBadge = (label: string) => (
    <Badge
      color={color}
      variant="outline"
      size="sm"
      style={{ flexShrink: 1, minWidth: 0, maxWidth: '100%' }}
    >
      {label}
    </Badge>
  );
  const precedenceWarningLabel = match.precedence_conflict
    ? t('precedence_conflict_label', 'Starts before a feeder match has finished')
    : t('match_scheduled_before_previous_stage_label');
  const violationIcon =
    isViolation || match.precedence_conflict ? (
      <Tooltip label={precedenceWarningLabel}>
        <Box
          component="span"
          style={{ flexShrink: 0, display: 'flex', alignItems: 'center', height: '1rem' }}
        >
          <AiFillWarning color="orange" />
        </Box>
      </Tooltip>
    ) : null;
  const shortBreakIcon = match.short_break_conflict ? (
    <Tooltip
      label={t('short_break_conflict_label', 'Break before this match is shorter than the default')}
    >
      <Box
        component="span"
        style={{ flexShrink: 0, display: 'flex', alignItems: 'center', height: '1rem' }}
      >
        <AiFillWarning color="var(--mantine-color-yellow-filled)" />
      </Box>
    </Tooltip>
  ) : null;
  const placementWarningIcon = hasPlacementWarning ? (
    <Tooltip label={t('placement_conflict_preview_label', 'Would double-book a team')}>
      <Box
        component="span"
        style={{ flexShrink: 0, display: 'flex', alignItems: 'center', height: '1rem' }}
      >
        <AiFillWarning color="var(--mantine-color-orange-filled)" />
      </Box>
    </Tooltip>
  ) : null;

  return (
    <Box
      data-match-id={match.id}
      data-highlighted={isHighlighted ? 'true' : undefined}
      data-dimmed={highlightActive && !isHighlighted ? 'true' : undefined}
      data-conflict-preview={hasPlacementWarning ? 'true' : undefined}
      onClick={(event) => {
        event.stopPropagation();
        onTap();
      }}
      style={{
        position: 'absolute',
        top: block.startMinutes * pxPerMinute,
        height: cardHeightPx,
        left: 3,
        right: 3,
        overflow: 'hidden',
        // Every card is tappable: unlocked ones select for placement, locked
        // (played) ones open the action sheet with the move-anyway override.
        cursor: 'pointer',
        opacity:
          highlightActive && !isHighlighted ? 0.22 : match.state === 'COMPLETED' ? 0.55 : undefined,
        borderRadius: 6,
        border: isSelected
          ? '1px solid var(--mantine-color-indigo-filled)'
          : hasPlacementWarning
            ? '1px dashed var(--mantine-color-orange-filled)'
            : '1px solid var(--mantine-color-default-border)',
        borderLeft: `4px solid var(--mantine-color-${color}-filled)`,
        backgroundColor: `var(--mantine-color-${color}-light)`,
        boxShadow: isSelected
          ? '0 0 0 2px var(--mantine-color-indigo-filled)'
          : isHighlighted
            ? '0 0 0 2px var(--mantine-color-teal-filled)'
            : hasPlacementWarning
              ? '0 0 0 2px var(--mantine-color-orange-light)'
              : undefined,
        zIndex: isSelected ? 1 : undefined,
      }}
    >
      <Box
        px={6}
        pt={rows === 3 ? 2 : 0}
        style={{
          height: '100%',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: rows === 3 ? 'flex-start' : 'center',
        }}
      >
        {rows === 3 && (
          <Flex gap={4} justify="space-between" align="center" wrap="nowrap">
            <Flex gap={4} align="center" wrap="nowrap">
              {timeLabel}
              {statusIndicator}
            </Flex>
            {contextRows.length === 0 && contextParts.length > 0
              ? contextBadge(contextParts.join(' · '))
              : null}
            {placementWarningIcon}
            {shortBreakIcon}
            {violationIcon}
          </Flex>
        )}
        {contextRows.map((label) => (
          <Flex key={label} mt={2} wrap="nowrap">
            {contextBadge(label)}
          </Flex>
        ))}
        <Flex gap={6} align="center" wrap="nowrap">
          {rows < 3 && showTime && timeLabel}
          {rows < 3 && statusIndicator}
          {match.stage_item_input1_conflict && <AiFillWarning color="red" />}
          {rows < 3 && placementWarningIcon}
          {rows < 3 && shortBreakIcon}
          {rows === 1 &&
            match.stage_item_input2_conflict &&
            !(mergeConflictIcons && match.stage_item_input1_conflict) && (
              <AiFillWarning color="red" />
            )}
          <Text size="xs" fz={fontSize} fw={600} lh={1.3} truncate style={{ flex: 1 }}>
            {rows === 1 ? `${input1} – ${input2}` : input1}
          </Text>
          {showScore &&
            scoreText(
              rows === 1
                ? `${match.stage_item_input1_score}–${match.stage_item_input2_score}`
                : `${match.stage_item_input1_score}`
            )}
          {rows < 3 && violationIcon}
        </Flex>
        {rows > 1 && (
          <Flex gap={4} align="center" wrap="nowrap">
            {match.stage_item_input2_conflict && <AiFillWarning color="red" />}
            <Text size="xs" fz={fontSize} fw={600} lh={1.3} truncate>
              {input2}
            </Text>
            {showScore && scoreText(`${match.stage_item_input2_score}`)}
          </Flex>
        )}
      </Box>
    </Box>
  );
}

/**
 * Overview rendering of a match: a colored block without text. Colour carries
 * the level, opacity (plus a check) carries the status. Pointer events pass
 * through to the column, whose taps navigate instead of selecting.
 */
function OverviewBlock({
  block,
  pxPerMinute,
  colour,
  isSelected,
  highlightActive,
  isHighlighted,
}: {
  block: MatchBlock<MatchWithDetails>;
  pxPerMinute: number;
  colour: string;
  isSelected: boolean;
  highlightActive: boolean;
  isHighlighted: boolean;
}) {
  const blockHeightPx = block.durationMinutes * pxPerMinute;
  const isCompleted = block.match.state === 'COMPLETED';
  const isInProgress = block.match.state === 'IN_PROGRESS';
  const opacity =
    highlightActive && !isHighlighted ? 0.18 : isCompleted ? 0.35 : isInProgress ? 1 : 0.85;

  return (
    <Box
      data-match-id={block.match.id}
      data-highlighted={isHighlighted ? 'true' : undefined}
      data-dimmed={highlightActive && !isHighlighted ? 'true' : undefined}
      style={{
        position: 'absolute',
        top: block.startMinutes * pxPerMinute,
        height: blockHeightPx,
        left: 1,
        right: 1,
        borderRadius: 2,
        backgroundColor: `var(--mantine-color-${colour}-filled)`,
        opacity,
        boxShadow: isSelected
          ? '0 0 0 2px var(--mantine-color-indigo-filled)'
          : isHighlighted
            ? '0 0 0 2px var(--mantine-color-teal-filled)'
            : undefined,
        zIndex: isSelected ? 1 : undefined,
        pointerEvents: 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {isCompleted && blockHeightPx >= 12 && (
        <Text c="white" fz={Math.min(blockHeightPx - 2, 12)} lh={1}>
          ✓
        </Text>
      )}
      {isInProgress && blockHeightPx >= 12 && (
        <Box
          component="span"
          className={classes.liveDot}
          style={{ backgroundColor: 'var(--mantine-color-white)' }}
        />
      )}
    </Box>
  );
}

function InsertionLineTarget({
  line,
  gridHeight,
  pxPerMinute,
  isNoop,
  hasConflictWarning,
  onTap,
}: {
  line: InsertionLine;
  gridHeight: number;
  pxPerMinute: number;
  isNoop: boolean;
  hasConflictWarning: boolean;
  onTap: () => void;
}) {
  const lineY = line.offsetMinutes * pxPerMinute;
  // The top line sits above minute 0; its hit area may extend into the top
  // inset, but no further (the header would cover it).
  const top = Math.min(
    Math.max(lineY - INSERTION_HIT_AREA_PX / 2, -GRID_TOP_INSET_PX),
    gridHeight - INSERTION_HIT_AREA_PX
  );
  // Keep the visible line on the true boundary even when the hit area is clamped
  // at the grid's edges.
  const lineTop = Math.min(Math.max(0, lineY - top - 2), INSERTION_HIT_AREA_PX - 4);

  return (
    <Box
      data-insertion-index={line.index}
      data-conflict-preview={hasConflictWarning ? 'true' : undefined}
      onClick={(event) => {
        event.stopPropagation();
        onTap();
      }}
      style={{
        position: 'absolute',
        top,
        left: 0,
        right: 0,
        height: INSERTION_HIT_AREA_PX,
        cursor: 'pointer',
        zIndex: 1,
        opacity: isNoop ? 0.35 : 1,
      }}
    >
      <Box
        style={{
          position: 'absolute',
          top: lineTop,
          left: 4,
          right: 4,
          height: 4,
          borderRadius: 2,
          backgroundColor: hasConflictWarning
            ? 'var(--mantine-color-orange-filled)'
            : 'var(--mantine-color-indigo-filled)',
          boxShadow: hasConflictWarning
            ? '0 0 0 1px var(--mantine-color-body), 0 0 0 4px var(--mantine-color-orange-light)'
            : '0 0 0 1px var(--mantine-color-body)',
        }}
      />
    </Box>
  );
}

/**
 * Time-proportional schedule: court columns against a shared vertical time ruler.
 * Card positions and heights are proportional to computed start times and playing
 * durations; the pause after a match shows as a calendar-style gap before the next
 * card.
 *
 * The grid renders at one of three semantic zoom levels: agenda (one court, full
 * cards), compact (3–4 courts, abbreviated cards) or overview (all courts, colored
 * blocks). Tapping a card selects it for placement and insertion lines render at
 * agenda/compact; at overview, taps navigate (zoom in toward the tapped region).
 * Pinch gestures and ctrl+scroll snap between the levels.
 */
export default function ScheduleGrid({
  layout,
  violations,
  conflictPreview,
  stageItemsLookup,
  matchesLookup,
  levels,
  selection,
  highlightTarget,
  zoom,
  focus,
  nowOffsetMinutes,
  nowScrollNonce,
  onSelectionEvent,
}: {
  layout: ScheduleGridLayout<Court, MatchWithDetails>;
  violations: Set<number>;
  conflictPreview: ConflictPreview;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  levels: LevelResponse[];
  selection: SelectionState;
  highlightTarget: HighlightTarget | null;
  zoom: ZoomLevel;
  focus: (FocusTarget & { nonce: number }) | null;
  nowOffsetMinutes: number | null;
  nowScrollNonce: number;
  onSelectionEvent: (event: PlannerEvent) => void;
}) {
  const pxPerMinute = ZOOM_PX_PER_MINUTE[zoom];
  const gridHeight = layout.totalMinutes * pxPerMinute;
  const selectedMatch =
    selection.kind === 'match-selected' || selection.kind === 'action-sheet-open'
      ? selection.match
      : null;
  // Insertion lines only make sense while a match is being placed; with the
  // action sheet open the grid is inert behind the sheet's overlay.
  const placing = selection.kind === 'match-selected' || selection.kind === 'tray-match-selected';
  const isOverview = zoom === 'overview';
  const highlightActive = highlightTarget != null;
  const { t } = useTranslation();

  const containerRef = useRef<HTMLDivElement | null>(null);

  // Soften the otherwise hard cut when the zoom level snaps: restart a short
  // fade/scale-in animation on every level change (but not on first paint).
  const lastAnimatedZoom = useRef(zoom);
  useEffect(() => {
    const element = containerRef.current;
    if (lastAnimatedZoom.current === zoom || element == null) return;
    lastAnimatedZoom.current = zoom;
    element.classList.remove(classes.zoomSnap);
    // Force a reflow so re-adding the class restarts the animation.
    void element.offsetWidth;
    element.classList.add(classes.zoomSnap);
  }, [zoom]);

  // After a zoom change with a focus target (overview tap, anchored pinch or
  // ctrl+wheel), center the focused court/time region. Runs after the
  // re-render at the new zoom level, so measurements are up to date.
  useEffect(() => {
    if (focus == null) return;
    const container = containerRef.current;
    const column = container?.querySelector<HTMLElement>(`[data-court-id="${focus.courtId}"]`);
    if (container == null || column == null) return;

    const columnLeft =
      column.getBoundingClientRect().left -
      container.getBoundingClientRect().left +
      container.scrollLeft;
    const targetY = HEADER_HEIGHT_PX + GRID_TOP_INSET_PX + focus.fraction * gridHeight;
    container.scrollTo({
      left: columnLeft - (container.clientWidth - column.clientWidth) / 2,
      top: targetY - container.clientHeight / 2,
      behavior: 'smooth',
    });
    // Only re-run per navigation event; gridHeight is already the post-zoom scale.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce]);

  useEffect(() => {
    if (nowScrollNonce === 0 || nowOffsetMinutes == null) return;
    const container = containerRef.current;
    if (container == null) return;

    container.scrollTo({
      top: nowLineScrollTop({
        offsetMinutes: nowOffsetMinutes,
        pxPerMinute,
        viewportHeightPx: container.clientHeight,
        headerHeightPx: HEADER_HEIGHT_PX,
        gridTopInsetPx: GRID_TOP_INSET_PX,
      }),
      behavior: 'smooth',
    });
  }, [nowOffsetMinutes, nowScrollNonce, pxPerMinute]);

  return (
    <Box
      ref={containerRef}
      {...{ [PLANNER_GRID_ATTRIBUTE]: true }}
      onClick={() => onSelectionEvent({ type: 'cancel' })}
      style={{
        overflow: 'auto',
        maxHeight: 'calc(100dvh - 14rem)',
        maxWidth: '100%',
        width: 'fit-content',
        border: '1px solid var(--mantine-color-default-border)',
        borderRadius: 8,
        touchAction: 'pan-x pan-y',
      }}
    >
      <Flex wrap="nowrap" style={{ minWidth: 'fit-content' }}>
        <Box
          style={{
            position: 'sticky',
            left: 0,
            zIndex: 3,
            flex: '0 0 auto',
            width: RULER_WIDTH,
            backgroundColor: 'var(--mantine-color-body)',
            borderRight: '1px solid var(--mantine-color-default-border)',
          }}
        >
          <Box
            style={{
              position: 'sticky',
              top: 0,
              zIndex: 4,
              height: HEADER_HEIGHT,
              backgroundColor: 'var(--mantine-color-body)',
              borderBottom: '1px solid var(--mantine-color-default-border)',
            }}
          />
          <Box style={{ position: 'relative', height: gridHeight, marginTop: GRID_TOP_INSET_PX }}>
            {nowOffsetMinutes != null && (
              <Box
                data-now-line="ruler"
                style={{
                  position: 'absolute',
                  top: nowOffsetMinutes * pxPerMinute,
                  left: 0,
                  right: 0,
                  zIndex: 1,
                  borderTop: '2px solid var(--mantine-color-red-filled)',
                  opacity: NOW_LINE_OPACITY,
                }}
              >
                <Text
                  component="span"
                  c="red"
                  fz={10}
                  fw={700}
                  style={{
                    position: 'absolute',
                    top: -8,
                    right: 6,
                    backgroundColor: 'var(--mantine-color-body)',
                    lineHeight: 1,
                  }}
                >
                  {t('now_marker_label', 'Now')}
                </Text>
              </Box>
            )}
            {layout.ticks.map((tick) => (
              <Text
                key={tick.offsetMinutes}
                size="xs"
                c="dimmed"
                ta="right"
                pr={6}
                style={{
                  position: 'absolute',
                  top: tick.offsetMinutes * pxPerMinute,
                  right: 0,
                  transform: tick.offsetMinutes === 0 ? undefined : 'translateY(-50%)',
                  backgroundColor: 'var(--mantine-color-body)',
                }}
              >
                {format(tick.time, 'HH:mm')}
              </Text>
            ))}
          </Box>
        </Box>
        {layout.courts.map(({ court, blocks }) => (
          <Box
            key={court.id}
            data-court-id={court.id}
            style={{
              flex: '0 0 auto',
              width: courtColumnWidth(zoom, layout.courts.length),
              minWidth: isOverview ? 14 : undefined,
              borderRight: '1px solid var(--mantine-color-default-border)',
            }}
          >
            <Box
              px={isOverview ? 2 : 'xs'}
              style={{
                position: 'sticky',
                top: 0,
                zIndex: 2,
                height: HEADER_HEIGHT,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: 'var(--mantine-color-body)',
                borderBottom: '1px solid var(--mantine-color-default-border)',
              }}
            >
              <Text fw={600} fz={isOverview ? 11 : undefined} truncate>
                {isOverview ? shortCourtLabel(court.name) : court.name}
              </Text>
            </Box>
            <Box
              {...{ [COURT_CONTENT_ATTRIBUTE]: court.id }}
              onClick={
                isOverview
                  ? (event) => {
                      event.stopPropagation();
                      const rect = event.currentTarget.getBoundingClientRect();
                      const fraction = Math.min(
                        Math.max((event.clientY - rect.top) / rect.height, 0),
                        1
                      );
                      onSelectionEvent({ type: 'tap-overview', courtId: court.id, fraction });
                    }
                  : undefined
              }
              style={{
                position: 'relative',
                height: gridHeight,
                marginTop: GRID_TOP_INSET_PX,
                cursor: isOverview ? 'zoom-in' : undefined,
              }}
            >
              {layout.ticks.map((tick) =>
                tick.offsetMinutes === 0 ? null : (
                  <Box
                    key={tick.offsetMinutes}
                    style={{
                      position: 'absolute',
                      top: tick.offsetMinutes * pxPerMinute,
                      left: 0,
                      right: 0,
                      borderTop: '1px dashed var(--mantine-color-default-border)',
                      opacity: 0.5,
                    }}
                  />
                )
              )}
              {nowOffsetMinutes != null && (
                <Box
                  data-now-line="court"
                  style={{
                    position: 'absolute',
                    top: nowOffsetMinutes * pxPerMinute,
                    left: 0,
                    right: 0,
                    zIndex: 2,
                    borderTop: '2px solid var(--mantine-color-red-filled)',
                    opacity: NOW_LINE_OPACITY,
                    pointerEvents: 'none',
                  }}
                />
              )}
              {blocks.map((block, blockIndex) => {
                const isHighlighted = matchInvolvesHighlight(
                  block.match,
                  highlightTarget,
                  matchesLookup
                );
                if (isOverview) {
                  return (
                    <OverviewBlock
                      key={block.match.id}
                      block={block}
                      pxPerMinute={pxPerMinute}
                      colour={matchColour(block.match, matchesLookup[block.match.id], levels)}
                      isSelected={selectedMatch?.matchId === block.match.id}
                      highlightActive={highlightActive}
                      isHighlighted={isHighlighted}
                    />
                  );
                }
                const matchRef: GridMatchRef = {
                  matchId: block.match.id,
                  courtId: court.id,
                  position: blockIndex,
                  locked: block.locked,
                };
                return (
                  <MatchCard
                    key={block.match.id}
                    block={block}
                    zoom={zoom}
                    pxPerMinute={pxPerMinute}
                    isViolation={violations.has(block.match.id)}
                    hasPlacementWarning={conflictPreview.swapTargets.has(block.match.id)}
                    isSelected={selectedMatch?.matchId === block.match.id}
                    highlightActive={highlightActive}
                    isHighlighted={isHighlighted}
                    stageItemsLookup={stageItemsLookup}
                    matchesLookup={matchesLookup}
                    levels={levels}
                    onTap={() => onSelectionEvent({ type: 'tap-match', match: matchRef })}
                  />
                );
              })}
              {placing &&
                !isOverview &&
                computeInsertionLines(blocks).map((line) => (
                  <InsertionLineTarget
                    key={line.index}
                    line={line}
                    gridHeight={gridHeight}
                    pxPerMinute={pxPerMinute}
                    isNoop={
                      selectedMatch != null &&
                      selectedMatch.courtId === court.id &&
                      (line.index === selectedMatch.position ||
                        line.index === selectedMatch.position + 1)
                    }
                    hasConflictWarning={conflictPreview.insertionLines.has(
                      insertionLineKey(court.id, line.index)
                    )}
                    onTap={() =>
                      onSelectionEvent({
                        type: 'tap-insertion-line',
                        courtId: court.id,
                        index: line.index,
                      })
                    }
                  />
                ))}
            </Box>
          </Box>
        ))}
      </Flex>
      {/* While placing, add scroll slack so insertion lines near the viewport
          bottom can always be scrolled out from under the floating cancel bar. */}
      {placing && <Box style={{ height: '10rem' }} />}
    </Box>
  );
}
