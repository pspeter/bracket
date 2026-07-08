import { Group, Stack, Text } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import Builder from '@components/builder/builder';
import { CreateStageButtonLarge } from '@components/buttons/create_stage';
import { LevelFilterSelect } from '@components/levels/levels';
import { CreateFromTemplateButton } from '@components/modals/create_from_template_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import { TableSkeletonTwoColumnsSmall } from '@components/utils/skeletons';
import { getTournamentIdFromRouter } from '@components/utils/util';
import { StageWithStageItems } from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import {
  getAvailableStageItemInputs,
  getRankings,
  getStages,
  getTeams,
  getTournamentById,
} from '@services/adapter';
import { getAssignedTeamIds } from '@services/lookups';

export default function StagesPage() {
  const { t } = useTranslation();
  const [filteredLevelId, setFilteredLevelId] = useState('all');
  const { tournamentData } = getTournamentIdFromRouter();
  const swrStagesResponse = getStages(tournamentData.id);
  const swrTeamsResponse = getTeams(tournamentData.id);
  const swrRankingsResponse = getRankings(tournamentData.id);
  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const swrAvailableInputsResponse = getAvailableStageItemInputs(tournamentData.id);
  const tournamentDataFull =
    swrTournamentResponse.data != null ? swrTournamentResponse.data.data : null;
  const levels = tournamentDataFull?.levels ?? [];
  const rankings = swrRankingsResponse.data != null ? swrRankingsResponse.data.data : [];

  const stages: StageWithStageItems[] =
    swrStagesResponse.data != null ? swrStagesResponse.data.data : [];
  const filteredStages =
    filteredLevelId === 'all'
      ? stages
      : stages.filter((stage) => `${stage.level_id}` === filteredLevelId);
  const assignedTeamCount =
    swrStagesResponse.data != null ? getAssignedTeamIds(swrStagesResponse).length : 0;
  const totalTeamCount = swrTeamsResponse.data?.data.count ?? 0;
  const unassignedTeamCount = Math.max(totalTeamCount - assignedTeamCount, 0);

  let content;
  if (
    swrStagesResponse.isLoading ||
    swrTeamsResponse.isLoading ||
    swrTournamentResponse.isLoading ||
    swrAvailableInputsResponse.isLoading ||
    swrRankingsResponse.isLoading
  ) {
    content = <TableSkeletonTwoColumnsSmall />;
  } else if (tournamentDataFull == null) {
    // TODO: show loading icon.
    return null;
  } else if (stages.length < 1) {
    content = (
      <Stack align="center">
        <NoContent title={t('no_matches_title')} description={t('no_matches_description')} />
        <Group justify="center" gap="md" wrap="wrap">
          <CreateStageButtonLarge
            tournament={tournamentDataFull}
            swrStagesResponse={swrStagesResponse}
          />
          <CreateFromTemplateButton
            tournament={tournamentDataFull}
            registeredTeamCount={totalTeamCount}
            swrStagesResponse={swrStagesResponse}
            swrAvailableInputsResponse={swrAvailableInputsResponse}
            buttonSize="lg"
          />
        </Group>
      </Stack>
    );
  } else {
    content = (
      <>
        <Stack gap="xs" mt="1rem" maw="30rem">
          <Text c="dimmed" size="sm">
            {t('stage_unassigned_teams_notice', { count: unassignedTeamCount })}
          </Text>
        </Stack>
        <Stack mt="1rem" gap="md">
          <LevelFilterSelect
            levels={levels}
            value={filteredLevelId}
            onChange={setFilteredLevelId}
            label={t('filter_level_label')}
            placeholder={t('filter_level_placeholder')}
            allLevelsLabel={t('all_levels_label')}
          />
          <Builder
            tournament={tournamentDataFull}
            registeredTeamCount={totalTeamCount}
            swrStagesResponse={swrStagesResponse}
            swrAvailableInputsResponse={swrAvailableInputsResponse}
            rankings={rankings}
            stages={filteredStages}
          />
        </Stack>
      </>
    );
  }

  return <TournamentLayout tournament_id={tournamentData.id}>{content}</TournamentLayout>;
}
