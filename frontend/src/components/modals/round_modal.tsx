import { ActionIcon, Button, Modal, TextInput, Title, UnstyledButton } from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconPencil } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import DeleteButton from '@components/buttons/delete';
import { TournamentMinimal } from '@components/utils/tournament';
import { RoundWithMatches, StagesWithStageItemsResponse } from '@openapi';
import { deleteRound, updateRound } from '@services/round';

function RoundDeleteButton({
  tournamentData,
  round,
  swrStagesResponse,
}: {
  tournamentData: TournamentMinimal;
  round: RoundWithMatches;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
}) {
  const { t } = useTranslation();
  return (
    <DeleteButton
      fullWidth
      onClick={async () => {
        await deleteRound(tournamentData.id, round.id);
        await swrStagesResponse.mutate();
      }}
      style={{ marginTop: '15px' }}
      size="sm"
      title={t('delete_round_button')}
    />
  );
}

export default function RoundModal({
  tournamentData,
  round,
  swrStagesResponse,
}: {
  tournamentData: TournamentMinimal;
  round: RoundWithMatches;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);

  const form = useForm({
    initialValues: {
      name: round == null ? '' : round.name,
    },

    validate: {
      name: (value) => (value.length > 0 ? null : t('too_short_name_validation')),
    },
  });

  return (
    <>
      <Modal opened={opened} onClose={() => setOpened(false)} title={t('edit_round')}>
        <form
          onSubmit={form.onSubmit(async (values) => {
            await updateRound(
              tournamentData.id,
              round.id,
              values.name,
              round.lifecycle_state ?? 'ACTIVE'
            );
            await swrStagesResponse.mutate();
            setOpened(false);
          })}
        >
          <TextInput
            withAsterisk
            label={t('name_input_label')}
            placeholder={t('round_name_input_placeholder')}
            {...form.getInputProps('name')}
          />
          <Button fullWidth mt="1rem" color="green" type="submit">
            {t('save_button')}
          </Button>
        </form>
        <RoundDeleteButton
          swrStagesResponse={swrStagesResponse}
          tournamentData={tournamentData}
          round={round}
        />
      </Modal>

      <UnstyledButton onClick={() => setOpened(true)}>
        <Title order={3}>{round.name}</Title>
      </UnstyledButton>
      <ActionIcon
        variant="subtle"
        ml="0.5rem"
        mb="0.25rem"
        color="gray"
        onClick={() => setOpened(true)}
      >
        <IconPencil size={18} style={{ marginBottom: '5px' }} />
      </ActionIcon>
    </>
  );
}
