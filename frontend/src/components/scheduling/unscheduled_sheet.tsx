import {
  Badge,
  Box,
  Collapse,
  Divider,
  Flex,
  Group,
  Paper,
  ScrollArea,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconChevronDown, IconChevronUp } from '@tabler/icons-react';
import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { MatchWithDetails } from '@openapi';
import { MatchLookupEntry, getStageItemLookup, stringToColour } from '@services/lookups';

/**
 * Collapsible bottom sheet listing matches that are not on the schedule yet.
 * Read-only flat list; grouping and the tap-to-place flow come in later slices.
 */
export default function UnscheduledSheet({
  unscheduledMatches,
  stageItemsLookup,
  matchesLookup,
  openMatchModal,
}: {
  unscheduledMatches: MatchWithDetails[];
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  openMatchModal: (m: MatchWithDetails) => void;
}) {
  const { t } = useTranslation();
  const [opened, { toggle }] = useDisclosure(false);

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
        width: 'min(100%, 30rem)',
        zIndex: 150,
        borderTopLeftRadius: 12,
        borderTopRightRadius: 12,
        borderBottom: 'none',
      }}
    >
      <UnstyledButton onClick={toggle} w="100%" p="sm" aria-expanded={opened}>
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
            {unscheduledMatches.length === 0 && (
              <Text c="dimmed" size="sm" pb="xs">
                {t('unscheduled_column_empty_description')}
              </Text>
            )}
            {unscheduledMatches.map((match, index) => {
              const entry = matchesLookup[match.id];
              return (
                <Fragment key={match.id}>
                  {index > 0 && <Divider />}
                  <UnstyledButton onClick={() => openMatchModal(match)} w="100%" py="xs">
                    <Flex justify="space-between" align="center" gap="xs" wrap="nowrap">
                      <Box style={{ minWidth: 0 }}>
                        <Text size="sm" fw={500} truncate>
                          {formatMatchInput1(t, stageItemsLookup, matchesLookup, match)}
                        </Text>
                        <Text size="sm" fw={500} truncate>
                          {formatMatchInput2(t, stageItemsLookup, matchesLookup, match)}
                        </Text>
                      </Box>
                      {entry != null && (
                        <Badge
                          color={stringToColour(`${entry.stageItem.id}`)}
                          variant="outline"
                          style={{ flexShrink: 0 }}
                        >
                          {entry.stage.name} · {entry.stageItem.name}
                        </Badge>
                      )}
                    </Flex>
                  </UnstyledButton>
                </Fragment>
              );
            })}
          </Box>
        </ScrollArea.Autosize>
      </Collapse>
    </Paper>
  );
}
