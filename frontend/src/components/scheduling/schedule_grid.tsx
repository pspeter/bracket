import { Box, Flex, Text, Tooltip } from '@mantine/core';
import { AiFillWarning } from '@react-icons/all-files/ai/AiFillWarning';
import { format } from 'date-fns';
import { useTranslation } from 'react-i18next';

import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import {
  InsertionLine,
  MatchBlock,
  ScheduleGridLayout,
  computeInsertionLines,
} from '@logic/planning/layout';
import { GridMatchRef, SelectionEvent, SelectionState } from '@logic/planning/selection';
import { Court, MatchWithDetails } from '@openapi';
import { MatchLookupEntry, getStageItemLookup, stringToColour } from '@services/lookups';

/** Vertical scale of the grid: one minute of schedule time takes this many pixels. */
const PX_PER_MINUTE = 5;
const COURT_COLUMN_WIDTH = '14rem';
const RULER_WIDTH = '3.25rem';
const HEADER_HEIGHT = '2.5rem';
/** Height of an insertion line's tap target; the visible line is centered inside it. */
const INSERTION_HIT_AREA_PX = 32;
/**
 * Breathing space between the header and minute 0, applied to the ruler and all
 * court columns alike so time alignment is preserved. Gives the topmost insertion
 * line room above the first match, so moving a match to the front of a court is
 * an easy tap.
 */
const GRID_TOP_INSET_PX = 32;

function MatchCard({
  block,
  isViolation,
  isSelected,
  stageItemsLookup,
  matchesLookup,
  onTap,
}: {
  block: MatchBlock<MatchWithDetails>;
  isViolation: boolean;
  isSelected: boolean;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  onTap: () => void;
}) {
  const { t } = useTranslation();
  const { match } = block;
  const entry = matchesLookup[match.id];
  const color = entry != null ? stringToColour(`${entry.stageItem.id}`) : 'gray';

  // The card covers only the playing time; the margin after the match shows as a
  // calendar-style gap before the next card.
  const cardHeightPx = block.durationMinutes * PX_PER_MINUTE;
  // Pick the densest layout that still fits: three rows (time / team 1 / team 2),
  // two rows (time + team 1 / team 2), or a single "time team 1 – team 2" row.
  const rows = cardHeightPx >= 52 ? 3 : cardHeightPx >= 34 ? 2 : 1;

  const input1 = formatMatchInput1(t, stageItemsLookup, matchesLookup, match);
  const input2 = formatMatchInput2(t, stageItemsLookup, matchesLookup, match);

  const timeLabel = (
    <Text size="xs" c="dimmed" lh={1.3} style={{ whiteSpace: 'nowrap' }}>
      {format(block.startTime, 'HH:mm')}
    </Text>
  );
  const violationIcon = isViolation ? (
    <Tooltip label={t('match_scheduled_before_previous_stage_label')}>
      <Box
        component="span"
        style={{ flexShrink: 0, display: 'flex', alignItems: 'center', height: '1rem' }}
      >
        <AiFillWarning color="orange" />
      </Box>
    </Tooltip>
  ) : null;

  return (
    <Box
      onClick={(event) => {
        event.stopPropagation();
        onTap();
      }}
      style={{
        position: 'absolute',
        top: block.startMinutes * PX_PER_MINUTE,
        height: cardHeightPx,
        left: 3,
        right: 3,
        overflow: 'hidden',
        cursor: 'pointer',
        borderRadius: 6,
        border: isSelected
          ? '1px solid var(--mantine-color-indigo-filled)'
          : '1px solid var(--mantine-color-default-border)',
        borderLeft: `4px solid var(--mantine-color-${color}-filled)`,
        backgroundColor: `var(--mantine-color-${color}-light)`,
        boxShadow: isSelected ? '0 0 0 2px var(--mantine-color-indigo-filled)' : undefined,
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
            {timeLabel}
            {violationIcon}
          </Flex>
        )}
        <Flex gap={6} align="center" wrap="nowrap">
          {rows < 3 && timeLabel}
          {match.stage_item_input1_conflict && <AiFillWarning color="red" />}
          {rows === 1 && match.stage_item_input2_conflict && <AiFillWarning color="red" />}
          <Text size="xs" fw={600} lh={1.3} truncate style={{ flex: 1 }}>
            {rows === 1 ? `${input1} – ${input2}` : input1}
          </Text>
          {rows < 3 && violationIcon}
        </Flex>
        {rows > 1 && (
          <Flex gap={4} align="center" wrap="nowrap">
            {match.stage_item_input2_conflict && <AiFillWarning color="red" />}
            <Text size="xs" fw={600} lh={1.3} truncate>
              {input2}
            </Text>
          </Flex>
        )}
      </Box>
    </Box>
  );
}

