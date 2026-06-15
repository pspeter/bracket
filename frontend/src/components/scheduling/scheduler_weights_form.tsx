import { Anchor, Collapse, NumberInput, SimpleGrid, Stack } from '@mantine/core';
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { SchedulerWeights } from '@openapi';

// The auto-scheduler's objective weights. Defaults mirror the backend's tuned
// constants (PRD #73); they are the starting point shown in the advanced panel
// before an organizer overrides them for a specific tournament.
export const DEFAULT_SCHEDULER_WEIGHTS: SchedulerWeights = {
  makespan: 150,
  team_rest: 13,
  group_sync: 8,
  court_locality: 4,
  comfortable_rest_minutes: 30,
  referee_fairness: 200,
};

export default function SchedulerWeightsForm({
  weights,
  onChange,
  opened,
  onToggle,
}: {
  weights: SchedulerWeights;
  onChange: (weights: SchedulerWeights) => void;
  opened: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();

  const setField = (field: keyof SchedulerWeights) => (value: string | number) =>
    onChange({ ...weights, [field]: typeof value === 'number' ? value : Number(value) || 0 });

  return (
    <Stack gap="xs">
      <Anchor
        component="button"
        type="button"
        onClick={onToggle}
        size="sm"
        c="dimmed"
        style={{ alignSelf: 'flex-start' }}
      >
        {opened ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}{' '}
        {t('scheduler_advanced_label')}
      </Anchor>
      <Collapse in={opened}>
        <SimpleGrid cols={2} spacing="sm">
          <NumberInput
            label={t('scheduler_weight_makespan_label')}
            min={0}
            value={weights.makespan}
            onChange={setField('makespan')}
          />
          <NumberInput
            label={t('scheduler_weight_team_rest_label')}
            min={0}
            value={weights.team_rest}
            onChange={setField('team_rest')}
          />
          <NumberInput
            label={t('scheduler_weight_group_sync_label')}
            min={0}
            value={weights.group_sync}
            onChange={setField('group_sync')}
          />
          <NumberInput
            label={t('scheduler_weight_court_locality_label')}
            min={0}
            value={weights.court_locality}
            onChange={setField('court_locality')}
          />
          <NumberInput
            label={t('scheduler_weight_comfortable_rest_label')}
            min={0}
            value={weights.comfortable_rest_minutes}
            onChange={setField('comfortable_rest_minutes')}
          />
          <NumberInput
            label={t('scheduler_weight_referee_fairness_label')}
            min={0}
            value={weights.referee_fairness}
            onChange={setField('referee_fairness')}
          />
        </SimpleGrid>
      </Collapse>
    </Stack>
  );
}
