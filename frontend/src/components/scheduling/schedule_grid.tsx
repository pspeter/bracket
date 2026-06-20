import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Flex,
  Group,
  Modal,
  NumberInput,
  Popover,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AiFillWarning } from '@react-icons/all-files/ai/AiFillWarning';
import { format } from 'date-fns';
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { RefereeDisplay } from '@components/utils/referee';
import { NEUTRAL_STAGE_ITEM_COLOUR, scoreColour, type StageItemColour } from '@logic/colors';
import { ConflictPreview, insertionLineKey } from '@logic/planning/conflict_preview';
import { HighlightTarget, matchInvolvesHighlight } from '@logic/planning/highlight';
import {
  BreakBlock,
  InsertionLine,
  MatchBlock,
  ScheduleGridLayout,
  computeBreaks,
  computeInsertionLines,
} from '@logic/planning/layout';
import { FocusTarget, GridMatchRef, PlannerEvent, SelectionState } from '@logic/planning/selection';
import {
  ZOOM_PX_PER_MINUTE,
  ZoomLevel,
  abbreviateStageItem,
  abbreviateTeamName,
  shortCourtLabel,
} from '@logic/planning/zoom';
import { Court, MatchWithDetails } from '@openapi';
import { MatchLookupEntry, getStageItemLookup } from '@services/lookups';

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
  colour,
  refereesEnabled,
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
  colour: StageItemColour;
  refereesEnabled: boolean;
  onTap: () => void;
}) {
  const { t } = useTranslation();
  const { match } = block;
  const entry = matchesLookup[match.id];

  // The card covers only the playing time; the margin after the match shows as a
  // calendar-style gap before the next card.
  const cardHeightPx = block.durationMinutes * pxPerMinute;
  // Pick the densest layout that still fits: three rows (time / team 1 / team 2),
  // two rows (badge + team 1 / team 2), or a single "team 1 – team 2" row.
  const rows = cardHeightPx >= 52 ? 3 : cardHeightPx >= 34 ? 2 : 1;
  const fontSize = zoom === 'compact' ? 11 : undefined;
  // A one-row card is too narrow for everything; both conflict flags collapse
  // into a single icon.
  const mergeConflictIcons = rows === 1;

  let input1 = formatMatchInput1(t, stageItemsLookup, matchesLookup, match);
  let input2 = formatMatchInput2(t, stageItemsLookup, matchesLookup, match);
  if (zoom === 'compact') {
    input1 = abbreviateTeamName(input1);
    input2 = abbreviateTeamName(input2);
  }

  // The match's identity badge, shown at every card height: the stage item plus
  // its running match number ("Group C · 3"). The colour already carries the
  // level (and, via its hue cluster, the stage), so the level name is never
  // written; the stage name is prepended only when the card has a line to spare.
  const counter = entry?.matchNumber;
  const itemName = entry?.stageItem.name;
  const stageName = entry?.stage.name;
  const coreFull =
    itemName != null && counter != null ? `${itemName} · ${counter}` : (itemName ?? null);
  const coreShort =
    itemName != null && counter != null
      ? `${abbreviateStageItem(itemName)} · ${counter}`
      : itemName != null
        ? abbreviateStageItem(itemName)
        : null;
  const badgeLabel =
    cardHeightPx >= 72 && stageName != null && coreFull != null
      ? `${stageName} · ${coreFull}`
      : coreFull;
  // Full pill at 2+ rows; a bare coloured token on the shortest one-row cards,
  // where a pill's padding would crowd out the team names.
  // The accent (the level's hue) shares the fill's hue, so using it as text on the
  // fill has no guaranteed contrast. The fill is built so the theme's default text
  // colour always reads on it, so the badge text uses that; the accent stays on the
  // border, where it sits against the page and keeps its contrast.
  const fullBadge = (label: string) => (
    <Badge
      color={colour.accent}
      variant="outline"
      size="sm"
      styles={{ label: { color: 'var(--mantine-color-text)' } }}
      style={{ flexShrink: 1, minWidth: 0, maxWidth: '100%' }}
    >
      {label}
    </Badge>
  );
  const inlineBadge = (label: string) => (
    <Text
      component="span"
      fz={fontSize ?? 10}
      fw={700}
      lh={1.3}
      c="var(--mantine-color-text)"
      style={{ flexShrink: 0, whiteSpace: 'nowrap' }}
    >
      {label}
    </Text>
  );

  const timeLabel = (
    <Text size="xs" fz={fontSize} c="dimmed" lh={1.3} style={{ whiteSpace: 'nowrap' }}>
      {format(block.startTime, 'HH:mm')}
    </Text>
  );
  // Status marker: a check for completed matches, a pulsing dot for in-progress
  // ones. Upcoming matches carry no marker.
  const statusIndicator =
    match.state === 'COMPLETED' ? (
      <Text component="span" c="teal" fz={fontSize ?? 12} fw={700} lh={1} style={{ flexShrink: 0 }}>
        ✓
      </Text>
    ) : match.state === 'IN_PROGRESS' ? (
      <Box component="span" className={classes.liveDot} />
    ) : null;
  // Both zoom levels carry the current score once a match has started. Scores are
  // pinned to the card's right edge as solid winner/loser-coloured chips, so they
  // stay readable on any tint and at every card height — including short matches'
  // one-line layout, where both scores sit side by side next to the names.
  const showScore = match.state !== 'NOT_STARTED';
  const score1Colour = scoreColour(match.stage_item_input1_score, match.stage_item_input2_score);
  const score2Colour = scoreColour(match.stage_item_input2_score, match.stage_item_input1_score);
  const scoreChip = (value: number, chipColour: string) => (
    <Text
      component="span"
      fz={fontSize ?? 12}
      fw={800}
      lh={1}
      style={{
        flexShrink: 0,
        color: '#fff',
        backgroundColor: chipColour,
        borderRadius: 4,
        padding: '1px 5px',
        whiteSpace: 'nowrap',
      }}
    >
      {value}
    </Text>
  );
  const pinnedScores = (...chips: ReactNode[]) => (
    <Box
      style={{ marginLeft: 'auto', flexShrink: 0, display: 'flex', gap: 3, alignItems: 'center' }}
    >
      {chips}
    </Box>
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
  const refereeConflictIcon =
    refereesEnabled && match.referee_conflict ? (
      <Tooltip
        label={t(
          'referee_conflict_label',
          'Referee is playing or refereeing another match during this match'
        )}
      >
        <Box
          component="span"
          style={{ flexShrink: 0, display: 'flex', alignItems: 'center', height: '1rem' }}
        >
          <AiFillWarning color="orange" />
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
        // Every card is tappable: played and frozen-past moves are gated later
        // by the confirmation popup, not by blocking selection here.
        cursor: 'pointer',
        // Completed matches are no longer dimmed (which muddied the tint); the
        // winner/loser-coloured scores carry that they are finished instead.
        opacity: highlightActive && !isHighlighted ? 0.22 : undefined,
        borderRadius: 6,
        border: isSelected
          ? '1px solid var(--mantine-color-indigo-filled)'
          : hasPlacementWarning
            ? '1px dashed var(--mantine-color-orange-filled)'
            : '1px solid var(--mantine-color-default-border)',
        borderLeft: `4px solid ${colour.accent}`,
        backgroundColor: colour.fill,
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
            {badgeLabel != null ? fullBadge(badgeLabel) : null}
            {placementWarningIcon}
            {shortBreakIcon}
            {refereeConflictIcon}
            {violationIcon}
          </Flex>
        )}
        <Flex gap={6} align="center" wrap="nowrap">
          {rows === 2 && coreShort != null && fullBadge(coreShort)}
          {rows === 1 && coreShort != null && inlineBadge(coreShort)}
          {rows < 3 && statusIndicator}
          {match.stage_item_input1_conflict && <AiFillWarning color="red" />}
          {rows < 3 && placementWarningIcon}
          {rows < 3 && shortBreakIcon}
          {rows < 3 && refereeConflictIcon}
          {rows === 1 &&
            match.stage_item_input2_conflict &&
            !(mergeConflictIcons && match.stage_item_input1_conflict) && (
              <AiFillWarning color="red" />
            )}
          <Text size="xs" fz={fontSize} fw={600} lh={1.3} truncate style={{ flex: 1 }}>
            {rows === 1 ? `${input1} – ${input2}` : input1}
          </Text>
          {showScore &&
            (rows === 1
              ? pinnedScores(
                  scoreChip(match.stage_item_input1_score, score1Colour),
                  scoreChip(match.stage_item_input2_score, score2Colour)
                )
              : pinnedScores(scoreChip(match.stage_item_input1_score, score1Colour)))}
          {rows < 3 && violationIcon}
        </Flex>
        {rows > 1 && (
          <Flex gap={4} align="center" wrap="nowrap">
            {match.stage_item_input2_conflict && <AiFillWarning color="red" />}
            <Text size="xs" fz={fontSize} fw={600} lh={1.3} truncate>
              {input2}
            </Text>
            {showScore && pinnedScores(scoreChip(match.stage_item_input2_score, score2Colour))}
          </Flex>
        )}
        {rows >= 2 && (
          <RefereeDisplay
            match={match}
            refereesEnabled={refereesEnabled}
            stageItemsLookup={stageItemsLookup}
          />
        )}
      </Box>
    </Box>
  );
}

