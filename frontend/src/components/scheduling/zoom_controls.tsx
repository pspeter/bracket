import { ActionIcon, Paper, Stack } from '@mantine/core';
import { IconMinus, IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { PlannerEvent } from '@logic/planning/selection';
import { ZoomLevel } from '@logic/planning/zoom';

import { PLANNER_DESELECT_IGNORE_ATTRIBUTE, resolveGridCenterAnchor } from './planner_anchor';

/**
 * Floating ± buttons that snap the schedule grid between its three semantic
 * zoom levels; the desktop counterpart to pinching.
 */
export default function ZoomControls({
  zoom,
  onZoomEvent,
}: {
  zoom: ZoomLevel;
  onZoomEvent: (event: PlannerEvent) => void;
}) {
  const { t } = useTranslation();

  return (
    <Paper
      shadow="md"
      radius="xl"
      withBorder
      p={4}
      {...{ [PLANNER_DESELECT_IGNORE_ATTRIBUTE]: true }}
    >
      <Stack gap={4}>
        <ActionIcon
          variant="subtle"
          color="gray"
          radius="xl"
          size="lg"
          disabled={zoom === 'agenda'}
          aria-label={t('zoom_in_label')}
          onClick={() => onZoomEvent({ type: 'zoom-in', anchor: resolveGridCenterAnchor() })}
        >
          <IconPlus size={20} />
        </ActionIcon>
        <ActionIcon
          variant="subtle"
          color="gray"
          radius="xl"
          size="lg"
          disabled={zoom === 'overview'}
          aria-label={t('zoom_out_label')}
          onClick={() => onZoomEvent({ type: 'zoom-out', anchor: resolveGridCenterAnchor() })}
        >
          <IconMinus size={20} />
        </ActionIcon>
      </Stack>
    </Paper>
  );
}
