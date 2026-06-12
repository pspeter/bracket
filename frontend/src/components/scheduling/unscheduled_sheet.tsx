import {
  Badge,
  Box,
  Collapse,
  Divider,
  Flex,
  Group,
  Paper,
  ScrollArea,
  Stack,
  Text,
  ThemeIcon,
  UnstyledButton,
} from '@mantine/core';
import { IconCheck, IconChevronDown, IconChevronUp } from '@tabler/icons-react';
import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import {
  groupUnscheduledMatchesForTray,
  type TrayMatchGroups,
} from '@logic/planning/unscheduled_tray';
import { levelColour } from '@logic/planning/zoom';
import type { LevelResponse, MatchWithDetails } from '@openapi';
import { getStageItemLookup, type MatchLookupEntry, stringToColour } from '@services/lookups';

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
  opened,
  onToggle,
  onSelectMatch,
}: {
  unscheduledMatches: MatchWithDetails[];
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  levels: LevelResponse[];
  opened: boolean;
  onToggle: () => void;
  onSelectMatch: (m: MatchWithDetails) => void;
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
    const label =
      badgeLabel ?? (entry != null ? `${entry.stage.name} · ${entry.stageItem.name}` : null);

    return (
      <UnstyledButton key={match.id} onClick={() => onSelectMatch(match)} w="100%" py="xs">
        <Flex justify="space-between" align="center" gap="xs" wrap="nowrap">
          <Box style={{ minWidth: 0 }}>
            <Text size="sm" fw={500} truncate>
              {formatMatchInput1(t, stageItemsLookup, matchesLookup, match)}
            </Text>
            <Text size="sm" fw={500} truncate>
              {formatMatchInput2(t, stageItemsLookup, matchesLookup, match)}
            </Text>
          </Box>
          {entry != null && label != null && (
            <Badge
              color={stringToColour(`${entry.stageItem.id}`)}
              variant="outline"
              style={{ flexShrink: 0 }}
            >
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
              <Badge size="sm" color={levelColour(level.id, levels)} variant="light">
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
    <Paper
      shadow="lg"
      radius={0}
      withBorder
      style={{
        position: 'fixed',
        bottom: 0,
        left: '50%',
        transform: 'translateX(-50%)',
        width: `min(100%, ${preferredTrayWidthRem}rem)`,
        zIndex: 150,
        borderTopLeftRadius: 12,
        borderTopRightRadius: 12,
        borderBottom: 'none',
      }}
    >
      <UnstyledButton onClick={onToggle} w="100%" p="sm" aria-expanded={opened}>
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
  );
}
