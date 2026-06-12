import { Button, Group, Modal, NumberInput, Text } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { MatchWithDetails } from '@openapi';
import { updateMatch } from '@services/match';

export type TimingField = 'duration' | 'margin';

/**
 * Quick editor for a single timing field of a match — its custom duration or the
 * pause after it (margin) — opened from the planner's action sheet. Saves via the
 * match update endpoint, whose start-time recomputation re-packs the court; the
 * caller revalidates the schedule so the grid reflects the change immediately.
 */
function TimingForm({
  tournamentId,
  match,
  field,
  onClose,
  onSaved,
}: {
  tournamentId: number;
  match: MatchWithDetails;
  field: TimingField;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const isCustom =
    field === 'duration'
      ? match.custom_duration_minutes != null
      : match.custom_margin_minutes != null;
  const [value, setValue] = useState<number | string>(
    field === 'duration' ? match.duration_minutes : match.margin_minutes
  );

  async function save(customMinutes: number | null) {
    await updateMatch(tournamentId, match.id, {
      round_id: match.round_id,
      stage_item_input1_score: match.stage_item_input1_score,
      stage_item_input2_score: match.stage_item_input2_score,
      court_id: match.court_id ?? null,
      custom_duration_minutes:
        field === 'duration' ? customMinutes : (match.custom_duration_minutes ?? null),
      custom_margin_minutes:
        field === 'margin' ? customMinutes : (match.custom_margin_minutes ?? null),
      state: match.state,
      completed_at: match.completed_at ?? null,
    });
    await onSaved();
    onClose();
  }

  return (
    <>
      <NumberInput
        min={0}
        value={value}
        onChange={setValue}
        rightSection={<Text>{t('minutes')}</Text>}
        rightSectionWidth={92}
        data-autofocus
      />
      <Group mt="md" grow>
        {isCustom && (
          <Button variant="light" onClick={() => save(null)}>
            {t('reset_to_default_button')}
          </Button>
        )}
        <Button
          color="green"
          disabled={typeof value !== 'number'}
          onClick={() => save(value as number)}
        >
          {t('save_button')}
        </Button>
      </Group>
    </>
  );
}

export default function MatchTimingModal({
  tournamentId,
  match,
  field,
  opened,
  onClose,
  onSaved,
}: {
  tournamentId: number;
  match: MatchWithDetails | null;
  field: TimingField;
  opened: boolean;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { t } = useTranslation();

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        field === 'duration' ? t('custom_match_duration_label') : t('custom_match_margin_label')
      }
    >
      {match != null && (
        <TimingForm
          key={`${match.id}-${field}`}
          tournamentId={tournamentId}
          match={match}
          field={field}
          onClose={onClose}
          onSaved={onSaved}
        />
      )}
    </Modal>
  );
}
