import { Button, Menu } from '@mantine/core';
import { GoPlus } from '@react-icons/all-files/go/GoPlus';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import {
  StageItemInputOptionsResponse,
  StagesWithStageItemsResponse,
  TournamentWithLevels,
} from '@openapi';
import { createStage } from '@services/stage';

async function createStageAndRefresh(
  tournament: TournamentWithLevels,
  levelId: number | null,
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>,
  swrAvailableInputsResponse?: SWRResponse<StageItemInputOptionsResponse>
) {
  await createStage(tournament.id, levelId);
  await swrStagesResponse.mutate();
  await swrAvailableInputsResponse?.mutate();
}

export default function CreateStageButton({
  tournament,
  swrStagesResponse,
  swrAvailableInputsResponse,
}: {
  tournament: TournamentWithLevels;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
}) {
  const { t } = useTranslation();

  if (tournament.levels.length > 0) {
    return (
      <Menu withinPortal position="bottom-start" shadow="sm">
        <Menu.Target>
          <Button
            variant="outline"
            color="green"
            size="xs"
            style={{ marginRight: 10 }}
            leftSection={<GoPlus size={24} />}
          >
            {t('add_stage_button')}
          </Button>
        </Menu.Target>
        <Menu.Dropdown>
          {tournament.levels.map((level) => (
            <Menu.Item
              key={level.id}
              onClick={() =>
                createStageAndRefresh(
                  tournament,
                  level.id,
                  swrStagesResponse,
                  swrAvailableInputsResponse
                )
              }
            >
              {level.name}
            </Menu.Item>
          ))}
        </Menu.Dropdown>
      </Menu>
    );
  }

  return (
    <Button
      variant="outline"
      color="green"
      size="xs"
      style={{ marginRight: 10 }}
      onClick={() =>
        createStageAndRefresh(tournament, null, swrStagesResponse, swrAvailableInputsResponse)
      }
      leftSection={<GoPlus size={24} />}
    >
      {t('add_stage_button')}
    </Button>
  );
}

export function CreateStageButtonLarge({
  tournament,
  swrStagesResponse,
}: {
  tournament: TournamentWithLevels;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
}) {
  const { t } = useTranslation();

  if (tournament.levels.length > 0) {
    return (
      <Menu withinPortal position="bottom-start" shadow="sm">
        <Menu.Target>
          <Button
            variant="outline"
            color="green"
            size="lg"
            style={{ marginRight: 10 }}
            leftSection={<GoPlus size={24} />}
          >
            {t('add_stage_button')}
          </Button>
        </Menu.Target>
        <Menu.Dropdown>
          {tournament.levels.map((level) => (
            <Menu.Item
              key={level.id}
              onClick={() => createStageAndRefresh(tournament, level.id, swrStagesResponse)}
            >
              {level.name}
            </Menu.Item>
          ))}
        </Menu.Dropdown>
      </Menu>
    );
  }

  return (
    <Button
      variant="outline"
      color="green"
      size="lg"
      style={{ marginRight: 10 }}
      onClick={() => createStageAndRefresh(tournament, null, swrStagesResponse)}
      leftSection={<GoPlus size={24} />}
    >
      {t('add_stage_button')}
    </Button>
  );
}
