import { Alert, Button, Modal, Select } from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconAlertCircle, IconSquareArrowLeft } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { LevelResponse, StageRankingResponse, StagesWithStageItemsResponse } from '@openapi';
import { activateNextStage } from '@services/stage';

export default function ActivatePreviousStageModal({
  tournamentId,
  swrStagesResponse,
  swrRankingsPerStageItemResponse,
  levels,
  levelId,
  onLevelChange,
}: {
  tournamentId: number;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrRankingsPerStageItemResponse: SWRResponse<StageRankingResponse>;
  levels: LevelResponse[];
  levelId: string;
  onLevelChange: (levelId: string) => void;
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);

  const form = useForm({
    initialValues: {},
  });

  const hasActiveStage = swrStagesResponse.data?.data?.some((stage) => stage.is_active) ?? false;
  if (!hasActiveStage) {
    return null;
  }

  return (
    <>
      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title={t('active_previous_stage_modal_title')}
        size="40rem"
      >
        <form
          onSubmit={form.onSubmit(async () => {
            await activateNextStage(
              tournamentId,
              'previous',
              levelId === 'all' ? null : Number(levelId)
            );
            swrStagesResponse.mutate();
            swrRankingsPerStageItemResponse.mutate();
            setOpened(false);
          })}
        >
          <Alert icon={<IconAlertCircle size={16} />} color="orange" radius="lg">
            {t('active_previous_stage_modal_description')}
          </Alert>

          {levels.length > 0 ? (
            <Select
              withAsterisk
              label={t('filter_level_label')}
              placeholder={t('filter_level_placeholder')}
              data={levels.map((level) => ({ value: `${level.id}`, label: level.name }))}
              value={levelId}
              onChange={(value) => onLevelChange(value ?? `${levels[0].id}`)}
              mt="md"
            />
          ) : null}

          <Button
            fullWidth
            color="indigo"
            size="md"
            mt="lg"
            type="submit"
            leftSection={<IconSquareArrowLeft size={24} />}
          >
            {t('plan_previous_stage_button')}
          </Button>
        </form>
      </Modal>

      <Button
        size="md"
        mb="10"
        color="indigo"
        leftSection={<IconSquareArrowLeft size={24} />}
        onClick={async () => {
          setOpened(true);
        }}
      >
        {t('previous_stage_button')}
      </Button>
    </>
  );
}
