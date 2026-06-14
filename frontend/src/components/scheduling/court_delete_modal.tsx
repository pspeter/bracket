import { ActionIcon, Badge, Group, Modal, Stack, Text } from '@mantine/core';
import { IconTrash } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { buildCourtManagementList } from '@logic/planning/courts';
import { Court, CourtsResponse, MatchWithDetails } from '@openapi';
import { deleteCourt } from '@services/court';

/**
 * Lists the tournament's courts with a delete control each. Courts still used by
 * matches are rejected by the backend; the match-count badge warns up front.
 * Shared by the desktop courts toolbar and the mobile planner tools sheet.
 */
export default function CourtDeleteModal({
  tournamentId,
  swrCourtsResponse,
  courts,
  matchesByCourtId,
  opened,
  setOpened,
}: {
  tournamentId: number;
  swrCourtsResponse: SWRResponse<CourtsResponse>;
  courts: Court[];
  matchesByCourtId: Record<number, MatchWithDetails[]>;
  opened: boolean;
  setOpened: (opened: boolean) => void;
}) {
  const { t } = useTranslation();
  const entries = buildCourtManagementList(courts, matchesByCourtId);

  return (
    <Modal opened={opened} onClose={() => setOpened(false)} title={t('delete_court_button')}>
      {entries.length < 1 ? (
        <Text c="dimmed">{t('no_courts_title')}</Text>
      ) : (
        <Stack gap="xs">
          {entries.map(({ court, matchCount }) => (
            <Group key={court.id} justify="space-between" wrap="nowrap">
              <Text fw={500} truncate>
                {court.name}
              </Text>
              <Group gap="xs" wrap="nowrap">
                {matchCount > 0 && (
                  <Badge color="orange" variant="light">
                    {t('court_match_count_badge', { count: matchCount })}
                  </Badge>
                )}
                <ActionIcon
                  color="red"
                  variant="light"
                  size="lg"
                  aria-label={`${t('delete_court_button')} ${court.name}`}
                  onClick={async () => {
                    await deleteCourt(tournamentId, court.id);
                    await swrCourtsResponse.mutate();
                  }}
                >
                  <IconTrash size={18} />
                </ActionIcon>
              </Group>
            </Group>
          ))}
        </Stack>
      )}
    </Modal>
  );
}