/**
 * Overview rendering of a match: a colored block without text. The fill carries
 * the level/stage/item (same tint as the cards), opacity plus a glyph carries the
 * status. Pointer events pass through to the column, whose taps navigate instead
 * of selecting.
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
  colour: StageItemColour;
  isSelected: boolean;
  highlightActive: boolean;
  isHighlighted: boolean;
}) {
  const blockHeightPx = block.durationMinutes * pxPerMinute;
  const isCompleted = block.match.state === 'COMPLETED';
  const isInProgress = block.match.state === 'IN_PROGRESS';
  // The fill is the same capped-light tint the cards use, so a level/stage keeps
  // its colour when zooming out. Blocks render at full opacity (status is carried
  // by the check/live-dot glyphs); only the highlight-dim fades the rest.
  const opacity = highlightActive && !isHighlighted ? 0.25 : undefined;

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
        backgroundColor: colour.fill,
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
        <Text c="var(--mantine-color-text)" fz={Math.min(blockHeightPx - 2, 12)} fw={700} lh={1}>
          ✓
        </Text>
      )}
      {isInProgress && blockHeightPx >= 12 && (
        <Box
          component="span"
          className={classes.liveDot}
          style={{ backgroundColor: colour.accent }}
        />
      )}
    </Box>
  );
}

/**
 * Touch-target height for a break's chip, so even a 0-minute break is comfortably
 * tappable. The target hugs the centered chip — not the full column width — so the
 * match cards on either side keep almost all of their own tap area.
 */
