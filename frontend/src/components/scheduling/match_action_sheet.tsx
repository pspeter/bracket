import { Button, Drawer, Stack, Text } from '@mantine/core';
import { IconArrowsMove, IconCalendarOff, IconListDetails } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { MatchWithDetails } from '@openapi';
import { MatchLookupEntry, getStageItemLookup } from '@services/lookups';

/**
 * Bottom action sheet with the secondary per-match operations, opened by tapping
 * an already-selected match (or a soft-locked played match, which can't be
 * plainly selected). Dismissing it returns to the selected state; each button
 * dispatches back to the page, which owns the reducer and the details modal.
 *
 * The match details modal is the single place for editing — scores, state and
 * custom duration/margin. Played (locked) matches can't be unscheduled (the
 * backend rejects it), so they get the explicit "move anyway" override instead,
 * which lifts the soft lock for one placement operation.
 */
export default function MatchActionSheet({
  match,
  locked,
  opened,
  stageItemsLookup,
  matchesLookup,
  onDismiss,
  onOpenDetails,
  onUnschedule,
  onMoveAnyway,
}: {
  match: MatchWithDetails | null;
  locked: boolean;
  opened: boolean;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  onDismiss: () => void;
  onOpenDetails: () => void;
  onUnschedule: () => void;
  onMoveAnyway: () => void;
}) {
  const { t } = useTranslation();

  return (
    <Drawer
      opened={opened}
      onClose={onDismiss}
      position="bottom"
      // A true bottom sheet: hug the content's height instead of a fixed share
      // of the screen, so the grid stays visible behind the overlay.
      styles={{
        content: { height: 'auto', borderTopLeftRadius: 12, borderTopRightRadius: 12 },
      }}
      zIndex={400}
      title={
        match != null ? (
          <Text fw={600} component="span">
            {formatMatchInput1(t, stageItemsLookup, matchesLookup, match)} –{' '}
            {formatMatchInput2(t, stageItemsLookup, matchesLookup, match)}
          </Text>
        ) : null
      }
    >
      <Stack gap="xs">
        <Button
          variant="light"
          justify="flex-start"
          leftSection={<IconListDetails size={20} />}
          onClick={onOpenDetails}
        >
          {t('match_details_button')}
        </Button>
        {locked ? (
          <>
            <Button
              variant="light"
              color="orange"
              justify="flex-start"
              leftSection={<IconArrowsMove size={20} />}
              onClick={onMoveAnyway}
            >
              {t('move_anyway_button')}
            </Button>
            <Text size="xs" c="dimmed">
              {t('move_anyway_description')}
            </Text>
          </>
        ) : (
          <Button
            variant="light"
            color="orange"
            justify="flex-start"
            leftSection={<IconCalendarOff size={20} />}
            onClick={onUnschedule}
          >
            {t('unschedule_button')}
          </Button>
        )}
      </Stack>
    </Drawer>
  );
}
