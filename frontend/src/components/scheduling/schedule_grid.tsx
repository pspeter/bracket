import { Box, Flex, Text, Tooltip } from '@mantine/core';
import { AiFillWarning } from '@react-icons/all-files/ai/AiFillWarning';
import { format } from 'date-fns';
import { useTranslation } from 'react-i18next';

import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { MatchBlock, ScheduleGridLayout } from '@logic/planning/layout';
import { Court, MatchWithDetails } from '@openapi';
import { MatchLookupEntry, getStageItemLookup, stringToColour } from '@services/lookups';

/** Vertical scale of the grid: one minute of schedule time takes this many pixels. */
const PX_PER_MINUTE = 5;
const COURT_COLUMN_WIDTH = '14rem';
const RULER_WIDTH = '3.25rem';
const HEADER_HEIGHT = '2.5rem';

function MatchCard({
  block,
  isViolation,
  stageItemsLookup,
  matchesLookup,
  openMatchModal,
}: {
  block: MatchBlock<MatchWithDetails>;
  isViolation: boolean;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  openMatchModal: (m: MatchWithDetails) => void;
}) {
  const { t } = useTranslation();
  const { match } = block;
  const entry = matchesLookup[match.id];
  const color = entry != null ? stringToColour(`${entry.stageItem.id}`) : 'gray';

  return (
    <Box
      onClick={() => openMatchModal(match)}
      style={{
        position: 'absolute',
        top: block.startMinutes * PX_PER_MINUTE,
        height: (block.endMinutes - block.startMinutes) * PX_PER_MINUTE,
        left: 3,
        right: 3,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        cursor: 'pointer',
        borderRadius: 6,
        border: '1px solid var(--mantine-color-default-border)',
        borderLeft: `4px solid var(--mantine-color-${color}-filled)`,
        backgroundColor: `var(--mantine-color-${color}-light)`,
      }}
    >
      <Box px={6} pt={2} style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <Flex gap={4} justify="space-between" align="center" wrap="nowrap">
          <Text size="xs" c="dimmed" lh={1.3} style={{ whiteSpace: 'nowrap' }}>
            {format(block.startTime, 'HH:mm')}
          </Text>
          {isViolation && (
            <Tooltip label={t('match_scheduled_before_previous_stage_label')}>
              <Box
                component="span"
                style={{ flexShrink: 0, display: 'flex', alignItems: 'center', height: '1rem' }}
              >
                <AiFillWarning color="orange" />
              </Box>
            </Tooltip>
          )}
        </Flex>
        <Flex gap={4} align="center" wrap="nowrap">
          {match.stage_item_input1_conflict && <AiFillWarning color="red" />}
          <Text size="xs" fw={600} lh={1.3} truncate>
            {formatMatchInput1(t, stageItemsLookup, matchesLookup, match)}
          </Text>
        </Flex>
        <Flex gap={4} align="center" wrap="nowrap">
          {match.stage_item_input2_conflict && <AiFillWarning color="red" />}
          <Text size="xs" fw={600} lh={1.3} truncate>
            {formatMatchInput2(t, stageItemsLookup, matchesLookup, match)}
          </Text>
        </Flex>
      </Box>
      {block.marginMinutes > 0 && (
        <Box
          style={{
            flex: '0 0 auto',
            height: block.marginMinutes * PX_PER_MINUTE,
            borderTop: '1px dashed var(--mantine-color-default-border)',
            background:
              'repeating-linear-gradient(-45deg, transparent 0 5px, var(--mantine-color-default-border) 5px 7px)',
            opacity: 0.35,
          }}
        />
      )}
    </Box>
  );
}

/**
 * Read-only, time-proportional schedule: court columns against a shared vertical time
 * ruler. Card positions and heights are proportional to computed start times and
 * durations; the pause after a match renders as a striped tail on its card.
 */
export default function ScheduleGrid({
  layout,
  violations,
  stageItemsLookup,
  matchesLookup,
  openMatchModal,
}: {
  layout: ScheduleGridLayout<Court, MatchWithDetails>;
  violations: Set<number>;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  openMatchModal: (m: MatchWithDetails) => void;
}) {
  const gridHeight = layout.totalMinutes * PX_PER_MINUTE;

  return (
    <Box
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
          <Box style={{ position: 'relative', height: gridHeight }}>
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
            <Box style={{ position: 'relative', height: gridHeight }}>
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
              {blocks.map((block) => (
                <MatchCard
                  key={block.match.id}
                  block={block}
                  isViolation={violations.has(block.match.id)}
                  stageItemsLookup={stageItemsLookup}
                  matchesLookup={matchesLookup}
                  openMatchModal={openMatchModal}
                />
              ))}
            </Box>
          </Box>
        ))}
      </Flex>
    </Box>
  );
}
