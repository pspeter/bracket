import { Alert, Container, Group, Skeleton, Stack } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { NoContent } from '@components/no_content/empty_table_info';
import { BracketDisplaySettings } from '@components/utils/brackets';
import { responseIsValid } from '@components/utils/util';
import {
  RoundWithMatches,
  StageItemWithRounds,
  StagesWithStageItemsResponse,
  TournamentWithLevels,
} from '@openapi';
import RoundComponent from './round';

function NoRoundsAlert({ readOnly }: { readOnly: boolean }) {
  const { t } = useTranslation();
  if (readOnly) {
    return (
      <Alert
        icon={<IconAlertCircle size={16} />}
        title={t('no_round_found_title')}
        color="blue"
        radius="lg"
      >
        {t('no_round_found_description')}
      </Alert>
    );
  }
  return (
    <Container>
      <Alert
        icon={<IconAlertCircle size={16} />}
        title={t('no_round_found_title')}
        color="blue"
        radius="lg"
      >
        {t('no_round_found_in_stage_description')}
      </Alert>
    </Container>
  );
}

function LoadingSkeleton() {
  return (
    <Group>
      <div style={{ width: '400px', marginLeft: '1rem' }}>
        <Skeleton height={500} mb="xl" radius="xl" />
      </div>
      <div style={{ width: '400px', marginLeft: '1rem' }}>
        <Skeleton height={500} mb="xl" radius="xl" />
      </div>
    </Group>
  );
}

export function SwissRoundsGrid({
  stageItem,
  tournamentData,
  swrStagesResponse,
  displaySettings,
}: {
  stageItem: StageItemWithRounds;
  tournamentData: TournamentWithLevels;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  displaySettings: BracketDisplaySettings;
}) {
  const { t } = useTranslation();

  if (swrStagesResponse.isLoading) {
    return <LoadingSkeleton />;
  }
  if (!responseIsValid(swrStagesResponse)) {
    return <NoRoundsAlert readOnly={false} />;
  }

  const rounds = stageItem.rounds
    .sort((r1: any, r2: any) => (r1.name > r2.name ? 1 : -1))
    .filter(
      (round: RoundWithMatches) =>
        round.matches.length > 0 || displaySettings.matchVisibility === 'all'
    );

  if (rounds.length === 0) {
    return (
      <Container mt="1rem">
        <Stack align="center">
          <NoContent title={t('no_round_description')} />
        </Stack>
      </Container>
    );
  }

  return (
    <React.Fragment key={stageItem.id}>
      <Group align="top">
        {rounds.map((round: RoundWithMatches) => (
          <RoundComponent
            key={round.id}
            tournamentData={tournamentData}
            round={round}
            swrStagesResponse={swrStagesResponse}
            readOnly={false}
            displaySettings={displaySettings}
            showLifecycleState={true}
            refereesEnabled={tournamentData.referees_enabled}
          />
        ))}
      </Group>
    </React.Fragment>
  );
}
