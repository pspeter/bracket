import { ActionIcon, Badge, Button, Group, Menu, Modal, Stack, Text } from '@mantine/core';
import { IconAdjustmentsHorizontal, IconPlus, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import CourtModal from '@components/modals/create_court_modal';
import { buildCourtManagementList } from '@logic/planning/courts';
import { Court, CourtsResponse, MatchWithDetails } from '@openapi';
import { deleteCourt } from '@services/court';

/**
 * Toolbar menu for managing courts from the planning view. Court add/delete
 * lives here, instead of in per-column grid headers, so it stays reachable on
 * small screens without consuming grid space.
 */
export default function CourtsToolbar({
  tournamentId,
  swrCourtsResponse,
  courts,
  matchesByCourtId,
}: {
  tournamentId: number;
  swrCourtsResponse: SWRResponse<CourtsResponse>;
  courts: Court[];
  matchesByCourtId: Record<number, MatchWithDetails[]>;
}) {
  const { t } = useTranslation();
  const [addOpened, setAddOpened] = useState(false);
  const [deleteOpened, setDeleteOpened] = useState(false);
  const entries = buildCourtManagementList(courts, matchesByCourtId);

  return (
    <>
      <CourtModal
        tournamentId={tournamentId}
        swrCourtsResponse={swrCourtsResponse}
        opened={addOpened}
        setOpened={setAddOpened}
      />
      <Modal
        opened={deleteOpened}
        onClose={() => setDeleteOpened(false)}
        title={t('delete_court_button')}
      >
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
                      // Courts still used by matches are rejected by the backend
                      // with an error notification; the badge warns up front.
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
      <Menu shadow="md" position="bottom-end">
        <Menu.Target>
          <Button
            variant="default"
            size="md"
            style={{ marginBottom: 10 }}
            leftSection={<IconAdjustmentsHorizontal size={20} />}
          >
            {t('courts_button')}
          </Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item leftSection={<IconPlus size={18} />} onClick={() => setAddOpened(true)}>
            {t('add_court_title')}
          </Menu.Item>
          <Menu.Item
            color="red"
            leftSection={<IconTrash size={18} />}
            onClick={() => setDeleteOpened(true)}
          >
            {t('delete_court_button')}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
    </>
  );
}