const BREAK_TARGET_HEIGHT_PX = 32;

/**
 * A derived break between two consecutive matches: the calendar-style gap from
 * the previous match's end to the next match's start. Clicking it opens a popup
 * to set the break's duration (with a "default pause duration" reset); a
 * double-click resets it to the default directly. A 0-minute break still renders
 * as a clickable line so a pause can be added anywhere.
 */
function BreakElement({
  breakBlock,
  pxPerMinute,
  asModal,
  onResize,
}: {
  breakBlock: BreakBlock;
  pxPerMinute: number;
  asModal: boolean;
  onResize: (newDurationMinutes: number) => void;
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);
  const [draftMinutes, setDraftMinutes] = useState<number | string>(
    Math.round(breakBlock.durationMinutes)
  );

  const gapMiddle = ((breakBlock.startMinutes + breakBlock.endMinutes) / 2) * pxPerMinute;
  const roundedDuration = Math.round(breakBlock.durationMinutes);

  const apply = (minutes: number) => {
    setOpened(false);
    onResize(Math.max(0, Math.round(minutes)));
  };

  const stepBy = (delta: number) =>
    setDraftMinutes((current) => {
      const value = typeof current === 'number' ? current : Number(current) || 0;
      return Math.max(0, value + delta);
    });

  // The number field. On the small-screen modal the native (tiny) steppers are
  // hidden and the input does not auto-focus, so tapping the editor never pops
  // the iOS keyboard on its own; big +/- buttons drive the value instead.
  const numberField = (
    <NumberInput
      aria-label={t('break_duration_minutes_label', 'Break duration (minutes)')}
      value={draftMinutes}
      onChange={setDraftMinutes}
      min={0}
      step={5}
      suffix={` ${t('minutes_suffix', 'min')}`}
      size={asModal ? 'md' : 'sm'}
      hideControls={asModal}
      {...(asModal ? {} : { 'data-autofocus': true })}
    />
  );

  // The duration form, shared by the desktop popover and the small-screen modal.
  const form = (
    <>
      {asModal ? (
        <Group gap="sm" wrap="nowrap" align="stretch">
          {/* The -/+ buttons adjust the value without focusing the input, so
              stepping never opens the keyboard. */}
          <ActionIcon
            size="xl"
            variant="default"
            aria-label={t('break_decrease_label', 'Decrease break')}
            onClick={() => stepBy(-5)}
          >
            –
          </ActionIcon>
          <Box style={{ flex: 1 }}>{numberField}</Box>
          <ActionIcon
            size="xl"
            variant="default"
            aria-label={t('break_increase_label', 'Increase break')}
            onClick={() => stepBy(5)}
          >
            +
          </ActionIcon>
        </Group>
      ) : (
        numberField
      )}
      <Stack mt="sm" gap={6}>
        <Button
          size="compact-sm"
          fullWidth
          onClick={() =>
            apply(typeof draftMinutes === 'number' ? draftMinutes : Number(draftMinutes) || 0)
          }
        >
          {t('apply_break_button', 'Set')}
        </Button>
        <Button
          size="compact-sm"
          fullWidth
          variant="light"
          onClick={() => apply(breakBlock.defaultBreakMinutes)}
        >
          {t('default_pause_duration_button', 'Default pause duration')}
        </Button>
      </Stack>
    </>
  );

  // The chip is the tap target: full band height for a comfortable touch area,
  // but only as wide as the label so it stays clear of the cards.
  const chip = (
    <Box
      aria-label={t('edit_break_aria_label', 'Edit break')}
      data-break-before-match-id={breakBlock.matchId}
      onClick={(event) => {
        event.stopPropagation();
        setDraftMinutes(roundedDuration);
        setOpened((value) => !value);
      }}
      onDoubleClick={(event) => {
        event.stopPropagation();
        setOpened(false);
        onResize(breakBlock.defaultBreakMinutes);
      }}
      style={{
        position: 'absolute',
        top: 0,
        bottom: 0,
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        cursor: 'pointer',
        pointerEvents: 'auto',
      }}
    >
      <Text
        component="span"
        fz={10}
        c="dimmed"
        style={{
          lineHeight: 1,
          padding: '1px 6px',
          borderRadius: 4,
          backgroundColor: 'var(--mantine-color-body)',
          border: '1px solid var(--mantine-color-default-border)',
          whiteSpace: 'nowrap',
        }}
      >
        {t('break_minutes_short', '{{count}}m', { count: roundedDuration })}
      </Text>
    </Box>
  );

  return (
    // A full-width band centered on the break, but click-through: only the chip
    // inside it captures taps, so the cards on either side keep their tap area.
    <Box
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: gapMiddle - BREAK_TARGET_HEIGHT_PX / 2,
        height: BREAK_TARGET_HEIGHT_PX,
        pointerEvents: 'none',
        zIndex: 1,
      }}
    >
      {/* The break line: full width, visual only — taps fall through to the cards. */}
      <Box
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: BREAK_TARGET_HEIGHT_PX / 2,
          borderTop: '1px dashed var(--mantine-color-dimmed)',
          opacity: 0.7,
        }}
      />
      {asModal ? (
        <>
          {chip}
          {/* On phones an anchored popover can open off-screen, so the editor
              becomes a centered modal that is always fully visible. */}
          <Modal
            opened={opened}
            onClose={() => setOpened(false)}
            centered
            size="xs"
            title={t('break_popover_title', 'Break duration')}
            // Above the action sheet (400) and selection pill, so it is never covered.
            zIndex={500}
            // On iOS the keyboard sliding up shifts the centered modal, and the
            // delayed synthetic click then lands outside it — which would dismiss
            // the edit. Require an explicit close (the X or a button) instead.
            closeOnClickOutside={false}
          >
            {form}
          </Modal>
        </>
      ) : (
        <Popover
          opened={opened}
          onChange={setOpened}
          position="right"
          withArrow
          shadow="md"
          trapFocus
          width={220}
        >
          <Popover.Target>{chip}</Popover.Target>
          <Popover.Dropdown onClick={(event) => event.stopPropagation()}>
            <Text size="sm" fw={600} mb={6}>
              {t('break_popover_title', 'Break duration')}
            </Text>
            {form}
          </Popover.Dropdown>
        </Popover>
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
  stageItemColours,
  selection,
  highlightTarget,
  zoom,
  focus,
  nowOffsetMinutes,
  refereesEnabled = false,
  onSelectionEvent,
}: {
  layout: ScheduleGridLayout<Court, MatchWithDetails>;
  violations: Set<number>;
  conflictPreview: ConflictPreview;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  stageItemColours: Record<number, StageItemColour>;
  selection: SelectionState;
  highlightTarget: HighlightTarget | null;
  zoom: ZoomLevel;
  focus: (FocusTarget & { nonce: number }) | null;
  nowOffsetMinutes: number | null;
  refereesEnabled?: boolean;
  onSelectionEvent: (event: PlannerEvent) => void;
}) {
  const pxPerMinute = ZOOM_PX_PER_MINUTE[zoom];
  const gridHeight = layout.totalMinutes * pxPerMinute;
  // On phones an anchored break popover can open off-screen, so the editor
  // switches to a centered modal at the same breakpoint as the default zoom.
  const editBreaksInModal = useMediaQuery('(max-width: 768px)') ?? false;
  const selectedMatch =
    selection.kind === 'match-selected'
      ? selection.match
      : selection.kind === 'confirm-move' && selection.previous.kind === 'match-selected'
        ? selection.previous.match
        : null;
  // Insertion lines only make sense while a match is being placed; with a move
  // confirmation pending, the grid is inert behind the modal overlay.
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
  // ctrl+wheel), center the focused court/time region. A layout effect with an
  // instant scroll snaps the grid to the target before the browser paints the
  // new zoom level: otherwise the re-render at the new scale paints once at the
  // now-stale scroll offset (a jump to a canvas edge) before a smooth scroll
  // pans across to the target. Runs after the re-render, so measurements match
  // the post-zoom layout.
  useLayoutEffect(() => {
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
      behavior: 'auto',
    });
    // Only re-run per navigation event; gridHeight is already the post-zoom scale.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce]);

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
                const entry = matchesLookup[block.match.id];
                const colour =
                  (entry != null ? stageItemColours[entry.stageItem.id] : undefined) ??
                  NEUTRAL_STAGE_ITEM_COLOUR;
                if (isOverview) {
                  return (
                    <OverviewBlock
                      key={block.match.id}
                      block={block}
                      pxPerMinute={pxPerMinute}
                      colour={colour}
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
                  played: block.match.state !== 'NOT_STARTED',
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
                    colour={colour}
                    refereesEnabled={refereesEnabled}
                    onTap={() => onSelectionEvent({ type: 'tap-match', match: matchRef })}
                  />
                );
              })}
              {/* Breaks are the resting state of a court lane; while placing a
                  match, insertion lines take their place instead. */}
              {!placing &&
                !isOverview &&
                computeBreaks(blocks)
                  .filter((breakBlock) => !breakBlock.locked)
                  .map((breakBlock) => (
                    <BreakElement
                      key={breakBlock.matchId}
                      breakBlock={breakBlock}
                      pxPerMinute={pxPerMinute}
                      asModal={editBreaksInModal}
                      onResize={(newDurationMinutes) =>
                        onSelectionEvent({
                          type: 'resize-break',
                          matchId: breakBlock.matchId,
                          newDurationMinutes,
                        })
                      }
                    />
                  ))}
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
