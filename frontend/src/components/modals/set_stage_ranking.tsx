import { Button, Modal } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { RankingSelect } from '@components/select/ranking_select';
import {
  Ranking,
  StageWithStageItems,
  StagesWithStageItemsResponse,
  TournamentWithLevels,
} from '@openapi';
import { setRankingForStageItems } from '@services/stage';

function getSharedRankingId(stage: StageWithStageItems): string {
  const rankingIds = new Set(stage.stage_items.map((stageItem) => stageItem.ranking_id));
  // Pre-select the ranking only when every stage item already shares it; otherwise leave the
  // selection empty so it is clear the action will unify them.
  return rankingIds.size === 1 ? (stage.stage_items[0].ranking_id?.toString() ?? '') : '';
}

export function SetStageRankingModal({
  tournament,
  opened,
  setOpened,
  stage,
  rankings,
  swrStagesResponse,
}: {
  tournament: TournamentWithLevels;
  opened: boolean;
  setOpened: (opened: boolean) => void;
  stage: StageWithStageItems;
  rankings: Ranking[];
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
}) {
  const { t } = useTranslation();
  const form = useForm({
    initialValues: { ranking_id: getSharedRankingId(stage) },
    validate: {
      ranking_id: (value) => (value !== '' ? null : t('ranking_required_validation')),
    },
  });

  return (
    <Modal
      opened={opened}
      onClose={() => setOpened(false)}
      title={t('set_ranking_for_stage_items_label')}
    >
      <form
        onSubmit={form.onSubmit(async (values) => {
          await setRankingForStageItems(tournament.id, stage.id, Number(values.ranking_id));
          await swrStagesResponse.mutate();
          setOpened(false);
        })}
      >
        <RankingSelect form={form} rankings={rankings} />
        <Button fullWidth style={{ marginTop: 16 }} color="green" type="submit">
          {t('save_button')}
        </Button>
      </form>
    </Modal>
  );
}
