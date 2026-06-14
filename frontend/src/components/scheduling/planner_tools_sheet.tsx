import { Button, Divider, Drawer, Select, Stack } from '@mantine/core';
import { IconCalendarPlus, IconPlus, IconTrash, IconWand } from '@tabler/icons-react';
import { ComponentProps, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import CourtModal from '@components/modals/create_court_modal';
import CourtDeleteModal from '@components/scheduling/court_delete_modal';
import { Court, CourtsResponse, MatchWithDetails } from '@openapi';

/**
 * Mobile-only bottom sheet that gathers the planner's top-toolbar controls —
 * team highlight, court add/delete and the two auto-schedule actions — behind a
 * single tools button, so the awkward inline toolbar disappears on small
 * screens. Opening a court modal or an auto-schedule modal closes this sheet
 * first to avoid stacking two overlays; the court modals stay mounted here so
 * they survive that close.
 */
export default function PlannerToolsSheet({
  opened,
  onClose,
  tournamentId,
  swrCourtsResponse,
  courts,
  matchesByCourtId,
  highlightOptions,
  highlightValue,
  onHighlightChange,
  onSchedule,
  onReoptimize,
}: {
  opened: boolean;
  onClose: () => void;
  tournamentId: number;
  swrCourtsResponse: SWRResponse<CourtsResponse>;
  courts: Court[];
  matchesByCourtId: Record<number, MatchWithDetails[]>;
  highlightOptions: ComponentProps<typeof Select>['data'];
  highlightValue: string | null;
  onHighlightChange: (value: string | null) => void;
  onSchedule: () => void;
  onReoptimize: () => void;
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
      <Drawer
        opened={opened}
        onClose={onClose}
        position="bottom"
        // A true bottom sheet: hug the content's height so the grid stays
        // visible behind the overlay, matching the match action sheet.
        styles={{
          content: { height: 'auto', borderTopLeftRadius: 12, borderTopRightRadius: 12 },
        }}
        zIndex={400}
        title={t('planner_tools_title')}
      >
        <Stack gap="xs">
          <Select
            aria-label={t('team_highlight_label', 'Highlight team or input')}
            placeholder={t('team_highlight_placeholder', 'Find team or input')}
            data={highlightOptions}
            value={highlightValue}
            onChange={onHighlightChange}
            searchable
            clearable
            limit={100}
          />
          <Divider />
          <Button
            variant="light"
            color="green"
            justify="flex-start"
            leftSection={<IconPlus size={20} />}
            onClick={() => {
              onClose();
              setAddOpened(true);
            }}
          >
            {t('add_court_title')}
          </Button>
          <Button
            variant="light"
            color="red"
            justify="flex-start"
            leftSection={<IconTrash size={20} />}
            onClick={() => {
              onClose();
              setDeleteOpened(true);
            }}
          >
            {t('delete_court_button')}
          </Button>
          <Divider />
          <Button
            variant="light"
            color="indigo"
            justify="flex-start"
            leftSection={<IconCalendarPlus size={20} />}
            onClick={() => {
              onClose();
              onSchedule();
            }}
          >
            {t('schedule_description')}
          </Button>
          <Button
            variant="light"
            color="indigo"
            justify="flex-start"
            leftSection={<IconWand size={20} />}
            onClick={() => {
              onClose();
              onReoptimize();
            }}
          >
            {t('reoptimize_description')}
          </Button>
        </Stack>
      </Drawer>
    </>
  );
}
