import { Button, Menu } from '@mantine/core';
import { IconAdjustmentsHorizontal, IconPlus, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import CourtModal from '@components/modals/create_court_modal';
import CourtDeleteModal from '@components/scheduling/court_delete_modal';
import { Court, CourtsResponse, MatchWithDetails } from '@openapi';

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

  return (
    <>
      <CourtModal
        tournamentId={tournamentId}
        swrCourtsResponse={swrCourtsResponse}
        opened={addOpened}
        setOpened={setAddOpened}
      />
      <CourtDeleteModal
        tournamentId={tournamentId}
        swrCourtsResponse={swrCourtsResponse}
        courts={courts}
        matchesByCourtId={matchesByCourtId}
        opened={deleteOpened}
        setOpened={setDeleteOpened}
      />
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
