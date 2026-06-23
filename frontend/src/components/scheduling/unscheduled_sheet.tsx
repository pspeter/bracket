import {
  Badge,
  Box,
  Collapse,
  Divider,
  Flex,
  Group,
  Paper,
  Portal,
  ScrollArea,
  Stack,
  Text,
  ThemeIcon,
  UnstyledButton,
} from '@mantine/core';
import { IconCheck, IconChevronDown, IconChevronUp } from '@tabler/icons-react';
import { Fragment, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { levelSwatchColour, NEUTRAL_STAGE_ITEM_COLOUR, type StageItemColour } from '@logic/colors';
import {
  groupUnscheduledMatchesForTray,
  type TrayMatchGroups,
} from '@logic/planning/unscheduled_tray';
import type { LevelResponse, MatchWithDetails } from '@openapi';
import { getStageItemLookup, type MatchLookupEntry } from '@services/lookups';
import { PLANNER_DESELECT_IGNORE_ATTRIBUTE } from './planner_anchor';

/**
 * Collapsible bottom sheet listing matches that are not on the schedule yet.
 * Tapping a match selects it for tap-to-place placement on the grid; the parent
 * collapses the sheet while placing, so `opened` is controlled.
 */
export default function UnscheduledSheet({
  unscheduledMatches,
  stageItemsLookup,
  matchesLookup,
  levels,
  stageItemColours,
  opened,
  hidden = false,
  onToggle,
  onSelectMatch,
  rightSection,
}: {
  unscheduledMatches: MatchWithDetails[];
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  levels: LevelResponse[];
  stageItemColours: Record<number, StageItemColour>;
  opened: boolean;
  // When true, slide the entire sheet down off the bottom of the screen (kept
  // mounted so the slide animates). Used to clear it out of the way on phones
  // while a match is being placed.
  hidden?: boolean;
  onToggle: () => void;
  onSelectMatch: (m: MatchWithDetails) => void;
  // Optional control rendered to the right of the toggle (the mobile tools
  // button); it sits outside the toggle so tapping it doesn't expand the tray.
  rightSection?: ReactNode;
}) {
  const { t } = useTranslation();
  const groups = groupUnscheduledMatchesForTray(unscheduledMatches, matchesLookup, levels);
  const visibleLevelCount = groups.kind === 'grouped' ? groups.levels.length : 1;
  const preferredTrayWidthRem =
    groups.kind === 'grouped'
      ? Math.max(30, visibleLevelCount * 18 + Math.max(visibleLevelCount - 1, 0) * 0.75 + 2)
      : 30;

  function renderMatchRow(match: MatchWithDetails, badgeLabel?: string) {
    const entry = matchesLookup[match.id];
    const baseLabel =
      badgeLabel ?? (entry != null ? `${entry.stage.name} · ${entry.stageItem.name}` : null);
    // Mirror the grid badge: round number for swiss/elimination, match number for round-robin.
    const isRoundRobin = entry?.stageItem.type === 'ROUND_ROBIN';
    const counter = isRoundRobin ? entry?.matchNumber : entry?.roundNumber;
    const label =
      baseLabel != null && entry != null ? `${baseLabel} · ${counter}` : baseLabel;
    const colour =
      (entry != null ? stageItemColours[entry.stageItem.id] : undefined) ??
      NEUTRAL_STAGE_ITEM_COLOUR;
    const emptyLabelKey = entry?.round.lifecycle_state === 'PLACEHOLDER' ? 'tbd_label' : 'empty_slot';

    return (
      <UnstyledButton key={match.id} onClick={() => onSelectMatch(match)} w="100%" py="xs">
        <Flex justify="space-between" align="center" gap="xs" wrap="nowrap">
          <Box style={{ minWidth: 0 }}>
            <Text size="sm" fw={500} truncate>
              {formatMatchInput1(t, stageItemsLookup, matchesLookup, match, emptyLabelKey)}
            </Text>
            <Text size="sm" fw={500} truncate>
              {formatMatchInput2(t, stageItemsLookup, matchesLookup, match, emptyLabelKey)}
            </Text>
          </Box>
          {entry != null && label != null && (
            <Badge color={colour.accent} variant="outline" style={{ flexShrink: 0 }}>
              {label}
            </Badge>
          )}
        </Flex>
      </UnstyledButton>
    );
  }

  function renderMatchList(
    matches: MatchWithDetails[],
    badgeLabel?: (match: MatchWithDetails) => string
  ) {
    return matches.map((match, index) => (
      <Fragment key={match.id}>
        {index > 0 && <Divider />}
        {renderMatchRow(match, badgeLabel?.(match))}
      </Fragment>
    ));
  }

  function renderGroups(groupedMatches: TrayMatchGroups) {
    if (groupedMatches.kind === 'flat') {
      return renderMatchList(groupedMatches.matches);
    }

    return (
      <Box
        style={{
          display: 'grid',
          gap: 'var(--mantine-spacing-sm)',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 18rem), 1fr))',
          alignItems: 'start',
        }}
      >
        {groupedMatches.levels.map((level) => (
          <Box key={level.id ?? 'none'}>
            <Group justify="space-between" gap="xs" mb={4}>
              <Text size="md" fw={700} tt="uppercase">
                {level.name || t('all_levels_label')}
              </Text>
              <Badge
                size="sm"
                color={level.id != null ? levelSwatchColour(level.id, levels) : undefined}
                variant="light"
              >
                {level.stages.reduce((count, stage) => count + stage.matches.length, 0)}
              </Badge>
            </Group>
            <Stack gap="xs">
              {level.stages.map((stage) => (
                <Box key={stage.id}>
                  <Text size="sm" fw={600} c="dimmed" mb={2}>
                    {stage.name}
                  </Text>
                  <Box>
                    {renderMatchList(
                      stage.matches,
                      (match) => matchesLookup[match.id]?.stageItem.name
                    )}
                  </Box>
                </Box>
              ))}
            </Stack>
          </Box>
        ))}
      </Box>
    );
  }

  return (
    // Portal to the body so the fixed positioning is viewport-relative: the
    // planning page wraps the grid in a `container-type: inline-size` box, which
    // establishes a containing block for fixed descendants and would otherwise
    // pin this sheet to the (often short) grid's bottom instead of the screen.
    <Portal>
      <Paper
        {...{ [PLANNER_DESELECT_IGNORE_ATTRIBUTE]: true }}
        shadow="lg"
        radius={0}
        withBorder
        style={{
          position: 'fixed',
          bottom: 0,
          left: '50%',
          // `calc(100% + 1px)` clears the shadow's top edge too, so nothing
          // peeks above the screen bottom while hidden.
          transform: hidden ? 'translate(-50%, calc(100% + 1px))' : 'translateX(-50%)',
          transition: 'transform 200ms ease',
          width: `min(100%, ${preferredTrayWidthRem}rem)`,
          zIndex: 150,
          borderTopLeftRadius: 12,
          borderTopRightRadius: 12,
          borderBottom: 'none',
        }}
      >
        <Group justify="space-between" wrap="nowrap" gap="xs" p="sm">
          <UnstyledButton
            onClick={onToggle}
            style={{ flex: 1, minWidth: 0 }}
            aria-expanded={opened}
          >
            <Group justify="space-between" wrap="nowrap">
              <Group gap="xs" wrap="nowrap">
                <Text fw={600}>{t('unscheduled_title')}</Text>
                <Badge color={unscheduledMatches.length > 0 ? 'indigo' : 'green'} variant="filled">
                  {unscheduledMatches.length}
                </Badge>
              </Group>
              {opened ? <IconChevronDown size={20} /> : <IconChevronUp size={20} />}
            </Group>
          </UnstyledButton>
          {rightSection}
        </Group>
        <Collapse in={opened}>
          <ScrollArea.Autosize mah="45dvh">
            <Box px="sm" pb="sm">
              {unscheduledMatches.length === 0 ? (
                <Group gap="sm" py="xs" wrap="nowrap">
                  <ThemeIcon color="green" variant="light" radius="xl">
                    <IconCheck size={18} />
                  </ThemeIcon>
                  <Box>
                    <Text size="sm" fw={600}>
                      {t('all_matches_scheduled_title')}
                    </Text>
                    <Text c="dimmed" size="sm">
                      {t('unscheduled_column_empty_description')}
                    </Text>
                  </Box>
                </Group>
              ) : (
                renderGroups(groups)
              )}
            </Box>
          </ScrollArea.Autosize>
        </Collapse>
      </Paper>
    </Portal>
  );
}
