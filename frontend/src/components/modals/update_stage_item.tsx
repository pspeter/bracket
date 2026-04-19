import { Button, Modal, NumberInput, Select, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { RankingSelect } from '@components/select/ranking_select';
import { Ranking, StageItemWithRounds, StagesWithStageItemsResponse, Tournament } from '@openapi';
import { updateStageItem } from '@services/stage_item';

interface FormValues {
  name: string;
  ranking_id: string;
  team_count_round_robin: number;
  team_count_elimination: string;
}

function TeamCountSelectElimination({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string | null) => void;
}) {
  const { t } = useTranslation();
  const data = [
    { value: '2', label: '2' },
    { value: '4', label: '4' },
    { value: '8', label: '8' },
    { value: '16', label: '16' },
    { value: '32', label: '32' },
  ];

  return (
    <Select
      withAsterisk
      data={data}
      label={t('team_count_select_elimination_label')}
      placeholder={t('team_count_select_elimination_placeholder')}
      searchable
      limit={20}
      my="lg"
      maw="50%"
      value={value}
      onChange={onChange}
    />
  );
}

function TeamCountInputRoundRobin({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: string | number) => void;
}) {
  const { t } = useTranslation();

  return (
    <NumberInput
      withAsterisk
      label={t('team_count_input_round_robin_label')}
      placeholder=""
      my="lg"
      maw="50%"
      value={value}
      onChange={onChange}
    />
  );
}

export function UpdateStageItemModal({
  tournament,
  opened,
  setOpened,
  stageItem,
  swrStagesResponse,
  rankings,
}: {
  tournament: Tournament;
  opened: boolean;
  setOpened: any;
  stageItem: StageItemWithRounds;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  rankings: Ranking[];
}) {
  const { t } = useTranslation();
  const formValues: FormValues = {
    name: stageItem.name,
    ranking_id:
      stageItem.ranking_id?.toString() ??
      rankings.filter((ranking) => ranking.position === 0)[0].id.toString(),
    team_count_round_robin: stageItem.team_count,
    team_count_elimination: stageItem.team_count.toString(),
  };
  const form = useForm<FormValues>({
    initialValues: formValues,
    validate: {
      team_count_round_robin: (value) => (value >= 2 ? null : t('at_least_two_team_validation')),
      team_count_elimination: (value) =>
        Number(value) >= 2 ? null : t('at_least_two_team_validation'),
    },
  });

  const defaultRankingId =
    stageItem.ranking_id?.toString() ??
    rankings.filter((ranking) => ranking.position === 0)[0].id.toString();

  useEffect(() => {
    if (!opened) {
      return;
    }

    form.setValues({
      name: stageItem.name,
      ranking_id: defaultRankingId,
      team_count_round_robin: stageItem.team_count,
      team_count_elimination: stageItem.team_count.toString(),
    });
  }, [defaultRankingId, opened, stageItem.id, stageItem.name, stageItem.ranking_id, stageItem.team_count]);

  const teamCount =
    stageItem.type === 'SINGLE_ELIMINATION'
      ? Number(form.values.team_count_elimination)
      : Number(form.values.team_count_round_robin);

  return (
    <Modal
      key={`${stageItem.id}-${opened ? 'open' : 'closed'}`}
      opened={opened}
      onClose={() => setOpened(false)}
      title={t('edit_stage_item_label')}
    >
      <form
        onSubmit={form.onSubmit(async (values) => {
          await updateStageItem(
            tournament.id,
            stageItem.id,
            values.name,
            values.ranking_id,
            teamCount
          );
          await swrStagesResponse.mutate();
          setOpened(false);
        })}
      >
        <TextInput
          label={t('name_input_label')}
          placeholder=""
          required
          my="lg"
          type="text"
          {...form.getInputProps('name')}
        />
        {stageItem.type === 'SINGLE_ELIMINATION' ? (
          <TeamCountSelectElimination
            value={form.values.team_count_elimination}
            onChange={(value) => form.setFieldValue('team_count_elimination', value ?? '2')}
          />
        ) : (
          <TeamCountInputRoundRobin
            value={form.values.team_count_round_robin}
            onChange={(value) => form.setFieldValue('team_count_round_robin', Number(value))}
          />
        )}
        <RankingSelect form={form} rankings={rankings} />
        <Button fullWidth style={{ marginTop: 16 }} color="green" type="submit">
          {t('save_button')}
        </Button>
      </form>
    </Modal>
  );
}
