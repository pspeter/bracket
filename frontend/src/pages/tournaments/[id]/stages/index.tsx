import { Group, Stack, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import Builder from '@components/builder/builder';
import { CreateStageButtonLarge } from '@components/buttons/create_stage';
import ActivateNextStageModal from '@components/modals/activate_next_stage_modal';
import { CreateFromTemplateButton } from '@components/modals/create_from_template_modal';
import ActivatePreviousStageModal from '@components/modals/activate_previous_stage_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import { TableSkeletonTwoColumnsSmall } from '@components/utils/skeletons';
import { getTournamentIdFromRouter } from '@components/utils/util';
import { StageWithStageItems } from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import {
  getAvailableStageItemInputs,
  getRankings,
  getRankingsPerStageItem,
  getStages,
  getTeams,
  getTournamentById,
} from '@services/adapter';
import { getAssignedTeamIds } from '@services/lookups';

export default function StagesPage() {
  const { t } = useTranslation();
  const { tournamentData } = getTournamentIdFromRouter();
  const swrStagesResponse = getStages(tournamentData.id);
  const swrTeamsResponse = getTeams(tournamentData.id);
  const swrRankingsResponse = getRankings(tournamentData.id);
  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const swrAvailableInputsResponse = getAvailableStageItemInputs(tournamentData.id);
  const swrRankingsPerStageItemResponse = getRankingsPerStageItem(tournamentData.id);
  const tournamentDataFull =
    swrTournamentResponse.data != null ? swrTournamentResponse.data.data : null;
  const rankings = swrRankingsResponse.data != null ? swrRankingsResponse.data.data : [];

  const stages: StageWithStageItems[] =
    swrStagesResponse.data != null ? swrStagesResponse.data.data : [];
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
            swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
            buttonSize="lg"
          />
        </Group>
      </Stack>
    );
  } else {
    content = (
      <>
        <Stack gap="xs" mt="1rem" maw="30rem">
          <Group grow>
            <ActivatePreviousStageModal
              tournamentId={tournamentData.id}
              swrStagesResponse={swrStagesResponse}
              swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
            />
            <ActivateNextStageModal
              tournamentId={tournamentData.id}
              swrStagesResponse={swrStagesResponse}
              swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
            />
          </Group>
          <Text c="dimmed" size="sm">
            {t('stage_unassigned_teams_notice', { count: unassignedTeamCount })}
          </Text>
        </Stack>
        <Group mt="1rem" align="top">
          <Builder
            tournament={tournamentDataFull}
            registeredTeamCount={totalTeamCount}
            swrStagesResponse={swrStagesResponse}
            swrAvailableInputsResponse={swrAvailableInputsResponse}
            swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
            rankings={rankings}
          />
        </Group>
      </>
    );
  }

  return <TournamentLayout tournament_id={tournamentData.id}>{content}</TournamentLayout>;
}