function InsertionLineTarget({
  line,
  gridHeight,
  isNoop,
  onTap,
}: {
  line: InsertionLine;
  gridHeight: number;
  isNoop: boolean;
  onTap: () => void;
}) {
  const lineY = line.offsetMinutes * PX_PER_MINUTE;
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
          backgroundColor: 'var(--mantine-color-indigo-filled)',
          boxShadow: '0 0 0 1px var(--mantine-color-body)',
        }}
      />
    </Box>
  );
}

/**
 * Time-proportional schedule: court columns against a shared vertical time ruler.
 * Card positions and heights are proportional to computed start times and playing
 * durations; the pause after a match shows as a calendar-style gap before the next
 * card. Tapping a card selects it for placement; while a match is selected,
 * insertion lines render between matches and taps on them dispatch placement events.
 */
export default function ScheduleGrid({
  layout,
  violations,
  stageItemsLookup,
  matchesLookup,
  selection,
  onSelectionEvent,
}: {
  layout: ScheduleGridLayout<Court, MatchWithDetails>;
  violations: Set<number>;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  selection: SelectionState;
  onSelectionEvent: (event: SelectionEvent) => void;
}) {
  const gridHeight = layout.totalMinutes * PX_PER_MINUTE;
  const selectedMatch = selection.kind === 'match-selected' ? selection.match : null;
  const placing = selection.kind !== 'idle';

  return (
    <Box
      onClick={() => onSelectionEvent({ type: 'cancel' })}
      style={{
        overflow: 'auto',
        maxHeight: 'calc(100dvh - 14rem)',
        maxWidth: '100%',
        width: 'fit-content',
        border: '1px solid var(--mantine-color-default-border)',
        borderRadius: 8,
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
            {layout.ticks.map((tick) => (
              <Text
                key={tick.offsetMinutes}
                size="xs"
                c="dimmed"
                ta="right"
                pr={6}
                style={{
                  position: 'absolute',
                  top: tick.offsetMinutes * PX_PER_MINUTE,
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
            style={{
              flex: '0 0 auto',
              width: COURT_COLUMN_WIDTH,
              borderRight: '1px solid var(--mantine-color-default-border)',
            }}
          >
            <Box
              px="xs"
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
              <Text fw={600} truncate>
                {court.name}
              </Text>
            </Box>
            <Box style={{ position: 'relative', height: gridHeight, marginTop: GRID_TOP_INSET_PX }}>
              {layout.ticks.map((tick) =>
                tick.offsetMinutes === 0 ? null : (
                  <Box
                    key={tick.offsetMinutes}
                    style={{
                      position: 'absolute',
                      top: tick.offsetMinutes * PX_PER_MINUTE,
                      left: 0,
                      right: 0,
                      borderTop: '1px dashed var(--mantine-color-default-border)',
                      opacity: 0.5,
                    }}
                  />
                )
              )}
              {blocks.map((block, blockIndex) => {
                const matchRef: GridMatchRef = {
                  matchId: block.match.id,
                  courtId: court.id,
                  position: block.match.position_in_schedule ?? blockIndex,
                };
                return (
                  <MatchCard
                    key={block.match.id}
                    block={block}
                    isViolation={violations.has(block.match.id)}
                    isSelected={selectedMatch?.matchId === block.match.id}
                    stageItemsLookup={stageItemsLookup}
                    matchesLookup={matchesLookup}
                    onTap={() => onSelectionEvent({ type: 'tap-match', match: matchRef })}
                  />
                );
              })}
              {placing &&
                computeInsertionLines(blocks).map((line) => (
                  <InsertionLineTarget
                    key={line.index}
                    line={line}
                    gridHeight={gridHeight}
                    isNoop={
                      selectedMatch != null &&
                      selectedMatch.courtId === court.id &&
                      (line.index === selectedMatch.position ||
                        line.index === selectedMatch.position + 1)
                    }
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
